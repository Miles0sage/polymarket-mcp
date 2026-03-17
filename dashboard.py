"""Polymarket Agent Dashboard — FastAPI web UI for monitoring paper trades and edges.

Run standalone:
    python dashboard.py          # starts on port 8501
    python dashboard.py --port 9000
"""

import math
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DB_DIR = os.path.expanduser("~/.polymarket-mcp")
DB_PATH = os.path.join(DB_DIR, "paper_trades.db")

app = FastAPI(title="Polymarket Agent Dashboard", version="1.0.0")


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    Path(DB_DIR).mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
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
    return conn


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/portfolio")
def api_portfolio():
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM paper_trades WHERE settled = 0 ORDER BY created_at DESC"
    ).fetchall()
    conn.close()

    positions = []
    for r in rows:
        r = dict(r)
        shares = r["amount"] / r["entry_price"] if r["entry_price"] > 0 else 0
        current_value = shares * r["current_price"]
        unrealised_pnl = current_value - r["amount"]
        pnl_pct = (unrealised_pnl / r["amount"] * 100) if r["amount"] > 0 else 0

        # Age in human-readable form
        try:
            created = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
            age_seconds = (datetime.now(timezone.utc) - created).total_seconds()
            if age_seconds < 3600:
                age_str = f"{int(age_seconds // 60)}m"
            elif age_seconds < 86400:
                age_str = f"{age_seconds / 3600:.1f}h"
            else:
                age_str = f"{age_seconds / 86400:.1f}d"
        except Exception:
            age_str = "?"

        positions.append({
            "id": r["id"],
            "market_id": r["market_id"],
            "question": r["question"] or r["market_id"],
            "side": r["side"],
            "amount": r["amount"],
            "entry_price": r["entry_price"],
            "current_price": r["current_price"],
            "shares": round(shares, 4),
            "current_value": round(current_value, 2),
            "unrealised_pnl": round(unrealised_pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "age": age_str,
            "created_at": r["created_at"],
        })

    return JSONResponse(content={"positions": positions, "count": len(positions)})


@app.get("/api/history")
def api_history():
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM paper_trades ORDER BY created_at DESC LIMIT 100"
    ).fetchall()
    conn.close()

    trades = []
    for r in rows:
        r = dict(r)
        status = r["outcome"] if r["settled"] else "OPEN"
        trades.append({
            "id": r["id"],
            "question": r["question"] or r["market_id"],
            "side": r["side"],
            "amount": r["amount"],
            "entry_price": r["entry_price"],
            "current_price": r["current_price"],
            "status": status,
            "pnl": r["pnl"],
            "created_at": r["created_at"],
            "settled_at": r["settled_at"],
        })

    return JSONResponse(content={"trades": trades, "count": len(trades)})


@app.get("/api/stats")
def api_stats():
    conn = _connect()
    all_rows = conn.execute("SELECT * FROM paper_trades").fetchall()
    conn.close()

    total_trades = len(all_rows)
    settled = [dict(r) for r in all_rows if r["settled"]]
    open_positions = total_trades - len(settled)
    wins = sum(1 for r in settled if r["outcome"] == "WIN")
    losses = sum(1 for r in settled if r["outcome"] == "LOSE")
    win_rate = (wins / len(settled) * 100) if settled else 0

    realised_pnl = sum(r["pnl"] for r in settled if r["pnl"] is not None)

    # Unrealised P&L for open positions
    open_rows = [dict(r) for r in all_rows if not r["settled"]]
    unrealised_pnl = 0.0
    for r in open_rows:
        if r["entry_price"] > 0:
            shares = r["amount"] / r["entry_price"]
            unrealised_pnl += shares * r["current_price"] - r["amount"]

    total_pnl = realised_pnl + unrealised_pnl

    # Sharpe ratio (simplified: daily P&L std dev)
    sharpe = 0.0
    if len(settled) >= 2:
        pnls = [r["pnl"] for r in settled if r["pnl"] is not None]
        if pnls:
            mean_pnl = sum(pnls) / len(pnls)
            variance = sum((p - mean_pnl) ** 2 for p in pnls) / len(pnls)
            std_dev = math.sqrt(variance) if variance > 0 else 0
            sharpe = (mean_pnl / std_dev) if std_dev > 0 else 0

    return JSONResponse(content={
        "total_trades": total_trades,
        "open_positions": open_positions,
        "settled_trades": len(settled),
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 1),
        "realised_pnl": round(realised_pnl, 2),
        "unrealised_pnl": round(unrealised_pnl, 2),
        "total_pnl": round(total_pnl, 2),
        "sharpe_ratio": round(sharpe, 2),
    })


