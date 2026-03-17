#!/usr/bin/env python3
"""Polymarket Autonomous Trading Agent.

A two-layer autonomous agent that scans Polymarket prediction markets for
mispriced opportunities and executes paper trades with full risk controls.

Architecture:
    Brain  -- market scanning, edge scoring, probability estimation
    Hands  -- paper/live trading, position sizing, risk management
    Alerts -- Telegram notifications with console fallback

Usage:
    python agent.py run          # Start the autonomous loop
    python agent.py scan         # One-shot scan, print edges
    python agent.py portfolio    # Show current positions
    python agent.py history      # Trade history with stats
    python agent.py settle ID    # Manually settle a trade (WIN/LOSE)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def _setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure structured logging and return the root agent logger."""
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(format=LOG_FORMAT, datefmt=LOG_DATE_FMT, level=numeric)
    return logging.getLogger("polymarket-agent")


log = _setup_logging(os.environ.get("LOG_LEVEL", "INFO"))


# ---------------------------------------------------------------------------
# Configuration (all from environment, sane defaults)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Config:
    """Immutable agent configuration loaded from environment variables."""

    scan_interval: int = int(os.environ.get("SCAN_INTERVAL", "900"))
    max_trade_size: float = float(os.environ.get("MAX_TRADE_SIZE", "100"))
    daily_loss_limit: float = float(os.environ.get("DAILY_LOSS_LIMIT", "500"))
    max_positions: int = int(os.environ.get("MAX_POSITIONS", "10"))
    min_edge: float = float(os.environ.get("MIN_EDGE", "0.05"))
    min_volume: float = float(os.environ.get("MIN_VOLUME", "10000"))
    min_liquidity: float = float(os.environ.get("MIN_LIQUIDITY", "5000"))
    confidence_threshold: float = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.6"))
    bankroll: float = float(os.environ.get("BANKROLL", "1000"))
    paper_mode: bool = os.environ.get("PAPER_MODE", "true").lower() in ("true", "1", "yes")
    telegram_bot_token: Optional[str] = os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = os.environ.get("TELEGRAM_CHAT_ID")
    db_dir: str = os.environ.get("AGENT_DB_DIR", os.path.expanduser("~/.polymarket-agent"))

    @property
    def db_path(self) -> str:
        return os.path.join(self.db_dir, "trades.db")

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    def log_summary(self) -> None:
        log.info("Configuration loaded:")
        log.info("  Scan interval:    %ds (%dm)", self.scan_interval, self.scan_interval // 60)
        log.info("  Max trade size:   $%.0f", self.max_trade_size)
        log.info("  Daily loss limit: $%.0f", self.daily_loss_limit)
        log.info("  Max positions:    %d", self.max_positions)
        log.info("  Min edge:         %.1f%%", self.min_edge * 100)
        log.info("  Min volume:       $%s", f"{self.min_volume:,.0f}")
        log.info("  Min liquidity:    $%s", f"{self.min_liquidity:,.0f}")
        log.info("  Bankroll:         $%s", f"{self.bankroll:,.0f}")
        log.info("  Paper mode:       %s", self.paper_mode)
        log.info("  Telegram:         %s", "enabled" if self.telegram_enabled else "disabled")
        log.info("  DB path:          %s", self.db_path)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GAMMA_URL = "https://gamma-api.polymarket.com/markets"
CLOB_BASE_URL = "https://clob.polymarket.com"
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

VERSION = "1.0.0"
USER_AGENT = f"polymarket-agent/{VERSION}"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class MarketEdge:
    """A scored market opportunity."""

    question: str
    condition_id: str
    yes_price: float
    estimated_prob: float
    side: str  # "YES" or "NO"
    edge: float
    kelly_fraction: float
    confidence: float  # 0.0 - 1.0
    confidence_label: str
    volume: float
    liquidity: float
    suggested_size: float = 0.0


@dataclass
class Trade:
    """Represents a paper or live trade."""

    id: Optional[int] = None
    market_id: str = ""
    question: str = ""
    side: str = ""
    amount: float = 0.0
    entry_price: float = 0.0
    current_price: float = 0.0
    estimated_prob: float = 0.0
    edge_at_entry: float = 0.0
    kelly_at_entry: float = 0.0
    settled: bool = False
    outcome: Optional[str] = None
    pnl: Optional[float] = None
    created_at: str = ""
    settled_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Database layer
# ---------------------------------------------------------------------------

class TradeStore:
    """SQLite-backed trade storage with schema migration."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        Path(os.path.dirname(db_path)).mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _ensure_schema(self) -> None:
        conn = self._connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    market_id       TEXT    NOT NULL,
                    question        TEXT    NOT NULL DEFAULT '',
                    side            TEXT    NOT NULL CHECK(side IN ('YES','NO')),
                    amount          REAL    NOT NULL,
                    entry_price     REAL    NOT NULL,
                    current_price   REAL    NOT NULL,
                    estimated_prob  REAL    NOT NULL DEFAULT 0,
                    edge_at_entry   REAL    NOT NULL DEFAULT 0,
                    kelly_at_entry  REAL    NOT NULL DEFAULT 0,
                    settled         INTEGER NOT NULL DEFAULT 0,
                    outcome         TEXT    DEFAULT NULL,
                    pnl             REAL    DEFAULT NULL,
                    created_at      TEXT    NOT NULL,
                    settled_at      TEXT    DEFAULT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scan_log (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    scanned_at      TEXT    NOT NULL,
                    markets_scanned INTEGER NOT NULL DEFAULT 0,
                    edges_found     INTEGER NOT NULL DEFAULT 0,
                    trades_placed   INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def insert_trade(self, trade: Trade) -> int:
        conn = self._connect()
        try:
            cursor = conn.execute("""
                INSERT INTO trades
                    (market_id, question, side, amount, entry_price, current_price,
                     estimated_prob, edge_at_entry, kelly_at_entry, settled, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            """, (
                trade.market_id, trade.question, trade.side, trade.amount,
                trade.entry_price, trade.current_price, trade.estimated_prob,
                trade.edge_at_entry, trade.kelly_at_entry, trade.created_at,
            ))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_open_positions(self) -> list[dict]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM trades WHERE settled = 0 ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_open_position_count(self) -> int:
        conn = self._connect()
        try:
            row = conn.execute("SELECT COUNT(*) as cnt FROM trades WHERE settled = 0").fetchone()
            return row["cnt"]
        finally:
            conn.close()

    def get_daily_exposure(self) -> float:
        """Total dollar amount of trades opened today (settled or not)."""
        conn = self._connect()
        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            row = conn.execute("""
                SELECT COALESCE(SUM(amount), 0) AS total
                FROM trades WHERE created_at LIKE ? || '%'
            """, (today,)).fetchone()
            return row["total"]
        finally:
            conn.close()

    def get_daily_pnl(self) -> float:
        """Realised P&L for today."""
        conn = self._connect()
        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            row = conn.execute("""
                SELECT COALESCE(SUM(pnl), 0) AS total
                FROM trades WHERE settled = 1 AND settled_at LIKE ? || '%'
            """, (today,)).fetchone()
            return row["total"]
        finally:
            conn.close()

    def has_open_position_for(self, market_id: str) -> bool:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM trades WHERE market_id = ? AND settled = 0",
                (market_id,),
            ).fetchone()
            return row["cnt"] > 0
        finally:
            conn.close()

    def settle_trade(self, trade_id: int, outcome: str) -> Optional[dict]:
        outcome = outcome.upper()
        if outcome not in ("WIN", "LOSE"):
            return None

        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
            if not row or row["settled"]:
                return None

            shares = row["amount"] / row["entry_price"]
            if outcome == "WIN":
                pnl = shares - row["amount"]
            else:
                pnl = -row["amount"]

            now = datetime.now(timezone.utc).isoformat()
            final_price = 1.0 if outcome == "WIN" else 0.0

            conn.execute("""
                UPDATE trades
                SET settled = 1, outcome = ?, pnl = ?, settled_at = ?, current_price = ?
                WHERE id = ?
            """, (outcome, pnl, now, final_price, trade_id))
            conn.commit()

            result = dict(row)
            result["pnl"] = pnl
            result["outcome"] = outcome
            return result
        finally:
            conn.close()

    def get_all_trades(self) -> list[dict]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM trades ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def log_scan(self, markets_scanned: int, edges_found: int, trades_placed: int) -> None:
        conn = self._connect()
        try:
            conn.execute("""
                INSERT INTO scan_log (scanned_at, markets_scanned, edges_found, trades_placed)
                VALUES (?, ?, ?, ?)
            """, (datetime.now(timezone.utc).isoformat(), markets_scanned, edges_found, trades_placed))
            conn.commit()
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Brain layer -- market scanning and edge scoring
# ---------------------------------------------------------------------------

class Brain:
    """Scans markets and scores them for trading edge."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._client = httpx.Client(
            timeout=20,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def fetch_active_markets(self) -> list[dict]:
        """Fetch all active markets from Gamma API."""
        all_markets = []
        offset = 0
        limit = 200

        while True:
            try:
                resp = self._client.get(GAMMA_URL, params={
                    "limit": limit,
                    "offset": offset,
                    "active": "true",
                    "closed": "false",
                })
                resp.raise_for_status()
                batch = resp.json()
            except httpx.HTTPStatusError as e:
                log.error("Gamma API HTTP error: %s", e)
                break
            except httpx.RequestError as e:
                log.error("Gamma API request error: %s", e)
                break
            except json.JSONDecodeError as e:
                log.error("Gamma API JSON decode error: %s", e)
                break

            if not batch:
                break

            all_markets.extend(batch)

            if len(batch) < limit:
                break

            offset += limit

        log.info("Fetched %d active markets from Gamma API", len(all_markets))
        return all_markets

    def extract_yes_price(self, market: dict) -> Optional[float]:
        """Extract the YES price from market data."""
        outcome_prices = market.get("outcomePrices", [])
        if isinstance(outcome_prices, str):
            try:
                outcome_prices = json.loads(outcome_prices)
            except (json.JSONDecodeError, TypeError):
                outcome_prices = []

        if len(outcome_prices) >= 2:
            try:
                y = float(outcome_prices[0])
                if 0 < y < 1:
                    return y
                n = float(outcome_prices[1])
                if 0 < n < 1:
                    return n
            except (ValueError, TypeError):
                pass

        # Fallback: tokens array
        for token in market.get("tokens", []):
            outcome = token.get("outcome", "").lower()
            price = token.get("price")
            if price and outcome in ("yes", "true", "1"):
                try:
                    return float(price)
                except (ValueError, TypeError):
                    pass

        return None

    def estimate_true_probability(self, market: dict, yes_price: float) -> tuple[float, float, str]:
        """Estimate true probability using multi-signal heuristics.

        Returns:
            (estimated_prob, confidence_score, confidence_label)
            confidence_score is 0.0-1.0 for threshold filtering.
        """
        volume = float(market.get("volume", 0))
        liquidity = float(market.get("liquidity", 0))

        # Base: start from market price
        est = yes_price

        # Signal 1: Volume-based efficiency adjustment
        # Low volume markets have less price discovery, pull toward 50%
        if volume < 5_000:
            vol_weight = 0.30
            confidence = 0.3
            label = "LOW"
        elif volume < 25_000:
            vol_weight = 0.20
            confidence = 0.45
            label = "LOW-MEDIUM"
        elif volume < 100_000:
            vol_weight = 0.12
            confidence = 0.6
            label = "MEDIUM"
        elif volume < 500_000:
            vol_weight = 0.06
            confidence = 0.75
            label = "MEDIUM-HIGH"
        else:
            vol_weight = 0.02
            confidence = 0.85
            label = "HIGH"

        est = yes_price * (1 - vol_weight) + 0.5 * vol_weight

        # Signal 2: Liquidity ratio -- thin books have stale/unreliable prices
        if volume > 0:
            liq_ratio = liquidity / volume
            if liq_ratio < 0.005:
                est = est * 0.85 + 0.5 * 0.15
                confidence *= 0.6
                label = "LOW"
            elif liq_ratio < 0.02:
                est = est * 0.92 + 0.5 * 0.08
                confidence *= 0.8

        # Signal 3: Mean reversion for extreme prices in thin markets
        if volume < 200_000:
            if yes_price > 0.93:
                reversion = min(0.04, (yes_price - 0.90) * 0.5)
                est = min(est, est - reversion)
            elif yes_price < 0.07:
                reversion = min(0.04, (0.10 - yes_price) * 0.5)
                est = max(est, est + reversion)

        # Signal 4: Price-liquidity mismatch
        # If price is extreme but liquidity is very low, the price may be unreliable
        if liquidity < 2_000 and (yes_price > 0.85 or yes_price < 0.15):
            confidence *= 0.5
            label = "LOW"

        # Clamp probability to valid range
        est = max(0.01, min(0.99, est))

        return est, confidence, label

    def score_market(self, market: dict) -> Optional[MarketEdge]:
        """Score a single market for trading edge.

        Returns MarketEdge if there is a tradeable signal, None otherwise.
        """
        volume = float(market.get("volume", 0))
        liquidity = float(market.get("liquidity", 0))

        # Pre-filter
        if volume < self._config.min_volume:
            return None
        if liquidity < self._config.min_liquidity:
            return None

        yes_price = self.extract_yes_price(market)
        if yes_price is None or yes_price <= 0.02 or yes_price >= 0.98:
            return None

        est_prob, confidence, conf_label = self.estimate_true_probability(market, yes_price)

        # Check confidence threshold
        if confidence < self._config.confidence_threshold:
            return None

        # Determine best side
        yes_edge = est_prob - yes_price
        no_edge = (1 - est_prob) - (1 - yes_price)

        if yes_edge >= self._config.min_edge:
            side = "YES"
            edge = yes_edge
            bet_price = yes_price
            bet_prob = est_prob
        elif (-yes_edge) >= self._config.min_edge:
            # NO side has edge
            side = "NO"
            edge = abs(yes_edge)
            bet_price = 1 - yes_price
            bet_prob = 1 - est_prob
        else:
            return None

        # Kelly sizing
        kelly = self._kelly_fraction(bet_prob, bet_price)
        suggested_size = min(
            self._config.bankroll * kelly,
            self._config.max_trade_size,
        )

        if suggested_size < 1.0:
            return None  # Not worth the trade

        # Use the best available unique identifier
        market_id = (
            market.get("conditionId")
            or market.get("condition_id")
            or market.get("slug")
            or str(market.get("id", ""))
        )

        return MarketEdge(
            question=market.get("question", "Unknown market"),
            condition_id=market_id,
            yes_price=yes_price,
            estimated_prob=est_prob,
            side=side,
            edge=edge,
            kelly_fraction=kelly,
            confidence=confidence,
            confidence_label=conf_label,
            volume=volume,
            liquidity=liquidity,
            suggested_size=round(suggested_size, 2),
        )

    def scan_all(self) -> list[MarketEdge]:
        """Fetch and score all active markets. Returns edges sorted by score."""
        markets = self.fetch_active_markets()
        edges = []

        for m in markets:
            edge = self.score_market(m)
            if edge is not None:
                edges.append(edge)

        # Sort by edge * confidence (composite score)
        edges.sort(key=lambda e: e.edge * e.confidence, reverse=True)

        log.info(
            "Scan complete: %d markets scanned, %d edges found",
            len(markets), len(edges),
        )
        return edges

    @staticmethod
    def _kelly_fraction(prob: float, price: float) -> float:
        """Quarter-Kelly fraction for a bet."""
        if price <= 0 or price >= 1 or prob <= 0 or prob >= 1:
            return 0.0
        edge = prob - price
        if edge <= 0:
            return 0.0
        kelly = (prob * (1 - price) - (1 - prob) * price) / (1 - price)
        return max(0.0, kelly / 4.0)


# ---------------------------------------------------------------------------
# Hands layer -- trading execution and risk management
# ---------------------------------------------------------------------------

class Hands:
    """Executes trades with full risk controls."""

    def __init__(self, config: Config, store: TradeStore) -> None:
        self._config = config
        self._store = store

    def check_risk(self, edge: MarketEdge) -> tuple[bool, str]:
        """Run all risk checks. Returns (passed, reason)."""
        # Check max positions
        open_count = self._store.get_open_position_count()
        if open_count >= self._config.max_positions:
            return False, f"Max positions reached ({open_count}/{self._config.max_positions})"

        # Check daily exposure
        daily_exposure = self._store.get_daily_exposure()
        if daily_exposure + edge.suggested_size > self._config.daily_loss_limit:
            return False, (
                f"Daily exposure limit: ${daily_exposure:.0f} + ${edge.suggested_size:.0f} "
                f"> ${self._config.daily_loss_limit:.0f}"
            )

        # Check daily P&L (stop loss)
        daily_pnl = self._store.get_daily_pnl()
        if daily_pnl <= -self._config.daily_loss_limit:
            return False, f"Daily loss limit hit: ${daily_pnl:+.2f}"

        # Check duplicate position
        if self._store.has_open_position_for(edge.condition_id):
            return False, f"Already have open position in {edge.condition_id[:12]}..."

        # Check trade size
        if edge.suggested_size > self._config.max_trade_size:
            return False, f"Trade size ${edge.suggested_size:.0f} > max ${self._config.max_trade_size:.0f}"

        return True, "All risk checks passed"

    def execute_trade(self, edge: MarketEdge) -> Optional[Trade]:
        """Place a paper trade (or live trade if configured)."""
        passed, reason = self.check_risk(edge)
        if not passed:
            log.warning("Risk check failed for %s: %s", edge.condition_id[:12], reason)
            return None

        bet_price = edge.yes_price if edge.side == "YES" else (1 - edge.yes_price)

        trade = Trade(
            market_id=edge.condition_id,
            question=edge.question,
            side=edge.side,
            amount=edge.suggested_size,
            entry_price=bet_price,
            current_price=bet_price,
            estimated_prob=edge.estimated_prob,
            edge_at_entry=edge.edge,
            kelly_at_entry=edge.kelly_fraction,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        if self._config.paper_mode:
            trade_id = self._store.insert_trade(trade)
            trade.id = trade_id
            log.info(
                "Paper trade #%d placed: %s %s @ %.2f ($%.2f) | edge: %.1f%%",
                trade_id, edge.side, edge.question[:50],
                bet_price, edge.suggested_size, edge.edge * 100,
            )
            return trade
        else:
            # Live trading placeholder -- requires CLOB API integration
            log.error("Live trading not yet implemented. Set PAPER_MODE=true.")
            return None


# ---------------------------------------------------------------------------
# Alert layer -- Telegram + console
# ---------------------------------------------------------------------------

class Alerter:
    """Sends alerts via Telegram with console fallback."""

    def __init__(self, config: Config) -> None:
        self._config = config

    def send(self, message: str, level: str = "INFO") -> None:
        """Send an alert. Tries Telegram first, falls back to console."""
        # Always log to console
        if level == "ERROR":
            log.error("[ALERT] %s", message)
        elif level == "WARNING":
            log.warning("[ALERT] %s", message)
        else:
            log.info("[ALERT] %s", message)

        # Send via Telegram if configured
        if self._config.telegram_enabled:
            self._send_telegram(message)

    def _send_telegram(self, message: str) -> None:
        """Send a message via Telegram Bot API."""
        # Truncate for Telegram's 4096 char limit
        if len(message) > 4000:
            message = message[:3950] + "\n\n... (truncated)"

        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(
                    TELEGRAM_API.format(token=self._config.telegram_bot_token),
                    json={
                        "chat_id": self._config.telegram_chat_id,
                        "text": message,
                        "parse_mode": "Markdown",
                        "disable_web_page_preview": True,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                if not data.get("ok"):
                    log.warning("Telegram API returned error: %s", data)
        except Exception as e:
            log.warning("Telegram send failed (non-fatal): %s", e)

    def format_edge_alert(self, edge: MarketEdge) -> str:
        """Format a MarketEdge as an alert message."""
        return (
            f"*Edge Found*\n"
            f"Market: {edge.question}\n"
            f"Signal: BET {edge.side} | Edge: +{edge.edge:.1%}\n"
            f"Market YES: {edge.yes_price:.0%} | Est. True: {edge.estimated_prob:.0%}\n"
            f"Quarter-Kelly: {edge.kelly_fraction:.1%} | Size: ${edge.suggested_size:.0f}\n"
            f"Volume: ${edge.volume:,.0f} | Liquidity: ${edge.liquidity:,.0f}\n"
            f"Confidence: {edge.confidence_label} ({edge.confidence:.0%})"
        )

    def format_trade_alert(self, trade: Trade) -> str:
        """Format a Trade as an alert message."""
        shares = trade.amount / trade.entry_price if trade.entry_price > 0 else 0
        return (
            f"*{'Paper ' if True else ''}Trade Placed*\n"
            f"#{trade.id} | {trade.side} {trade.question[:60]}\n"
            f"Entry: {trade.entry_price:.2f} | Amount: ${trade.amount:.2f}\n"
            f"Shares: {shares:.2f} | Potential payout: ${shares:.2f}\n"
            f"Edge: {trade.edge_at_entry:.1%} | Kelly: {trade.kelly_at_entry:.1%}"
        )

    def format_scan_summary(
        self, edges: list[MarketEdge], trades: list[Trade], scan_duration: float
    ) -> str:
        """Format a scan cycle summary."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            f"*Scan Summary* -- {now}",
            f"Duration: {scan_duration:.1f}s",
            f"Edges found: {len(edges)}",
            f"Trades placed: {len(trades)}",
        ]

        if edges:
            lines.append("\n*Top edges:*")
            for i, e in enumerate(edges[:5], 1):
                lines.append(
                    f"  {i}. {e.side} {e.question[:45]}... +{e.edge:.1%}"
                )

        if trades:
            lines.append("\n*Trades:*")
            for t in trades:
                lines.append(
                    f"  #{t.id} {t.side} ${t.amount:.0f} @ {t.entry_price:.2f}"
                )

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Agent -- the main autonomous loop
# ---------------------------------------------------------------------------

class Agent:
    """Autonomous Polymarket trading agent."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._store = TradeStore(config.db_path)
        self._brain = Brain(config)
        self._hands = Hands(config, self._store)
        self._alerter = Alerter(config)
        self._running = False

    def close(self) -> None:
        self._brain.close()

    def scan(self) -> list[MarketEdge]:
        """Run a single market scan and return edges."""
        return self._brain.scan_all()

    def run_cycle(self) -> tuple[list[MarketEdge], list[Trade]]:
        """Execute one full scan-evaluate-trade cycle."""
        start = time.monotonic()

        # 1. Scan
        edges = self._brain.scan_all()

        # 2. Execute trades for qualifying edges
        trades_placed = []
        for edge in edges:
            trade = self._hands.execute_trade(edge)
            if trade is not None:
                trades_placed.append(trade)
                self._alerter.send(self._alerter.format_trade_alert(trade))

        elapsed = time.monotonic() - start

        # 3. Log scan
        self._store.log_scan(
            markets_scanned=0,  # We don't track total from here
            edges_found=len(edges),
            trades_placed=len(trades_placed),
        )

        # 4. Send summary
        summary = self._alerter.format_scan_summary(edges, trades_placed, elapsed)
        self._alerter.send(summary)

        return edges, trades_placed

    def run_loop(self) -> None:
        """Run the agent in a continuous loop with graceful shutdown."""
        self._running = True

        # Register signal handlers for graceful shutdown
        def _shutdown(signum, frame):
            signame = signal.Signals(signum).name
            log.info("Received %s, shutting down gracefully...", signame)
            self._running = False

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        mode = "PAPER" if self._config.paper_mode else "LIVE"
        log.info("=" * 60)
        log.info("Polymarket Agent v%s starting (%s MODE)", VERSION, mode)
        log.info("=" * 60)
        self._config.log_summary()

        startup_msg = (
            f"*Polymarket Agent v{VERSION} started*\n"
            f"Mode: {mode}\n"
            f"Interval: {self._config.scan_interval}s\n"
            f"Bankroll: ${self._config.bankroll:,.0f}\n"
            f"Risk: max ${self._config.max_trade_size}/trade, "
            f"${self._config.daily_loss_limit}/day, "
            f"{self._config.max_positions} positions"
        )
        self._alerter.send(startup_msg)

        cycle = 0
        while self._running:
            cycle += 1
            log.info("--- Cycle %d ---", cycle)

            try:
                edges, trades = self.run_cycle()
                log.info(
                    "Cycle %d complete: %d edges, %d trades",
                    cycle, len(edges), len(trades),
                )
            except Exception as e:
                log.exception("Error in cycle %d: %s", cycle, e)
                self._alerter.send(f"*Error in cycle {cycle}*: {e}", level="ERROR")

            # Sleep in small increments for responsive shutdown
            if self._running:
                log.info("Sleeping %ds until next scan...", self._config.scan_interval)
                sleep_end = time.monotonic() + self._config.scan_interval
                while self._running and time.monotonic() < sleep_end:
                    time.sleep(1)

        self.close()
        log.info("Agent shut down cleanly.")
        self._alerter.send("*Polymarket Agent stopped.*")


# ---------------------------------------------------------------------------
# CLI formatters
# ---------------------------------------------------------------------------

def format_edges_table(edges: list[MarketEdge]) -> str:
    """Format edges for terminal display."""
    if not edges:
        return "No edges found. Markets appear efficient at current thresholds."

    lines = [
        f"Found {len(edges)} edge opportunities",
        "=" * 78,
    ]

    for i, e in enumerate(edges, 1):
        score = e.edge * e.confidence
        lines.append(f"{i}. {e.question}")
        lines.append(f"   ID: {e.condition_id}")
        lines.append(
            f"   Market: YES {e.yes_price:.0%} | Est. True: {e.estimated_prob:.0%} "
            f"| Edge: +{e.edge:.1%}"
        )
        lines.append(
            f"   Signal: BET {e.side} | Size: ${e.suggested_size:.0f} "
            f"(Kelly {e.kelly_fraction:.1%})"
        )
        lines.append(
            f"   Volume: ${e.volume:,.0f} | Liquidity: ${e.liquidity:,.0f} "
            f"| Confidence: {e.confidence_label} ({e.confidence:.0%})"
        )
        lines.append(f"   Score: {score:.4f}")
        lines.append("")

    return "\n".join(lines)


def format_portfolio(positions: list[dict]) -> str:
    """Format open positions for terminal display."""
    if not positions:
        return "No open positions."

    lines = ["Open Positions", "=" * 70]

    total_invested = 0.0
    total_current = 0.0

    for r in positions:
        shares = r["amount"] / r["entry_price"] if r["entry_price"] > 0 else 0
        current_value = shares * r["current_price"]
        unrealised = current_value - r["amount"]
        total_invested += r["amount"]
        total_current += current_value

        pct = (unrealised / r["amount"] * 100) if r["amount"] > 0 else 0

        lines.append(
            f"#{r['id']} | {r['side']} {r['question'][:55] or r['market_id'][:20]}"
        )
        lines.append(
            f"   Entry: {r['entry_price']:.4f} | Current: {r['current_price']:.4f}"
        )
        lines.append(
            f"   Amount: ${r['amount']:.2f} | Value: ${current_value:.2f} | "
            f"P&L: ${unrealised:+.2f} ({pct:+.0f}%)"
        )
        lines.append(
            f"   Edge at entry: {r['edge_at_entry']:.1%} | "
            f"Opened: {r['created_at'][:19]}"
        )
        lines.append("")

    total_pnl = total_current - total_invested
    lines.append("=" * 70)
    lines.append(
        f"Total invested: ${total_invested:.2f} | "
        f"Current value: ${total_current:.2f} | "
        f"Unrealised P&L: ${total_pnl:+.2f}"
    )

    return "\n".join(lines)


def format_history(trades: list[dict]) -> str:
    """Format trade history for terminal display."""
    if not trades:
        return "No trades yet."

    lines = ["Trade History", "=" * 70]

    settled = [t for t in trades if t["settled"]]
    wins = sum(1 for t in settled if t["outcome"] == "WIN")
    losses = sum(1 for t in settled if t["outcome"] == "LOSE")
    total_pnl = sum(t["pnl"] for t in settled if t["pnl"] is not None)
    open_count = len(trades) - len(settled)

    for r in trades:
        status = r["outcome"] if r["settled"] else "OPEN"
        pnl_str = f"${r['pnl']:+.2f}" if r["pnl"] is not None else "---"
        lines.append(
            f"#{r['id']} [{status:4s}] {r['side']} "
            f"{r['question'][:40] or r['market_id'][:15]} "
            f"| ${r['amount']:.2f} @ {r['entry_price']:.4f} "
            f"| Edge: {r['edge_at_entry']:.1%} | P&L: {pnl_str}"
        )

    lines.append("=" * 70)
    win_rate = (wins / len(settled) * 100) if settled else 0
    lines.append(
        f"Total: {len(trades)} | "
        f"Settled: {len(settled)} (W:{wins} L:{losses}) | "
        f"Open: {open_count}"
    )
    lines.append(f"Win Rate: {win_rate:.0f}% | Total P&L: ${total_pnl:+.2f}")

    # Edge stats
    if settled:
        avg_edge = sum(t["edge_at_entry"] for t in settled) / len(settled)
        lines.append(f"Avg Edge at Entry: {avg_edge:.1%}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="polymarket-agent",
        description="Autonomous Polymarket prediction market trading agent.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  SCAN_INTERVAL       Seconds between scans (default: 900)
  MAX_TRADE_SIZE      Max dollars per trade (default: 100)
  DAILY_LOSS_LIMIT    Max daily exposure in dollars (default: 500)
  MAX_POSITIONS       Max concurrent open positions (default: 10)
  MIN_EDGE            Min edge to trade, decimal (default: 0.05)
  MIN_VOLUME          Min market volume in USD (default: 10000)
  MIN_LIQUIDITY       Min market liquidity in USD (default: 5000)
  CONFIDENCE_THRESHOLD Min confidence score 0-1 (default: 0.6)
  BANKROLL            Total bankroll for Kelly sizing (default: 1000)
  PAPER_MODE          true/false (default: true)
  TELEGRAM_BOT_TOKEN  Telegram bot token for alerts
  TELEGRAM_CHAT_ID    Telegram chat ID for alerts
  LOG_LEVEL           Logging level (default: INFO)

Examples:
  python agent.py run                    Start the autonomous agent
  python agent.py scan                   One-shot scan for edges
  python agent.py portfolio              Show open positions
  python agent.py history                Full trade history
  python agent.py settle 42 WIN          Settle trade #42 as a win
  MIN_EDGE=0.03 python agent.py scan     Scan with lower edge threshold
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Agent command")

    # run
    subparsers.add_parser("run", help="Start the autonomous trading loop")

    # scan
    subparsers.add_parser("scan", help="One-shot scan for edge opportunities")

    # portfolio
    subparsers.add_parser("portfolio", help="Show current open positions")

    # history
    subparsers.add_parser("history", help="Full trade history with statistics")

    # settle
    settle_parser = subparsers.add_parser("settle", help="Manually settle a trade")
    settle_parser.add_argument("trade_id", type=int, help="Trade ID to settle")
    settle_parser.add_argument(
        "outcome",
        choices=["WIN", "LOSE", "win", "lose"],
        help="Trade outcome (WIN or LOSE)",
    )

    # version
    subparsers.add_parser("version", help="Show agent version")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    config = Config()

    if args.command == "version":
        print(f"polymarket-agent v{VERSION}")
        return 0

    if args.command == "run":
        agent = Agent(config)
        try:
            agent.run_loop()
        finally:
            agent.close()
        return 0

    if args.command == "scan":
        brain = Brain(config)
        try:
            edges = brain.scan_all()
            print(format_edges_table(edges))
        finally:
            brain.close()
        return 0

    if args.command == "portfolio":
        store = TradeStore(config.db_path)
        positions = store.get_open_positions()
        print(format_portfolio(positions))
        return 0

    if args.command == "history":
        store = TradeStore(config.db_path)
        trades = store.get_all_trades()
        print(format_history(trades))
        return 0

    if args.command == "settle":
        store = TradeStore(config.db_path)
        result = store.settle_trade(args.trade_id, args.outcome.upper())
        if result is None:
            print(f"Error: trade #{args.trade_id} not found or already settled.")
            return 1

        pnl = result["pnl"]
        print(f"Trade #{args.trade_id} settled: {args.outcome.upper()}")
        print(f"  Side: {result['side']} | Entry: {result['entry_price']:.4f}")
        print(f"  Amount: ${result['amount']:.2f} | P&L: ${pnl:+.2f}")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
