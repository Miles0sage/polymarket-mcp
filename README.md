# 📈 Polymarket MCP Server

**AI-powered prediction market tools — search markets, find edges, calculate EV, size bets.**

No API key needed for reading. Works with Claude Code, Cursor, Windsurf, or any MCP client.

![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-brightgreen.svg)
![Tools](https://img.shields.io/badge/Tools-9-orange.svg)

---

## 🛠️ Tools

| Tool | What it does | Auth |
|------|-------------|------|
| `search_markets` | Search Polymarket by keyword | None |
| `get_market` | Get full market details | None |
| `trending_markets` | Top markets by volume | None |
| `calculate_ev` | Expected value + Kelly sizing | None |
| `kelly_size` | Full & quarter Kelly bet sizing | None |
| `arbitrage_scan` | Find arb opportunities across outcomes | None |
| `market_summary` | Human-readable market analysis | None |
| `research_market` | News + YouTube research for any market | None |
| `edge_finder` | Find mispriced contracts via news sentiment | None |

## 🚀 Quick Start

```bash
git clone https://github.com/Miles0sage/polymarket-mcp.git
cd polymarket-mcp
pip install -r requirements.txt
```

Add to `~/.mcp.json`:
```json
{
  "polymarket": {
    "command": "python3",
    "args": ["server.py"],
    "cwd": "/path/to/polymarket-mcp"
  }
}
```

## 💡 Examples

```
"Search Polymarket for Bitcoin markets"
→ 10 markets with YES/NO prices, volume

"Calculate EV: YES price 0.35, my estimate 0.55"
→ EV: +57.1%, Quarter-Kelly: 7.7% of bankroll, BET YES

"Check for arbitrage: 0.45, 0.43, 0.08"
→ ARBITRAGE FOUND! Buy all for $0.96, collect $1.00

"Research: Will Bitcoin hit $200K by end of 2026?"
→ News headlines, YouTube videos, sentiment analysis
```

## 📄 License

MIT
