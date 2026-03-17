# Polymarket MCP -- The Open-Source Prediction Market Agent

**Your AI edge in prediction markets.** Search, analyze, detect mispricing, track whales, and trade -- all from your LLM.

![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-brightgreen.svg)
![Tools](https://img.shields.io/badge/Tools-15+-orange.svg)

---

## What This Is

Most prediction market tools give you a dashboard. This gives you a **brain**. Polymarket MCP connects any LLM (Claude, GPT, Gemini) to Polymarket's data and wraps it with EV calculations, Kelly sizing, arbitrage detection, news-driven edge finding, and crypto correlation analysis -- all as MCP tools your AI can call autonomously.

Not a toy. Not a wrapper. A full agent toolkit for prediction markets.

---

## Features

| Category | Capability | Status |
|----------|-----------|--------|
| **Market Analysis** | Search, trending, details, sports/crypto filters, market summaries | Live (9 tools) |
| **Edge Detection** | Auto-scan markets for mispricing via news sentiment analysis | Live (2 tools) |
| **Risk Management** | EV calculation, Kelly criterion sizing, arbitrage scanning | Live (3 tools) |
| **Crypto Integration** | Live prices (CoinGecko), Fear/Greed index, crypto vs predictions | Live (4 tools) |
| **Paper Trading** | Risk-free practice with virtual bankroll, track P&L | Planned |
| **Whale Tracking** | Follow top traders (Theo4, Fredi9999, etc.), copy signals | Planned |
| **Alert System** | Telegram/Discord notifications on edge detection triggers | Planned |
| **Live Trading** | Execute trades via Polymarket CLOB API | Planned |

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
  "polymarket": {
    "command": "python3",
    "args": ["server.py"],
    "cwd": "/path/to/polymarket-mcp"
  }
}
```

No API keys required for market data. Works immediately with Claude Code, Cursor, Windsurf, or any MCP-compatible client.

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
              +-------------------+-------------------+
              |                   |                   |
     +--------v------+  +--------v------+  +---------v-----+
     | Market Data   |  |  Analysis     |  |  Research      |
     | (tools_       |  |  (tools_      |  |  (tools_       |
     |  markets.py)  |  |   analysis.py)|  |   research.py) |
     +-------+-------+  +-------+-------+  +--------+------+
              |                  |                    |
     +--------v------+  +-------v-------+  +---------v-----+
     | Gamma API     |  | EV / Kelly /  |  | Google News   |
     | CLOB API      |  | Arbitrage     |  | YouTube       |
     +---------------+  +---------------+  | Sentiment     |
                                           +---------------+
              +-------------------+
              |   Crypto Data     |
              |  (tools_crypto.py)|
              +--------+----------+
                       |
              +--------v----------+
              | CoinGecko API     |
              | Fear/Greed Index  |
              +---------+---------+
                        |
                  (Future)
                        |
     +------------------v------------------+
     |  Paper Trading  |  Whale Tracker    |
     |  Risk Manager   |  Alert System     |
     |  CLOB Trading   |  Dashboard UI     |
     +------------------+------------------+
```

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

### Analysis (3 tools)

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
| `market_summary` | Human-readable summary with implied probability and market read |

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

"Research: Will Bitcoin hit $200K by end of 2026?"
  -> News headlines, YouTube analysis, sentiment score

"Compare BTC spot price with Polymarket prediction markets"
  -> Current price + all related markets side by side

"What's the Fear & Greed Index saying?"
  -> 7-day chart, current reading, trading signal
```

---

## Roadmap

- [ ] **Paper Trading** -- Virtual bankroll, position tracking, P&L history
- [ ] **Whale Tracker** -- Monitor top Polymarket wallets, alert on large positions
- [ ] **Live Trading** -- Execute via Polymarket CLOB API (requires wallet + API key)
- [ ] **WebSocket Feeds** -- Real-time price updates instead of polling
- [ ] **Alert System** -- Telegram/Discord notifications on edge triggers
- [ ] **Dashboard UI** -- Web UI for portfolio, positions, edge scanner
- [ ] **Discord Bot** -- Query markets and get alerts in Discord
- [ ] **One-Click Deploy** -- Railway/Render template for hosted instance

---

## Comparison

| Feature | Polymarket MCP | Polystrat | Kalshi News Bot | Manual Trading |
|---------|---------------|-----------|-----------------|----------------|
| LLM integration | Native MCP | None | API only | None |
| Edge detection | Auto (news sentiment) | Manual | None | Manual |
| Kelly sizing | Built-in | None | None | Spreadsheet |
| Arbitrage scan | Built-in | None | None | Manual |
| Crypto correlation | Live CoinGecko | None | N/A | Manual |
| Open source | MIT | Closed | Closed | N/A |
| Setup time | 2 minutes | Account required | API key + setup | N/A |
| Cost | Free | Subscription | Subscription | Free |

---

## Contributing

PRs welcome. The codebase is intentionally simple -- pure Python, no frameworks, no databases. Each tool module is standalone.

```
server.py             # MCP server, tool registration
tools_markets.py      # Market data (Gamma API, CLOB API)
tools_analysis.py     # EV, Kelly, arbitrage math
tools_research.py     # News sentiment, edge finding
tools_crypto.py       # CoinGecko prices, Fear/Greed
```

---

## License

MIT
