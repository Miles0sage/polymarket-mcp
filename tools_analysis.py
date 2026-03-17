"""Polymarket trading analysis — EV, Kelly, arbitrage calculations."""


def calculate_ev(yes_price: float, estimated_probability: float) -> str:
    """Calculate expected value and Kelly criterion for a Polymarket bet."""
    if yes_price <= 0 or yes_price >= 1:
        return "Error: yes_price must be between 0 and 1"
    if estimated_probability <= 0 or estimated_probability >= 1:
        return "Error: estimated_probability must be between 0 and 1"

    # EV for YES bet: prob * payout - (1-prob) * cost
    payout_if_win = (1 / yes_price) - 1  # profit per dollar
    ev_yes = (estimated_probability * payout_if_win) - ((1 - estimated_probability) * 1)

    # EV for NO bet
    no_price = 1 - yes_price
    payout_no = (1 / no_price) - 1
    ev_no = ((1 - estimated_probability) * payout_no) - (estimated_probability * 1)

    # Kelly criterion for YES
    kelly_yes = (estimated_probability * (1 - yes_price) - (1 - estimated_probability) * yes_price) / (1 - yes_price)
    quarter_kelly_yes = kelly_yes / 4

    # Kelly for NO
    kelly_no = ((1 - estimated_probability) * yes_price - estimated_probability * (1 - yes_price)) / yes_price
    quarter_kelly_no = kelly_no / 4

    # Recommendation
    if ev_yes > 0.05:
        rec = f"BET YES (EV: +{ev_yes:.1%})"
        kelly = quarter_kelly_yes
    elif ev_no > 0.05:
        rec = f"BET NO (EV: +{ev_no:.1%})"
        kelly = quarter_kelly_no
    else:
        rec = "SKIP — no edge"
        kelly = 0

    implied_prob = yes_price
    edge = estimated_probability - implied_prob

    return (
        f"Market Price: YES {yes_price:.0%} / NO {1-yes_price:.0%}\n"
        f"Your Estimate: {estimated_probability:.0%}\n"
        f"Edge: {edge:+.1%}\n"
        f"EV (YES): {ev_yes:+.3f} | EV (NO): {ev_no:+.3f}\n"
        f"Quarter-Kelly: {abs(kelly):.1%} of bankroll\n"
        f"Recommendation: {rec}"
    )


def kelly_size(bankroll: float, probability: float, odds: float) -> str:
    """Calculate full and quarter Kelly bet sizing."""
    if probability <= 0 or probability >= 1:
        return "Error: probability must be between 0 and 1"

    # Kelly fraction: f = (p * b - q) / b where b = odds, p = prob, q = 1-p
    b = odds
    p = probability
    q = 1 - p

    kelly_f = (p * b - q) / b
    quarter_kelly_f = kelly_f / 4

    if kelly_f <= 0:
        return f"No bet — Kelly fraction negative ({kelly_f:.3f}). No edge at these odds."

    full_bet = bankroll * kelly_f
    quarter_bet = bankroll * quarter_kelly_f

    return (
        f"Bankroll: ${bankroll:,.2f}\n"
        f"Probability: {probability:.0%} | Odds: {odds:.2f}x\n"
        f"Full Kelly: {kelly_f:.1%} = ${full_bet:,.2f}\n"
        f"Quarter Kelly: {quarter_kelly_f:.1%} = ${quarter_bet:,.2f} (recommended)\n"
        f"Max loss: ${quarter_bet:,.2f}"
    )


def arbitrage_scan(yes_prices: str) -> str:
    """Check for arbitrage across Polymarket markets. Input: comma-separated yes prices."""
    try:
        prices = [float(p.strip()) for p in yes_prices.split(',')]
    except ValueError:
        return "Error: provide comma-separated decimal prices (e.g. '0.65, 0.30, 0.08')"

    total = sum(prices)
    has_arb = total < 0.98

    result = f"Prices: {', '.join(f'{p:.0%}' for p in prices)}\n"
    result += f"Sum: {total:.2%}\n"

    if has_arb:
        profit = 1 - total
        result += f"ARBITRAGE FOUND! Guaranteed profit: {profit:.1%}\n"
        result += f"Buy all outcomes for ${total:.2f}, collect $1.00 on resolution"
    else:
        overround = total - 1
        result += f"No arbitrage. Overround: {overround:.1%}"

    return result


def market_summary(question: str, yes_price: float, volume: float = 0, end_date: str = "") -> str:
    """Human-readable market summary."""
    implied_prob = yes_price * 100
    no_price = (1 - yes_price) * 100

    result = f"Question: {question}\n"
    result += f"YES: {implied_prob:.0f}¢ ({implied_prob:.0f}% implied) | NO: {no_price:.0f}¢\n"

    if volume:
        result += f"Volume: ${volume:,.0f}\n"
    if end_date:
        result += f"Resolves: {end_date}\n"

    if implied_prob > 90:
        result += "Market says: Very likely YES"
    elif implied_prob > 70:
        result += "Market says: Probably YES"
    elif implied_prob > 50:
        result += "Market says: Leaning YES"
    elif implied_prob > 30:
        result += "Market says: Leaning NO"
    elif implied_prob > 10:
        result += "Market says: Probably NO"
    else:
        result += "Market says: Very likely NO"

    return result
