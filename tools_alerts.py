"""Edge alert system — scan for mispriced markets, whale signals, Telegram alerts."""

import json
import math
import os
from datetime import datetime, timezone
from typing import Optional

import httpx


GAMMA_URL = "https://gamma-api.polymarket.com/markets"
LEADERBOARD_URL = "https://data-api.polymarket.com/v1/leaderboard"
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _get_telegram_creds() -> tuple[Optional[str], Optional[str]]:
    """Load Telegram credentials from env or .env files."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if token and chat_id:
        return token, chat_id

    # Try loading from .env files
    for env_path in [".env", "/root/polymarket-mcp/.env", "/root/openclaw/.env"]:
        try:
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key == "TELEGRAM_BOT_TOKEN" and not token:
                        token = val
                    elif key == "TELEGRAM_CHAT_ID" and not chat_id:
                        chat_id = val
        except FileNotFoundError:
            continue

    return token, chat_id


def _fetch_markets(params: dict) -> list:
    """Fetch markets from Gamma API."""
    with httpx.Client(timeout=15) as client:
        resp = client.get(GAMMA_URL, params=params)
        resp.raise_for_status()
        return resp.json()


def _extract_yes_price(market: dict) -> Optional[float]:
    """Extract YES price from market data."""
    outcome_prices = market.get("outcomePrices", [])
    if isinstance(outcome_prices, str):
        try:
            outcome_prices = json.loads(outcome_prices)
        except Exception:
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


def _estimate_true_probability(market: dict, yes_price: float) -> tuple[float, str]:
    """Estimate true probability using volume/liquidity heuristics.

    Returns (estimated_prob, confidence_level).

    Heuristics:
    - High volume + high liquidity = market is efficient, small adjustment
    - Low volume = potential mispricing, larger adjustment toward 50%
    - Price momentum: extreme prices (>0.90 or <0.10) in low-volume markets
      tend to revert, apply mean-reversion adjustment
    - Market age: newer markets have less price discovery
    """
    volume = float(market.get("volume", 0))
    liquidity = float(market.get("liquidity", 0))

    # Start with market price as base
    est = yes_price

    # Volume-based confidence
    if volume < 5000:
        confidence = "LOW"
        # Low volume = pull toward 50% (less price discovery)
        est = yes_price * 0.7 + 0.5 * 0.3
    elif volume < 50000:
        confidence = "MEDIUM"
        est = yes_price * 0.85 + 0.5 * 0.15
    elif volume < 500000:
        confidence = "MEDIUM-HIGH"
        est = yes_price * 0.92 + 0.5 * 0.08
    else:
        confidence = "HIGH"
        # High volume markets are mostly efficient
        est = yes_price * 0.97 + 0.5 * 0.03

    # Liquidity ratio adjustment: low liquidity relative to volume = slippage risk
    if volume > 0:
        liq_ratio = liquidity / volume
        if liq_ratio < 0.01:
            # Very thin book — prices can be stale
            est = est * 0.9 + 0.5 * 0.1
            confidence = "LOW"

    # Mean reversion for extreme prices in thin markets
    if volume < 100000:
        if yes_price > 0.92:
            est = min(est, yes_price - 0.03)
        elif yes_price < 0.08:
            est = max(est, yes_price + 0.03)

    # Clamp
    est = max(0.01, min(0.99, est))

    return est, confidence


def _kelly_fraction(prob: float, price: float) -> float:
    """Quarter-Kelly fraction for a YES bet."""
    if price <= 0 or price >= 1 or prob <= 0 or prob >= 1:
        return 0.0
    edge = prob - price
    if edge <= 0:
        return 0.0
    kelly = (prob * (1 - price) - (1 - prob) * price) / (1 - price)
    return max(0, kelly / 4)


def scan_edges(min_edge: float = 0.05, min_volume: float = 10000) -> str:
    """Scan all active Polymarket markets for edges.

    Args:
        min_edge: Minimum edge (estimated_prob - market_price) to report.
        min_volume: Minimum USD volume to consider a market.

    Returns:
        Formatted list of edge opportunities.
    """
    try:
        markets = _fetch_markets({
            "limit": 200,
            "active": "true",
            "closed": "false",
        })
    except Exception as e:
        return f"Error fetching markets: {e}"

    edges = []

    for m in markets:
        volume = float(m.get("volume", 0))
        if volume < min_volume:
            continue

        yes_price = _extract_yes_price(m)
        if yes_price is None or yes_price <= 0.01 or yes_price >= 0.99:
            continue

        est_prob, confidence = _estimate_true_probability(m, yes_price)

        # Check YES edge
        yes_edge = est_prob - yes_price
        # Check NO edge
        no_edge = (1 - est_prob) - (1 - yes_price)  # same magnitude, opposite sign

        if abs(yes_edge) >= min_edge:
            side = "YES" if yes_edge > 0 else "NO"
            edge_val = abs(yes_edge)
            bet_price = yes_price if side == "YES" else (1 - yes_price)
            bet_prob = est_prob if side == "YES" else (1 - est_prob)
            kelly = _kelly_fraction(bet_prob, bet_price)

            edges.append({
                "question": m.get("question", "?"),
                "condition_id": m.get("condition_id", ""),
                "yes_price": yes_price,
                "est_prob": est_prob,
                "side": side,
                "edge": edge_val,
                "kelly": kelly,
                "confidence": confidence,
                "volume": volume,
                "liquidity": float(m.get("liquidity", 0)),
            })

    # Sort by edge descending
    edges.sort(key=lambda x: x["edge"], reverse=True)

    if not edges:
        return f"No edges found (min_edge={min_edge:.0%}, min_volume=${min_volume:,.0f}). Markets appear efficient."

    lines = [f"Edge Scanner: {len(edges)} opportunities found\n"]
    lines.append(f"Filters: edge >= {min_edge:.0%}, volume >= ${min_volume:,.0f}\n")

    for i, e in enumerate(edges, 1):
        lines.append(f"{i}. {e['question']}")
        lines.append(f"   ID: {e['condition_id']}")
        lines.append(f"   Market: YES {e['yes_price']:.0%} | Est. True: {e['est_prob']:.0%}")
        lines.append(f"   Signal: BET {e['side']} | Edge: +{e['edge']:.1%}")
        lines.append(f"   Quarter-Kelly: {e['kelly']:.1%} of bankroll")
        lines.append(f"   Volume: ${e['volume']:,.0f} | Confidence: {e['confidence']}")
        lines.append("")

    return "\n".join(lines)


def send_edge_alert(message: str) -> str:
    """Send an alert message via Telegram bot API.

    Falls back to returning the message if no Telegram credentials are set.

    Args:
        message: The alert text to send.

    Returns:
        Confirmation or the message itself if Telegram is unavailable.
    """
    token, chat_id = _get_telegram_creds()

    if not token or not chat_id:
        return f"[No Telegram creds — alert not sent]\n\n{message}"

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                TELEGRAM_API.format(token=token),
                json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("ok"):
                return f"Alert sent to Telegram (chat {chat_id})"
            return f"Telegram API error: {data}"
    except Exception as e:
        return f"Telegram send failed: {e}\n\nMessage was:\n{message}"


def check_whale_activity() -> str:
    """Check top Polymarket trader activity from leaderboard.

    Hits the Polymarket data API for the top 10 traders and
    cross-references with current edge signals.

    Returns:
        Formatted whale activity report.
    """
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(LEADERBOARD_URL, params={"limit": 10})
            resp.raise_for_status()
            leaders = resp.json()
    except Exception as e:
        return f"Error fetching leaderboard: {e}"

    if not leaders:
        return "No leaderboard data available."

    # Get current edge signals for cross-reference
    edge_text = scan_edges(min_edge=0.03, min_volume=5000)

    lines = ["Whale Activity Report (Top 10 Traders)\n"]

    for i, whale in enumerate(leaders, 1):
        username = whale.get("username") or whale.get("name") or whale.get("address", "anon")[:10]
        profit = float(whale.get("profit", 0) or whale.get("pnl", 0) or 0)
        volume = float(whale.get("volume", 0) or whale.get("totalVolume", 0) or 0)
        markets_traded = whale.get("marketsTraded") or whale.get("markets_traded") or "?"
        position_count = whale.get("positionCount") or whale.get("positions", "?")
        rank = whale.get("rank", i)

        lines.append(f"{rank}. {username}")
        lines.append(f"   P&L: ${profit:+,.0f} | Volume: ${volume:,.0f}")
        lines.append(f"   Markets: {markets_traded} | Positions: {position_count}")
        lines.append("")

    lines.append("---")
    lines.append("Current Edge Signals (for cross-reference):")
    lines.append(edge_text[:1500])  # Truncate to keep message reasonable

    return "\n".join(lines)


def auto_scan_and_alert() -> str:
    """Run edge scan + whale check, format results, send via Telegram.

    Designed for cron usage:
        python3 -c "from tools_alerts import auto_scan_and_alert; auto_scan_and_alert()"
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Run scans
    edge_report = scan_edges(min_edge=0.05, min_volume=10000)
    whale_report = check_whale_activity()

    # Format combined alert
    alert = (
        f"*Polymarket Edge Alert* -- {now}\n\n"
        f"{edge_report}\n\n"
        f"---\n\n"
        f"{whale_report}"
    )

    # Truncate for Telegram (4096 char limit)
    if len(alert) > 4000:
        alert = alert[:3950] + "\n\n... (truncated)"

    result = send_edge_alert(alert)
    print(result)
    print("\n" + alert)
    return result


if __name__ == "__main__":
    print("=" * 60)
    print("POLYMARKET EDGE SCANNER")
    print("=" * 60)

    print("\n--- Edge Scan (min_edge=5%, min_volume=$10K) ---")
    print(scan_edges())

    print("\n--- Whale Activity ---")
    print(check_whale_activity())

    print("\n--- Telegram Alert Test ---")
    print(send_edge_alert("Test alert from polymarket-mcp edge scanner"))
