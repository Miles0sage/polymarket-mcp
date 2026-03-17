"""Paper trading engine + CLOB API helpers for Polymarket MCP.

SQLite-backed paper trading with risk controls, plus live orderbook helpers
for future real trading integration.
"""

import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_DB_DIR = os.path.expanduser("~/.polymarket-mcp")
DEFAULT_DB_PATH = os.path.join(DEFAULT_DB_DIR, "paper_trades.db")

MAX_POSITION_SIZE: float = 100.0   # dollars per trade
DAILY_LOSS_LIMIT: float = 500.0    # max cumulative loss in a calendar day
KELLY_FRACTION: float = 0.25       # quarter-Kelly

CLOB_BASE_URL = "https://clob.polymarket.com"


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _db_path() -> str:
    """Return the SQLite DB path, creating the directory if needed."""
    Path(DEFAULT_DB_DIR).mkdir(parents=True, exist_ok=True)
    return DEFAULT_DB_PATH


def _connect() -> sqlite3.Connection:
    """Open a connection with row-factory enabled."""
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the paper_trades table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS paper_trades (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            market_id     TEXT    NOT NULL,
            question      TEXT    NOT NULL DEFAULT '',
            side          TEXT    NOT NULL CHECK(side IN ('YES','NO')),
            amount        REAL    NOT NULL,
            entry_price   REAL    NOT NULL,
            current_price REAL    NOT NULL,
            settled       INTEGER NOT NULL DEFAULT 0,
            outcome       TEXT    DEFAULT NULL,
            pnl           REAL    DEFAULT NULL,
            created_at    TEXT    NOT NULL,
            settled_at    TEXT    DEFAULT NULL
        )
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# Risk controls
# ---------------------------------------------------------------------------

def _check_position_size(amount: float, max_size: float = MAX_POSITION_SIZE) -> Optional[str]:
    """Return an error string if amount exceeds the per-trade cap."""
    if amount <= 0:
        return "Error: amount must be positive"
    if amount > max_size:
        return f"Error: amount ${amount:.2f} exceeds max position size ${max_size:.2f}"
    return None


