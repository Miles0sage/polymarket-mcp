"""Crypto market data via CoinGecko (free, no geo-restrictions) + ccxt fallbacks."""

import json
import httpx
from typing import Optional


COINGECKO_BASE = "https://api.coingecko.com/api/v3"

# Map common symbols to CoinGecko IDs
SYMBOL_TO_ID = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
    "DOGE": "dogecoin", "XRP": "ripple", "ADA": "cardano",
    "AVAX": "avalanche-2", "DOT": "polkadot", "MATIC": "matic-network",
    "LINK": "chainlink", "UNI": "uniswap", "ATOM": "cosmos",
    "LTC": "litecoin", "NEAR": "near", "ARB": "arbitrum",
    "OP": "optimism", "SUI": "sui", "APT": "aptos",
    "PEPE": "pepe", "SHIB": "shiba-inu", "TON": "the-open-network",
    "TRX": "tron", "BNB": "binancecoin", "RENDER": "render-token",
}


def get_crypto_prices(symbols: str = "BTC,ETH,SOL,DOGE,XRP") -> str:
    """Get current prices for crypto assets from CoinGecko.

    Args:
        symbols: Comma-separated symbols (e.g. "BTC,ETH,SOL")
    """
    try:
        symbol_list = [s.strip().upper() for s in symbols.split(",")]
        ids = [SYMBOL_TO_ID.get(s, s.lower()) for s in symbol_list]

        resp = httpx.get(
            f"{COINGECKO_BASE}/simple/price",
            params={
                "ids": ",".join(ids),
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_24hr_vol": "true",
                "include_market_cap": "true",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        lines = ["Crypto Prices:\n"]

        for sym, cg_id in zip(symbol_list, ids):
            info = data.get(cg_id, {})
            if not info:
                lines.append(f"{sym}: No data")
                continue

            price = info.get("usd", 0)
            change = info.get("usd_24h_change", 0) or 0
            vol = info.get("usd_24h_vol", 0) or 0
            mcap = info.get("usd_market_cap", 0) or 0

            arrow = "+" if change >= 0 else ""
            lines.append(f"{sym}: ${price:,.2f} ({arrow}{change:.1f}%)")
            lines.append(f"  Market Cap: ${mcap:,.0f} | 24h Volume: ${vol:,.0f}")
            lines.append("")

        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def crypto_market_overview() -> str:
    """Get top 20 crypto by market cap with prices and 24h change."""
    try:
        resp = httpx.get(
            f"{COINGECKO_BASE}/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 20,
                "page": 1,
                "sparkline": "false",
            },
            timeout=15,
        )
        resp.raise_for_status()
        coins = resp.json()

        lines = ["Top 20 Crypto by Market Cap:\n"]
        for i, c in enumerate(coins, 1):
            sym = c.get("symbol", "?").upper()
            price = c.get("current_price", 0) or 0
            change = c.get("price_change_percentage_24h", 0) or 0
            mcap = c.get("market_cap", 0) or 0
            vol = c.get("total_volume", 0) or 0
            arrow = "+" if change >= 0 else ""
            lines.append(
                f"{i:2d}. {sym:8s} ${price:>12,.2f}  {arrow}{change:>6.1f}%  "
                f"MCap: ${mcap:>14,.0f}  Vol: ${vol:>12,.0f}"
            )

        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def crypto_fear_greed() -> str:
    """Get Bitcoin Fear & Greed Index (Alternative.me API)."""
    try:
        resp = httpx.get("https://api.alternative.me/fng/?limit=7", timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", [])

        if not data:
            return "No Fear & Greed data available"

        lines = ["Bitcoin Fear & Greed Index (7 days):\n"]
        for entry in data:
            value = int(entry["value"])
            label = entry["value_classification"]
            from datetime import datetime
            ts = int(entry.get("timestamp", 0))
            date = datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "?"

            bar = "#" * (value // 5) + "." * (20 - value // 5)
            lines.append(f"  {date}: [{bar}] {value}/100 — {label}")

        current = int(data[0]["value"])
        if current < 25:
            lines.append("\nSignal: EXTREME FEAR — historically a buying opportunity")
        elif current < 40:
            lines.append("\nSignal: FEAR — market is cautious")
        elif current < 60:
            lines.append("\nSignal: NEUTRAL")
        elif current < 75:
            lines.append("\nSignal: GREED — market is optimistic")
        else:
            lines.append("\nSignal: EXTREME GREED — historically a selling signal")

        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def crypto_vs_polymarket(crypto_symbol: str = "BTC") -> str:
    """Compare crypto spot price with Polymarket prediction markets for the asset."""
    try:
        # Get current price from CoinGecko
        cg_id = SYMBOL_TO_ID.get(crypto_symbol.upper(), crypto_symbol.lower())
        price_resp = httpx.get(
            f"{COINGECKO_BASE}/simple/price",
            params={
                "ids": cg_id,
                "vs_currencies": "usd",
                "include_24hr_change": "true",
            },
            timeout=10,
        )
        price_resp.raise_for_status()
        price_data = price_resp.json().get(cg_id, {})
        current_price = price_data.get("usd", 0)
        change_24h = price_data.get("usd_24h_change", 0) or 0

        # Get Polymarket markets about this crypto
        pm_resp = httpx.get(
            "https://gamma-api.polymarket.com/markets",
            params={"limit": 200, "active": "true", "closed": "false"},
            timeout=15,
        )
        pm_resp.raise_for_status()
        markets = pm_resp.json()

        crypto_names = {
            "BTC": ["bitcoin", "btc"],
            "ETH": ["ethereum", "eth"],
            "SOL": ["solana", "sol"],
            "DOGE": ["doge", "dogecoin"],
            "XRP": ["xrp", "ripple"],
        }
        keywords = crypto_names.get(crypto_symbol.upper(), [crypto_symbol.lower()])

        related = [
            m for m in markets
            if any(kw in m.get("question", "").lower() for kw in keywords)
        ]

        lines = [
            f"=== {crypto_symbol.upper()} Analysis ===\n",
            f"Current Price: ${current_price:,.2f} ({'+'if change_24h>=0 else ''}{change_24h:.1f}% 24h)\n",
        ]

        if related:
            lines.append(f"Polymarket Markets ({len(related)}):\n")
            for i, m in enumerate(related[:10], 1):
                outcome_prices = m.get("outcomePrices", [])
                yes_price = "?"
                if outcome_prices:
                    try:
                        prices = outcome_prices if isinstance(outcome_prices, list) else json.loads(outcome_prices)
                        p = float(prices[0])
                        if 0 < p < 1:
                            yes_price = f"{p:.0%}"
                    except Exception:
                        pass
                lines.append(f"  {i}. {m.get('question', '?')}")
                lines.append(f"     YES: {yes_price} | Vol: ${float(m.get('volume', 0)):,.0f}")
                lines.append("")
        else:
            lines.append("No active Polymarket markets for this asset.\n")

        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


if __name__ == "__main__":
    print(get_crypto_prices("BTC,ETH,SOL"))
    print("\n" + crypto_fear_greed())
