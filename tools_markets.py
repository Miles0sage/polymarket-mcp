"""Polymarket market data — search, trending, details via Gamma API."""

import httpx
import json
from typing import Optional


GAMMA_URL = "https://gamma-api.polymarket.com/markets"


def _fetch_markets(params: dict) -> list:
    """Fetch markets from Gamma API with params."""
    with httpx.Client(timeout=15) as client:
        resp = client.get(GAMMA_URL, params=params)
        resp.raise_for_status()
        return resp.json()


def search_markets(query: str, max_results: int = 10) -> str:
    """Search Polymarket for active markets by keyword."""
    try:
        # Gamma API supports text search via slug/question matching
        markets = _fetch_markets({
            "limit": 100,
            "active": "true",
            "closed": "false",
        })

        # Filter by query in question
        matching = [
            m for m in markets
            if query.lower() in m.get("question", "").lower()
        ][:max_results]

        if not matching:
            return f"No active markets found matching '{query}'"

        return _format_markets(matching, f"Found {len(matching)} markets matching '{query}'")

    except Exception as e:
        return f"Error searching markets: {e}"


def get_market(condition_id: str) -> str:
    """Get full details for a specific market."""
    try:
        markets = _fetch_markets({"limit": 200, "active": "true"})
        market = next((m for m in markets if m.get("condition_id") == condition_id), None)

        if not market:
            # Try CLOB API
            with httpx.Client(timeout=10) as client:
                resp = client.get(f"https://clob.polymarket.com/markets/{condition_id}")
                resp.raise_for_status()
                market = resp.json()

        if not market:
            return f"Market {condition_id} not found"

        yes_price, no_price = _extract_prices(market)

        return (
            f"Market Details:\n"
            f"Condition ID: {market.get('condition_id', 'N/A')}\n"
            f"Question: {market.get('question', 'N/A')}\n"
            f"Description: {market.get('description', 'N/A')[:500]}\n"
            f"YES Price: {yes_price}\n"
            f"NO Price: {no_price}\n"
            f"Volume: ${float(market.get('volume', 0)):,.0f}\n"
            f"Liquidity: ${float(market.get('liquidity', 0)):,.0f}\n"
            f"End Date: {market.get('end_date_iso', market.get('end_date', 'N/A'))}\n"
        )

    except Exception as e:
        return f"Error getting market: {e}"


def get_prices(token_id: str) -> str:
    """Get current bid/ask prices for a token."""
    try:
        with httpx.Client(timeout=10) as client:
            buy = client.get(f"https://clob.polymarket.com/price?token_id={token_id}&side=buy")
            sell = client.get(f"https://clob.polymarket.com/price?token_id={token_id}&side=sell")
            buy.raise_for_status()
            sell.raise_for_status()

        return (
            f"Token: {token_id}\n"
            f"Bid: {buy.json().get('price', 'N/A')}\n"
            f"Ask: {sell.json().get('price', 'N/A')}\n"
        )
    except Exception as e:
        return f"Error getting prices: {e}"


def trending_markets(max_results: int = 10) -> str:
    """Get top active markets sorted by volume."""
    try:
        markets = _fetch_markets({
            "limit": 200,
            "active": "true",
            "closed": "false",
        })

        # Filter out markets with no real volume and sort
        with_volume = [
            m for m in markets
            if m.get("volume") and float(m.get("volume", 0)) > 100
        ]

        sorted_markets = sorted(
            with_volume,
            key=lambda x: float(x.get("volume", 0)),
            reverse=True,
        )[:max_results]

        if not sorted_markets:
            return "No trending markets found"

        return _format_markets(sorted_markets, f"Top {len(sorted_markets)} markets by volume")

    except Exception as e:
        return f"Error getting trending markets: {e}"


def crypto_markets(max_results: int = 10) -> str:
    """Get active crypto-related prediction markets."""
    try:
        markets = _fetch_markets({
            "limit": 200,
            "active": "true",
            "closed": "false",
        })

        crypto_keywords = ["bitcoin", "btc", "ethereum", "eth", "crypto", "solana", "sol", "defi", "token", "coin", "blockchain"]
        crypto = [
            m for m in markets
            if any(kw in m.get("question", "").lower() for kw in crypto_keywords)
        ][:max_results]

        if not crypto:
            return "No active crypto markets found"

        return _format_markets(crypto, f"Found {len(crypto)} crypto markets")

    except Exception as e:
        return f"Error: {e}"


def sports_markets(max_results: int = 10) -> str:
    """Get active sports prediction markets."""
    try:
        markets = _fetch_markets({
            "limit": 200,
            "active": "true",
            "closed": "false",
        })

        sports_keywords = ["nba", "nfl", "mlb", "nhl", "soccer", "football", "basketball", "baseball", "ufc", "mma", "tennis", "f1", "ncaa"]
        sports = [
            m for m in markets
            if any(kw in m.get("question", "").lower() for kw in sports_keywords)
        ][:max_results]

        if not sports:
            return "No active sports markets found"

        return _format_markets(sports, f"Found {len(sports)} sports markets")

    except Exception as e:
        return f"Error: {e}"


# --- Helpers ---

def _extract_prices(market: dict) -> tuple:
    """Extract YES/NO prices from market data."""
    outcome_prices = market.get("outcomePrices", [])
    if isinstance(outcome_prices, str):
        try:
            outcome_prices = json.loads(outcome_prices)
        except Exception:
            outcome_prices = []

    yes_price = "N/A"
    no_price = "N/A"

    if len(outcome_prices) >= 2:
        try:
            y = float(outcome_prices[0])
            n = float(outcome_prices[1])
            if y > 0 and y < 1:
                yes_price = f"{y:.4f}"
                no_price = f"{n:.4f}"
            elif n > 0 and n < 1:
                yes_price = f"{n:.4f}"
                no_price = f"{y:.4f}"
        except (ValueError, TypeError):
            pass

    # Fallback: tokens array
    if yes_price == "N/A":
        for token in market.get("tokens", []):
            outcome = token.get("outcome", "").lower()
            price = token.get("price")
            if price and outcome in ("yes", "true", "1"):
                yes_price = f"{float(price):.4f}"
            elif price and outcome in ("no", "false", "0"):
                no_price = f"{float(price):.4f}"

    return yes_price, no_price


def _format_markets(markets: list, header: str) -> str:
    """Format a list of markets for display."""
    lines = [f"{header}:\n"]

    for i, m in enumerate(markets, 1):
        yes_price, no_price = _extract_prices(m)
        volume = float(m.get("volume", 0))
        liquidity = float(m.get("liquidity", 0))
        end_date = m.get("end_date_iso", m.get("end_date", "N/A"))

        lines.append(f"{i}. {m.get('question', '?')}")
        lines.append(f"   ID: {m.get('condition_id', 'N/A')}")
        lines.append(f"   YES: {yes_price} | NO: {no_price}")
        lines.append(f"   Volume: ${volume:,.0f} | Liquidity: ${liquidity:,.0f}")
        lines.append(f"   Ends: {end_date}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    print("=== Trending Markets ===")
    print(trending_markets(5))
    print("\n=== Crypto Markets ===")
    print(crypto_markets(5))
    print("\n=== Sports Markets ===")
    print(sports_markets(5))