@app.get("/api/edges")
def api_edges():
    """Run the edge scanner and return results as structured JSON."""
    try:
        from tools_alerts import _fetch_markets, _extract_yes_price, _estimate_true_probability, _kelly_fraction
    except ImportError:
        # If running from a different cwd, add the project dir
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from tools_alerts import _fetch_markets, _extract_yes_price, _estimate_true_probability, _kelly_fraction

    min_edge = 0.05
    min_volume = 10000.0

    try:
        markets = _fetch_markets({
            "limit": 200,
            "active": "true",
            "closed": "false",
        })
    except Exception as e:
        return JSONResponse(content={"edges": [], "error": str(e)}, status_code=502)

    edges = []
    for m in markets:
        volume = float(m.get("volume", 0))
        if volume < min_volume:
            continue

        yes_price = _extract_yes_price(m)
        if yes_price is None or yes_price <= 0.01 or yes_price >= 0.99:
            continue

        est_prob, confidence = _estimate_true_probability(m, yes_price)
        yes_edge = est_prob - yes_price

        if abs(yes_edge) >= min_edge:
            side = "YES" if yes_edge > 0 else "NO"
            edge_val = abs(yes_edge)
            bet_price = yes_price if side == "YES" else (1 - yes_price)
            bet_prob = est_prob if side == "YES" else (1 - est_prob)
            kelly = _kelly_fraction(bet_prob, bet_price)

            edges.append({
                "question": m.get("question", "?"),
                "condition_id": m.get("condition_id", ""),
                "yes_price": round(yes_price, 4),
                "est_prob": round(est_prob, 4),
                "side": side,
                "edge": round(edge_val, 4),
                "kelly": round(kelly, 4),
                "confidence": confidence,
                "volume": round(volume, 0),
                "liquidity": round(float(m.get("liquidity", 0)), 0),
            })

    edges.sort(key=lambda x: x["edge"], reverse=True)
    return JSONResponse(content={"edges": edges, "count": len(edges)})


