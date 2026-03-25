# Polymarket MCP

**Your AI edge in prediction markets.** Search, analyze, detect mispricing, track whales, and paper trade -- all from your LLM.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-brightgreen?logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCI+PC9zdmc+)](https://modelcontextprotocol.io)
[![Tools: 22](https://img.shields.io/badge/tools-22-orange.svg)](#tool-reference)
[![GitHub stars](https://img.shields.io/github/stars/Miles0sage/polymarket-mcp?style=social)](https://github.com/Miles0sage/polymarket-mcp)

---

## What This Is

Most prediction market tools give you a dashboard. This gives you a **brain**. Polymarket MCP connects any LLM (Claude, GPT, Gemini) to Polymarket's data and wraps it with EV calculations, Kelly sizing, arbitrage detection, whale tracking, paper trading, and crypto correlation analysis -- all as MCP tools your AI can call autonomously.

Not a toy. Not a wrapper. A full agent toolkit for prediction markets.

---

## Features

| Category | Tools | What You Get |
|----------|:-----:|--------------|
| **Market Data** | 5 | Search, trending, details, sports & crypto market filters |
| **Risk & Sizing** | 3 | Expected value calc, Kelly criterion, arbitrage scanning |
| **Research & Edge** | 3 | News sentiment analysis, batch edge finder, auto edge scanner |
| **Paper Trading** | 5 | Risk-free practice, portfolio tracking, settlement, trade history, orderbook |
| **Crypto** | 4 | Live prices (CoinGecko), Fear & Greed index, crypto vs prediction cross-analysis |
| **Whale Tracking** | 1 | Monitor top Polymarket wallets and large position changes |
| **Autonomous Agent** | -- | Standalone agent mode: scans 11K+ markets, paper trades with risk controls |

---

## Quick Start

```bash
git clone https://github.com/Miles0sage/polymarket-mcp.git
cd polymarket-mcp
pip install -r requirements.txt
```

Add to your MCP config (`~/.mcp.json` or client settings):

```json
{
  "mcpServers": {
    "polymarket": {
      "command": "python3",
      "args": ["server.py"],
      "cwd": "/path/to/polymarket-mcp"
    }
  }
}
```

No API keys required for market data. Works immediately with Claude Code, Cursor, Windsurf, or any MCP client.

---

## Tool Reference

### Market Data (5 tools)

| Tool | Description |
|------|-------------|
| `search_markets` | Search active markets by keyword |
| `get_market` | Full details for a specific market (prices, volume, liquidity, dates) |
| `trending_markets` | Top markets ranked by trading volume |
| `crypto_prediction_markets` | Active crypto-related markets (BTC, ETH, SOL, DeFi) |
| `sports_prediction_markets` | Active sports markets (NBA, NFL, UFC, F1, NCAA) |

### Risk & Sizing (3 tools)

| Tool | Description |
|------|-------------|
| `calculate_ev` | Expected value + Kelly sizing for YES/NO positions |
| `kelly_size` | Full and quarter Kelly bet sizing given bankroll, probability, odds |
| `arbitrage_scan` | Detect arbitrage across market outcomes |

### Research & Edge Finding (3 tools)

| Tool | Description |
|------|-------------|
| `research_market` | News + YouTube + sentiment analysis for any market question |
| `edge_finder` | Batch scan markets for mispricing via news sentiment vs market price |
| `scan_edges` | Auto-scan trending markets for edges above your threshold |

### Paper Trading (5 tools)

| Tool | Description |
|------|-------------|
| `paper_trade` | Place a simulated trade with virtual bankroll |
| `paper_portfolio` | View open positions and P&L |
| `paper_settle` | Settle a trade when the market resolves |
| `paper_history` | Full trade history with results |
| `get_orderbook` | Live orderbook depth for a market token |

### Whale Tracking (1 tool)

| Tool | Description |
|------|-------------|
| `whale_activity` | Monitor top Polymarket traders and large position changes |

### Crypto (4 tools)

| Tool | Description |
|------|-------------|
| `crypto_prices` | Live prices from CoinGecko with 24h change, volume, market cap |
| `crypto_overview` | Top 20 crypto by market cap |
| `crypto_fear_greed` | Bitcoin Fear & Greed Index (7-day history + trading signal) |
| `crypto_vs_predictions` | Compare spot price with related Polymarket markets |

---

## Usage Examples

```
"Search Polymarket for Bitcoin markets"
  -> 10 markets with YES/NO prices, volume, liquidity

"Calculate EV: YES price 0.35, my estimate 0.55"
  -> EV: +57.1%, Quarter-Kelly: 7.7% of bankroll, BET YES

"Check for arbitrage: 0.45, 0.43, 0.08"
  -> ARBITRAGE FOUND! Buy all for $0.96, collect $1.00

"Paper trade $50 YES on 'Will BTC hit 200K?'"
  -> Trade placed, virtual bankroll updated, tracking P&L

"Scan for edges with min 5% mispricing"
  -> 3 markets found with news sentiment diverging from price

"Show whale activity"
  -> Top traders, recent large positions, copy signals

"What's the Fear & Greed Index saying?"
  -> 7-day chart, current reading, trading signal
```

---

## Architecture

```
                         +------------------+
                         |   LLM / Client   |
                         | (Claude, GPT...) |
                         +--------+---------+
                                  |
                            MCP Protocol
                                  |
                         +--------v---------+
                         |   MCP Server     |
                         |   (server.py)    |
                         +--------+---------+
                                  |
         +------------+----------+----------+------------+
         |            |          |          |            |
    +----v----+ +-----v----+ +--v------+ +-v--------+ +-v--------+
    | Markets | | Analysis | | Research| | Trading  | | Crypto   |
    +---------+ +----------+ +---------+ +----------+ +----------+
         |            |          |          |            |
    Gamma API    EV/Kelly    Google     Paper P&L    CoinGecko
    CLOB API    Arbitrage    News       Orderbook    Fear/Greed
                            YouTube     Whales
```

---

## Standalone Agent

Beyond the MCP tools, `agent.py` runs as a fully autonomous trading agent:

- Scans 11,000+ active markets for mispricing
- Places paper trades with risk controls (position limits, bankroll management)
- Sends alerts via Telegram on high-edge opportunities
- Runs on a cron or as a long-lived process

```bash
python3 agent.py
```

Web dashboard (Bloomberg-style UI):

```bash
python3 dashboard.py  # port 8501
```

---

## Comparison

| Feature | Polymarket MCP | Polystrat | Kalshi News Bot | Manual Trading |
|---------|:-:|:-:|:-:|:-:|
| LLM integration | Native MCP | None | API only | None |
| Edge detection | Auto (news) | Manual | None | Manual |
| Kelly sizing | Built-in | None | None | Spreadsheet |
| Arbitrage scan | Built-in | None | None | Manual |
| Paper trading | Built-in | None | None | N/A |
| Whale tracking | Built-in | None | None | Manual |
| Crypto correlation | Live | None | N/A | Manual |
| Open source | MIT | Closed | Closed | N/A |
| Setup time | 2 min | Account | API key | N/A |
| Cost | **Free** | Subscription | Subscription | Free |

---

## Roadmap

- [x] Market search, trending, details
- [x] EV calculation + Kelly sizing
- [x] Arbitrage detection
- [x] News sentiment edge finding
- [x] Crypto prices + Fear & Greed
- [x] Paper trading + portfolio tracking
- [x] Whale activity tracking
- [x] Orderbook data
- [x] Autonomous agent + dashboard
- [ ] Live trading via Polymarket CLOB API
- [ ] WebSocket real-time price feeds
- [ ] Telegram/Discord alert system
- [ ] One-click Railway/Render deploy

---

## Contributing

PRs welcome. The codebase is intentionally simple -- pure Python, no frameworks, no databases. Each tool module is standalone.

```
server.py             # MCP server, tool registration
tools_markets.py      # Market data (Gamma API, CLOB API)
tools_analysis.py     # EV, Kelly, arbitrage math
tools_research.py     # News sentiment, edge finding
tools_trading.py      # Paper trading, whale tracking, orderbook
tools_crypto.py       # CoinGecko prices, Fear/Greed
tools_alerts.py       # Alert system
agent.py              # Autonomous trading agent
dashboard.py          # Web dashboard (Streamlit)
```

---

## License

MIT