def _check_daily_loss(conn: sqlite3.Connection, limit: float = DAILY_LOSS_LIMIT) -> Optional[str]:
    """Return an error string if today's realised losses already hit the limit."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = conn.execute(
        """
        SELECT COALESCE(SUM(pnl), 0) AS daily_pnl
        FROM paper_trades
        WHERE settled = 1
          AND settled_at LIKE ? || '%'
        """,
        (today,),
    ).fetchone()
    daily_pnl = row["daily_pnl"]
    if daily_pnl <= -limit:
        return (
            f"Error: daily loss limit reached. "
            f"Today's P&L: ${daily_pnl:+.2f} (limit: -${limit:.2f})"
        )
    return None


def _quarter_kelly_check(amount: float, bankroll: float, probability: float, price: float) -> Optional[str]:
    """Warn (but don't block) if the bet exceeds quarter-Kelly sizing.

    Returns a warning string or None.
    """
    if bankroll <= 0 or probability <= 0 or probability >= 1 or price <= 0 or price >= 1:
        return None  # can't compute — skip check

    odds = 1.0 / price
    b = odds - 1  # net odds
    p = probability
    q = 1 - p

    kelly_f = (p * b - q) / b if b > 0 else 0
    quarter_kelly_f = max(kelly_f * KELLY_FRACTION, 0)
    suggested = bankroll * quarter_kelly_f

    if amount > suggested and suggested > 0:
        return (
            f"Warning: amount ${amount:.2f} exceeds quarter-Kelly suggestion "
            f"${suggested:.2f} ({quarter_kelly_f:.1%} of ${bankroll:.2f} bankroll)"
        )
    return None


# ---------------------------------------------------------------------------
# Paper trading functions
# ---------------------------------------------------------------------------

def paper_trade(
    market_id: str,
    side: str,
    amount: float,
    yes_price: float,
    question: str = "",
    estimated_probability: float = 0.0,
    bankroll: float = 0.0,
    max_position: float = MAX_POSITION_SIZE,
    daily_limit: float = DAILY_LOSS_LIMIT,
) -> str:
    """Simulate placing a bet on a Polymarket outcome.

    Args:
        market_id: The market condition ID or slug.
        side: 'YES' or 'NO'.
        amount: Dollar amount to wager.
        yes_price: Current YES price (0-1).
        question: Human-readable market question (optional).
        estimated_probability: Your estimated true probability for quarter-Kelly check.
        bankroll: Total bankroll for Kelly sizing (optional, 0 skips check).
        max_position: Override max position size per trade.
        daily_limit: Override daily loss limit.

    Returns:
        Confirmation string with trade details.
    """
    side = side.upper()
    if side not in ("YES", "NO"):
        return "Error: side must be 'YES' or 'NO'"
    if yes_price <= 0 or yes_price >= 1:
        return "Error: yes_price must be between 0 and 1 (exclusive)"

    # --- risk checks ---
    err = _check_position_size(amount, max_position)
    if err:
        return err

    conn = _connect()
    _ensure_schema(conn)

    err = _check_daily_loss(conn, daily_limit)
    if err:
        conn.close()
        return err

    # quarter-Kelly warning (non-blocking)
    price = yes_price if side == "YES" else (1 - yes_price)
    warning = ""
    if bankroll > 0 and estimated_probability > 0:
        w = _quarter_kelly_check(amount, bankroll, estimated_probability, price)
        if w:
            warning = f"\n{w}"

    now = datetime.now(timezone.utc).isoformat()
    shares = amount / price

    conn.execute(
        """
        INSERT INTO paper_trades
            (market_id, question, side, amount, entry_price, current_price, settled, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 0, ?)
        """,
        (market_id, question, side, amount, price, price, now),
    )
    conn.commit()
    trade_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()

    return (
        f"Paper trade #{trade_id} placed\n"
        f"Market: {question or market_id}\n"
        f"Side: {side} @ {price:.2f} ({price:.0%})\n"
        f"Amount: ${amount:.2f} | Shares: {shares:.2f}\n"
        f"Potential payout: ${shares:.2f}{warning}"
    )


def paper_portfolio() -> str:
    """Show all open (unsettled) paper positions with unrealised P&L.

    Returns:
        Formatted table of open positions.
    """
    conn = _connect()
    _ensure_schema(conn)

    rows = conn.execute(
        "SELECT * FROM paper_trades WHERE settled = 0 ORDER BY created_at DESC"
    ).fetchall()
    conn.close()

    if not rows:
        return "No open paper positions."

    total_invested = 0.0
    total_current = 0.0
    lines = ["Open Paper Positions", "=" * 50]

    for r in rows:
        shares = r["amount"] / r["entry_price"]
        current_value = shares * r["current_price"]
        unrealised = current_value - r["amount"]
        total_invested += r["amount"]
        total_current += current_value

        lines.append(
            f"#{r['id']} | {r['side']} {r['question'] or r['market_id']}\n"
            f"   Entry: {r['entry_price']:.2f} | Current: {r['current_price']:.2f}\n"
            f"   Amount: ${r['amount']:.2f} | Value: ${current_value:.2f} | "
            f"P&L: ${unrealised:+.2f} ({unrealised / r['amount']:+.0%})\n"
            f"   Opened: {r['created_at'][:19]}"
        )

    total_pnl = total_current - total_invested
    lines.append("=" * 50)
    lines.append(
        f"Total invested: ${total_invested:.2f} | "
        f"Current value: ${total_current:.2f} | "
        f"Unrealised P&L: ${total_pnl:+.2f}"
    )

    return "\n".join(lines)


def paper_settle(trade_id: int, outcome: str) -> str:
    """Manually settle a paper trade.

    Args:
        trade_id: The trade ID to settle.
        outcome: 'WIN' or 'LOSE'.

    Returns:
        Settlement confirmation with P&L.
    """
    outcome = outcome.upper()
    if outcome not in ("WIN", "LOSE"):
        return "Error: outcome must be 'WIN' or 'LOSE'"

    conn = _connect()
    _ensure_schema(conn)

    row = conn.execute(
        "SELECT * FROM paper_trades WHERE id = ?", (trade_id,)
    ).fetchone()

    if not row:
        conn.close()
        return f"Error: trade #{trade_id} not found"
    if row["settled"]:
        conn.close()
        return f"Error: trade #{trade_id} already settled ({row['outcome']})"

    shares = row["amount"] / row["entry_price"]

    if outcome == "WIN":
        payout = shares * 1.0  # each share pays $1 on win
        pnl = payout - row["amount"]
    else:
        pnl = -row["amount"]

    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """
        UPDATE paper_trades
        SET settled = 1, outcome = ?, pnl = ?, settled_at = ?, current_price = ?
        WHERE id = ?
        """,
        (outcome, pnl, now, 1.0 if outcome == "WIN" else 0.0, trade_id),
    )
    conn.commit()
    conn.close()

    return (
        f"Trade #{trade_id} settled: {outcome}\n"
        f"Side: {row['side']} | Entry: {row['entry_price']:.2f}\n"
        f"Invested: ${row['amount']:.2f} | P&L: ${pnl:+.2f}"
    )


def paper_history() -> str:
    """Full trade history with win rate and total P&L.

    Returns:
        Formatted trade log with aggregate statistics.
    """
    conn = _connect()
    _ensure_schema(conn)

    rows = conn.execute(
        "SELECT * FROM paper_trades ORDER BY created_at DESC"
    ).fetchall()
    conn.close()

    if not rows:
        return "No paper trades yet."

    lines = ["Paper Trade History", "=" * 60]

    total_trades = len(rows)
    settled_trades = [r for r in rows if r["settled"]]
    wins = sum(1 for r in settled_trades if r["outcome"] == "WIN")
    losses = sum(1 for r in settled_trades if r["outcome"] == "LOSE")
    total_pnl = sum(r["pnl"] for r in settled_trades if r["pnl"] is not None)
    open_count = total_trades - len(settled_trades)

    for r in rows:
        status = r["outcome"] if r["settled"] else "OPEN"
        pnl_str = f"${r['pnl']:+.2f}" if r["pnl"] is not None else "—"
        lines.append(
            f"#{r['id']} [{status}] {r['side']} {r['question'] or r['market_id']} "
            f"| ${r['amount']:.2f} @ {r['entry_price']:.2f} | P&L: {pnl_str}"
        )

    lines.append("=" * 60)
    win_rate = (wins / len(settled_trades) * 100) if settled_trades else 0
    lines.append(
        f"Total: {total_trades} trades | "
        f"Settled: {len(settled_trades)} (W:{wins} L:{losses}) | "
        f"Open: {open_count}"
    )
    lines.append(f"Win Rate: {win_rate:.0f}% | Total P&L: ${total_pnl:+.2f}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Live CLOB API helpers
# ---------------------------------------------------------------------------

def get_orderbook(token_id: str) -> str:
    """Fetch the current orderbook (bids + asks) for a token from Polymarket CLOB.

    Args:
        token_id: The CLOB token ID for the outcome.

    Returns:
        Formatted orderbook with best bid/ask and spread.
    """
    import httpx

    url = f"{CLOB_BASE_URL}/book"
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(url, params={"token_id": token_id})
            resp.raise_for_status()
            book = resp.json()
    except httpx.HTTPStatusError as e:
        return f"Error fetching orderbook: HTTP {e.response.status_code}"
    except Exception as e:
        return f"Error fetching orderbook: {e}"

    bids = book.get("bids", [])
    asks = book.get("asks", [])

    best_bid = float(bids[0]["price"]) if bids else 0.0
    best_ask = float(asks[0]["price"]) if asks else 1.0
    spread = best_ask - best_bid
    midpoint = (best_bid + best_ask) / 2

    lines = [
        f"Orderbook for token {token_id}",
        f"Best Bid: {best_bid:.4f} | Best Ask: {best_ask:.4f}",
        f"Spread: {spread:.4f} ({spread / midpoint:.2%})" if midpoint > 0 else f"Spread: {spread:.4f}",
        f"Midpoint: {midpoint:.4f}",
        "",
        f"Top 5 Bids:",
    ]
    for b in bids[:5]:
        lines.append(f"  {float(b['price']):.4f}  —  size: {b.get('size', '?')}")

    lines.append(f"\nTop 5 Asks:")
    for a in asks[:5]:
        lines.append(f"  {float(a['price']):.4f}  —  size: {a.get('size', '?')}")

    return "\n".join(lines)


def get_midpoint(token_id: str) -> str:
    """Return the midpoint price for a token from the CLOB orderbook.

    Args:
        token_id: The CLOB token ID for the outcome.

    Returns:
        Midpoint price as a string.
    """
    import httpx

    url = f"{CLOB_BASE_URL}/midpoint"
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(url, params={"token_id": token_id})
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        return f"Error fetching midpoint: HTTP {e.response.status_code}"
    except Exception as e:
        return f"Error fetching midpoint: {e}"

    mid = data.get("mid", data.get("midpoint", "unknown"))
    return f"Midpoint for {token_id}: {mid}"


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def _demo():
    """Run a quick demo of the paper trading engine."""
    import tempfile
    global DEFAULT_DB_DIR, DEFAULT_DB_PATH

    # Use a temp directory so the demo doesn't pollute real data
    tmpdir = tempfile.mkdtemp(prefix="polymarket_paper_demo_")
    DEFAULT_DB_DIR = tmpdir
    DEFAULT_DB_PATH = os.path.join(tmpdir, "paper_trades.db")

    print("=" * 60)
    print("Polymarket Paper Trading Engine — Demo")
    print("=" * 60)

    # 1. Place some trades
    print("\n--- Placing trades ---")
    print(paper_trade(
        market_id="abc123",
        side="YES",
        amount=50,
        yes_price=0.65,
        question="Will BTC hit $150k by July 2026?",
        estimated_probability=0.75,
        bankroll=1000,
    ))
    print()
    print(paper_trade(
        market_id="def456",
        side="NO",
        amount=30,
        yes_price=0.80,
        question="Will the Fed cut rates in June 2026?",
    ))

    # 2. Check portfolio
    print("\n--- Portfolio ---")
    print(paper_portfolio())

    # 3. Settle one trade
    print("\n--- Settling trade #1 as WIN ---")
    print(paper_settle(1, "WIN"))

    print("\n--- Settling trade #2 as LOSE ---")
    print(paper_settle(2, "LOSE"))

    # 4. History
    print("\n--- Trade History ---")
    print(paper_history())

    # 5. Risk control demos
    print("\n--- Risk Controls ---")
    print("Oversized trade:")
    print(paper_trade("xyz", "YES", 200, 0.50, "Too big"))
    print()
    print("Invalid side:")
    print(paper_trade("xyz", "MAYBE", 10, 0.50))

    # Cleanup
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)

    print("\n" + "=" * 60)
    print("Demo complete. DB was temporary and has been cleaned up.")
    print("=" * 60)


if __name__ == "__main__":
    _demo()