# ---------------------------------------------------------------------------
# Dashboard HTML
# ---------------------------------------------------------------------------

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Polymarket Agent</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
    background: #0d1117;
    color: #c9d1d9;
    min-height: 100vh;
  }
  a { color: #58a6ff; text-decoration: none; }
  .container { max-width: 1400px; margin: 0 auto; padding: 20px; }

  /* Header */
  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 0;
    border-bottom: 1px solid #21262d;
    margin-bottom: 24px;
  }
  .header h1 {
    font-size: 22px;
    font-weight: 600;
    color: #f0f6fc;
    letter-spacing: -0.5px;
  }
  .header h1 span { color: #58a6ff; }
  .status-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .status-badge.running { background: #0d3117; color: #3fb950; border: 1px solid #238636; }
  .status-badge.stopped { background: #3d1117; color: #f85149; border: 1px solid #da3633; }
  .status-dot {
    width: 8px; height: 8px; border-radius: 50%;
    animation: pulse 2s infinite;
  }
  .status-badge.running .status-dot { background: #3fb950; }
  .status-badge.stopped .status-dot { background: #f85149; animation: none; }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }
  .last-updated { font-size: 11px; color: #484f58; margin-top: 4px; }

  /* Stats row */
  .stats-row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
    margin-bottom: 28px;
  }
  .stat-card {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 8px;
    padding: 20px;
  }
  .stat-card .label {
    font-size: 12px;
    color: #8b949e;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 8px;
  }
  .stat-card .value {
    font-size: 28px;
    font-weight: 700;
    font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
    color: #f0f6fc;
  }
  .stat-card .sub {
    font-size: 12px;
    color: #8b949e;
    margin-top: 4px;
    font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
  }
  .positive { color: #3fb950 !important; }
  .negative { color: #f85149 !important; }
  .neutral { color: #8b949e !important; }

  /* Section */
  .section {
    margin-bottom: 28px;
  }
  .section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
  }
  .section-title {
    font-size: 15px;
    font-weight: 600;
    color: #f0f6fc;
  }
  .section-count {
    font-size: 12px;
    color: #8b949e;
    background: #21262d;
    padding: 2px 8px;
    border-radius: 10px;
  }

  /* Tables */
  .table-wrap {
    overflow-x: auto;
    border: 1px solid #21262d;
    border-radius: 8px;
    background: #161b22;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }
  thead th {
    background: #1c2128;
    padding: 10px 14px;
    text-align: left;
    font-weight: 600;
    color: #8b949e;
    text-transform: uppercase;
    font-size: 11px;
    letter-spacing: 0.5px;
    border-bottom: 1px solid #21262d;
    white-space: nowrap;
  }
  tbody td {
    padding: 10px 14px;
    border-bottom: 1px solid #21262d;
    white-space: nowrap;
  }
  tbody tr:last-child td { border-bottom: none; }
  tbody tr:hover { background: #1c2128; }
  .mono {
    font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
    font-size: 12px;
  }
  .pill {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
  }
  .pill-yes { background: #0d3117; color: #3fb950; }
  .pill-no { background: #3d1117; color: #f85149; }
  .pill-win { background: #0d3117; color: #3fb950; }
  .pill-lose { background: #3d1117; color: #f85149; }
  .pill-open { background: #1c2128; color: #8b949e; border: 1px solid #30363d; }
  .question-text {
    max-width: 350px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* Empty state */
  .empty {
    text-align: center;
    padding: 40px;
    color: #484f58;
    font-size: 14px;
  }

  /* Loading skeleton */
  .skeleton {
    background: linear-gradient(90deg, #21262d 25%, #30363d 50%, #21262d 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite;
    border-radius: 4px;
    height: 20px;
  }
  @keyframes shimmer {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
  }

  /* Footer */
  .footer {
    text-align: center;
    padding: 20px 0;
    font-size: 11px;
    color: #30363d;
    border-top: 1px solid #21262d;
    margin-top: 20px;
  }
</style>
</head>
<body>
<div class="container">

  <!-- Header -->
  <div class="header">
    <div>
      <h1><span>Polymarket</span> Agent</h1>
      <div class="last-updated" id="lastUpdated">Loading...</div>
    </div>
    <div id="statusBadge" class="status-badge stopped">
      <div class="status-dot"></div>
      <span>checking</span>
    </div>
  </div>

  <!-- Stats -->
  <div class="stats-row" id="statsRow">
    <div class="stat-card">
      <div class="label">Total P&L</div>
      <div class="value" id="statPnl">--</div>
      <div class="sub" id="statPnlSub"></div>
    </div>
    <div class="stat-card">
      <div class="label">Win Rate</div>
      <div class="value" id="statWinRate">--</div>
      <div class="sub" id="statWinRateSub"></div>
    </div>
    <div class="stat-card">
      <div class="label">Open Positions</div>
      <div class="value" id="statOpen">--</div>
      <div class="sub" id="statOpenSub"></div>
    </div>
    <div class="stat-card">
      <div class="label">Total Trades</div>
      <div class="value" id="statTotal">--</div>
      <div class="sub" id="statTotalSub"></div>
    </div>
  </div>

  <!-- Active Positions -->
  <div class="section">
    <div class="section-header">
      <div class="section-title">Active Positions</div>
      <div class="section-count" id="posCount">0</div>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Market</th>
            <th>Side</th>
            <th>Entry</th>
            <th>Current</th>
            <th>Amount</th>
            <th>P&L</th>
            <th>Age</th>
          </tr>
        </thead>
        <tbody id="positionsBody">
          <tr><td colspan="8" class="empty">Loading positions...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Edge Signals -->
  <div class="section">
    <div class="section-header">
      <div class="section-title">Edge Signals</div>
      <div class="section-count" id="edgeCount">0</div>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Market</th>
            <th>Mkt Price</th>
            <th>Est. Prob</th>
            <th>Side</th>
            <th>Edge</th>
            <th>Kelly</th>
            <th>Volume</th>
            <th>Confidence</th>
          </tr>
        </thead>
        <tbody id="edgesBody">
          <tr><td colspan="8" class="empty">Loading edges...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Trade History -->
  <div class="section">
    <div class="section-header">
      <div class="section-title">Trade History</div>
      <div class="section-count" id="historyCount">0</div>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Market</th>
            <th>Side</th>
            <th>Amount</th>
            <th>Entry</th>
            <th>Status</th>
            <th>P&L</th>
            <th>Date</th>
          </tr>
        </thead>
        <tbody id="historyBody">
          <tr><td colspan="8" class="empty">Loading history...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <div class="footer">
    Polymarket Agent Dashboard &middot; Auto-refreshes every 30s
  </div>
</div>

<script>
const $ = (id) => document.getElementById(id);

function pnlClass(v) {
  if (v > 0) return 'positive';
  if (v < 0) return 'negative';
  return 'neutral';
}

function fmtPnl(v) {
  if (v == null) return '--';
  const sign = v >= 0 ? '+' : '';
  return sign + '$' + v.toFixed(2);
}

function fmtPct(v) {
  if (v == null) return '--';
  return v.toFixed(1) + '%';
}

function fmtPrice(v) {
  if (v == null) return '--';
  return (v * 100).toFixed(1) + '¢';
}

function fmtMoney(v) {
  if (v == null) return '--';
  return '$' + Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 });
}

function fmtDate(iso) {
  if (!iso) return '--';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' ' +
           d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
  } catch { return iso.slice(0, 16); }
}

function sidePill(side) {
  const cls = side === 'YES' ? 'pill-yes' : 'pill-no';
  return `<span class="pill ${cls}">${side}</span>`;
}

function statusPill(status) {
  if (status === 'WIN') return '<span class="pill pill-win">WIN</span>';
  if (status === 'LOSE') return '<span class="pill pill-lose">LOSE</span>';
  return '<span class="pill pill-open">OPEN</span>';
}

async function fetchJSON(url) {
  try {
    const r = await fetch(url);
    if (!r.ok) throw new Error(r.status);
    return await r.json();
  } catch (e) {
    console.error('Fetch error:', url, e);
    return null;
  }
}

async function loadStats() {
  const d = await fetchJSON('/api/stats');
  if (!d) return;

  const pnlEl = $('statPnl');
  pnlEl.textContent = fmtPnl(d.total_pnl);
  pnlEl.className = 'value ' + pnlClass(d.total_pnl);
  $('statPnlSub').textContent = `Realised: ${fmtPnl(d.realised_pnl)} | Unreal: ${fmtPnl(d.unrealised_pnl)}`;

  $('statWinRate').textContent = fmtPct(d.win_rate);
  $('statWinRateSub').textContent = `${d.wins}W / ${d.losses}L`;

  $('statOpen').textContent = d.open_positions;
  $('statOpenSub').textContent = `Unrealised: ${fmtPnl(d.unrealised_pnl)}`;

  $('statTotal').textContent = d.total_trades;
  $('statTotalSub').textContent = `Sharpe: ${d.sharpe_ratio.toFixed(2)}`;
}

async function loadPositions() {
  const d = await fetchJSON('/api/portfolio');
  if (!d) return;
  $('posCount').textContent = d.count;

  if (!d.positions.length) {
    $('positionsBody').innerHTML = '<tr><td colspan="8" class="empty">No open positions</td></tr>';
    return;
  }

  $('positionsBody').innerHTML = d.positions.map(p => `
    <tr>
      <td class="mono">${p.id}</td>
      <td class="question-text" title="${p.question}">${p.question}</td>
      <td>${sidePill(p.side)}</td>
      <td class="mono">${fmtPrice(p.entry_price)}</td>
      <td class="mono">${fmtPrice(p.current_price)}</td>
      <td class="mono">${fmtMoney(p.amount)}</td>
      <td class="mono ${pnlClass(p.unrealised_pnl)}">${fmtPnl(p.unrealised_pnl)} (${p.pnl_pct >= 0 ? '+' : ''}${p.pnl_pct.toFixed(1)}%)</td>
      <td class="mono">${p.age}</td>
    </tr>
  `).join('');
}

async function loadEdges() {
  const d = await fetchJSON('/api/edges');
  if (!d) {
    $('edgesBody').innerHTML = '<tr><td colspan="8" class="empty">Failed to load edges</td></tr>';
    return;
  }
  $('edgeCount').textContent = d.count || 0;

  if (!d.edges || !d.edges.length) {
    $('edgesBody').innerHTML = '<tr><td colspan="8" class="empty">No edges found — markets appear efficient</td></tr>';
    return;
  }

  $('edgesBody').innerHTML = d.edges.slice(0, 25).map(e => `
    <tr>
      <td class="question-text" title="${e.question}">${e.question}</td>
      <td class="mono">${fmtPrice(e.yes_price)}</td>
      <td class="mono">${(e.est_prob * 100).toFixed(1)}%</td>
      <td>${sidePill(e.side)}</td>
      <td class="mono positive">+${(e.edge * 100).toFixed(1)}%</td>
      <td class="mono">${(e.kelly * 100).toFixed(1)}%</td>
      <td class="mono">${fmtMoney(e.volume)}</td>
      <td><span class="mono">${e.confidence}</span></td>
    </tr>
  `).join('');
}

async function loadHistory() {
  const d = await fetchJSON('/api/history');
  if (!d) return;
  $('historyCount').textContent = d.count;

  if (!d.trades.length) {
    $('historyBody').innerHTML = '<tr><td colspan="8" class="empty">No trades yet</td></tr>';
    return;
  }

  $('historyBody').innerHTML = d.trades.map(t => `
    <tr>
      <td class="mono">${t.id}</td>
      <td class="question-text" title="${t.question}">${t.question}</td>
      <td>${sidePill(t.side)}</td>
      <td class="mono">${fmtMoney(t.amount)}</td>
      <td class="mono">${fmtPrice(t.entry_price)}</td>
      <td>${statusPill(t.status)}</td>
      <td class="mono ${pnlClass(t.pnl)}">${t.pnl != null ? fmtPnl(t.pnl) : '--'}</td>
      <td class="mono">${fmtDate(t.created_at)}</td>
    </tr>
  `).join('');
}

async function checkHealth() {
  const d = await fetchJSON('/health');
  const badge = $('statusBadge');
  if (d && d.status === 'ok') {
    badge.className = 'status-badge running';
    badge.querySelector('span').textContent = 'running';
  } else {
    badge.className = 'status-badge stopped';
    badge.querySelector('span').textContent = 'stopped';
  }
}

async function refreshAll() {
  const now = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  $('lastUpdated').textContent = 'Last updated: ' + now;

  await Promise.all([
    checkHealth(),
    loadStats(),
    loadPositions(),
    loadHistory(),
  ]);

  // Load edges separately (slower, hits external API)
  loadEdges();
}

// Initial load
refreshAll();

// Auto-refresh every 30 seconds
setInterval(refreshAll, 30000);
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(content=DASHBOARD_HTML)


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Polymarket Agent Dashboard")
    parser.add_argument("--port", type=int, default=8501, help="Port to listen on (default: 8501)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    args = parser.parse_args()

    # Ensure tools_alerts is importable
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    print(f"Starting Polymarket Agent Dashboard on http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
