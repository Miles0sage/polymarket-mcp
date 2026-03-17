"""Polymarket + Crypto MCP Server — prediction markets, crypto prices, edge finding."""

from mcp.server.fastmcp import FastMCP


def create_server():
    mcp = FastMCP("polymarket-mcp")

    # === Polymarket Tools ===

    @mcp.tool()
    def search_markets(query: str, max_results: int = 10) -> str:
        """Search Polymarket for active prediction markets by keyword.
        Args:
            query: Search query (e.g. 'Trump', 'Fed rate', 'Bitcoin')
            max_results: Max markets to return
        """
        from tools_markets import search_markets as _fn
        return _fn(query, max_results)

    @mcp.tool()
    def get_market(condition_id: str) -> str:
        """Get full details of a Polymarket market.
        Args:
            condition_id: Market condition ID from search results
        """
        from tools_markets import get_market as _fn
        return _fn(condition_id)

    @mcp.tool()
    def trending_markets(max_results: int = 10) -> str:
        """Get top active Polymarket markets by trading volume."""
        from tools_markets import trending_markets as _fn
        return _fn(max_results)

    @mcp.tool()
    def crypto_prediction_markets(max_results: int = 10) -> str:
        """Get active crypto-related Polymarket prediction markets (BTC, ETH, etc)."""
        from tools_markets import crypto_markets as _fn
        return _fn(max_results)

    @mcp.tool()
    def sports_prediction_markets(max_results: int = 10) -> str:
        """Get active sports prediction markets (NBA, NFL, UFC, etc)."""
        from tools_markets import sports_markets as _fn
        return _fn(max_results)

    @mcp.tool()
    def calculate_ev(yes_price: float, estimated_probability: float) -> str:
        """Calculate expected value + Kelly sizing for a Polymarket bet.
        Args:
            yes_price: Current YES price (0-1, e.g. 0.65 = 65 cents)
            estimated_probability: Your estimated true probability (0-1)
        """
        from tools_analysis import calculate_ev as _fn
        return _fn(yes_price, estimated_probability)

    @mcp.tool()
    def kelly_size(bankroll: float, probability: float, odds: float) -> str:
        """Calculate Kelly criterion bet sizing.
        Args:
            bankroll: Total bankroll in USD
            probability: Estimated win probability (0-1)
            odds: Decimal odds (e.g. 2.5 means 2.5x payout)
        """
        from tools_analysis import kelly_size as _fn
        return _fn(bankroll, probability, odds)

    @mcp.tool()
    def arbitrage_scan(yes_prices: str) -> str:
        """Check for arbitrage across Polymarket outcomes. Input comma-separated YES prices.
        Args:
            yes_prices: Comma-separated prices (e.g. '0.65, 0.30, 0.08')
        """
        from tools_analysis import arbitrage_scan as _fn
        return _fn(yes_prices)

    @mcp.tool()
    def market_summary(question: str, yes_price: float, volume: float = 0, end_date: str = "") -> str:
        """Human-readable market summary with implied probability.
        Args:
            question: Market question
            yes_price: Current YES price (0-1)
            volume: Trading volume in USD (optional)
            end_date: Resolution date (optional)
        """
        from tools_analysis import market_summary as _fn
        return _fn(question, yes_price, volume, end_date)

    @mcp.tool()
    def research_market(question: str) -> str:
        """Research a prediction market question — news + YouTube + sentiment for edge finding.
        Args:
            question: The market question to research
        """
        from tools_research import research_market as _fn
        return _fn(question)

    @mcp.tool()
    def edge_finder(markets_json: str) -> str:
        """Find mispriced Polymarket contracts using news sentiment analysis.
        Args:
            markets_json: JSON array of [{question, yes_price}] objects
        """
        from tools_research import edge_finder as _fn
        return _fn(markets_json)

    # === Edge Alerts ===

    @mcp.tool()
    def scan_edges(min_edge: float = 0.05, min_volume: float = 10000) -> str:
        """Scan all active Polymarket markets for mispriced edges using volume/liquidity heuristics.
        Args:
            min_edge: Minimum edge to report (0-1, e.g. 0.05 = 5%)
            min_volume: Minimum USD volume to consider a market
        """
        from tools_alerts import scan_edges as _fn
        return _fn(min_edge, min_volume)

    @mcp.tool()
    def whale_activity() -> str:
        """Check top 10 Polymarket whale traders and cross-reference with current edge signals."""
        from tools_alerts import check_whale_activity as _fn
        return _fn()

    # === Paper Trading Tools ===

    @mcp.tool()
    def paper_trade(
        market_id: str,
        side: str,
        amount: float,
        yes_price: float,
        question: str = "",
        estimated_probability: float = 0.0,
        bankroll: float = 0.0,
    ) -> str:
        """Place a simulated paper trade on a Polymarket outcome.
        Args:
            market_id: Market condition ID or slug
            side: 'YES' or 'NO'
            amount: Dollar amount to wager (max $100)
            yes_price: Current YES price (0-1)
            question: Market question (optional)
            estimated_probability: Your true probability estimate for Kelly check (optional)
            bankroll: Total bankroll for Kelly sizing (optional)
        """
        from tools_trading import paper_trade as _fn
        return _fn(market_id, side, amount, yes_price, question, estimated_probability, bankroll)

    @mcp.tool()
    def paper_portfolio() -> str:
        """Show all open paper trading positions with unrealised P&L."""
        from tools_trading import paper_portfolio as _fn
        return _fn()

    @mcp.tool()
    def paper_settle(trade_id: int, outcome: str) -> str:
        """Manually settle a paper trade as WIN or LOSE.
        Args:
            trade_id: Trade ID to settle
            outcome: 'WIN' or 'LOSE'
        """
        from tools_trading import paper_settle as _fn
        return _fn(trade_id, outcome)

    @mcp.tool()
    def paper_history() -> str:
        """Full paper trade history with win rate and total P&L."""
        from tools_trading import paper_history as _fn
        return _fn()

    @mcp.tool()
    def get_orderbook(token_id: str) -> str:
        """Fetch live orderbook (bids/asks/spread) from Polymarket CLOB.
        Args:
            token_id: CLOB token ID for the outcome
        """
        from tools_trading import get_orderbook as _fn
        return _fn(token_id)

    # === Crypto Tools ===

    @mcp.tool()
    def crypto_prices(symbols: str = "BTC,ETH,SOL,DOGE,XRP") -> str:
        """Get live crypto prices from Binance with 24h change and volume.
        Args:
            symbols: Comma-separated symbols (e.g. 'BTC,ETH,SOL')
        """
        from tools_crypto import get_crypto_prices as _fn
        return _fn(symbols)

    @mcp.tool()
    def crypto_overview() -> str:
        """Top 20 crypto by volume — prices, 24h change, volume."""
        from tools_crypto import crypto_market_overview as _fn
        return _fn()

    @mcp.tool()
    def crypto_fear_greed() -> str:
        """Bitcoin Fear & Greed Index — 7-day history with trading signals."""
        from tools_crypto import crypto_fear_greed as _fn
        return _fn()

    @mcp.tool()
    def crypto_vs_predictions(crypto_symbol: str = "BTC") -> str:
        """Compare live crypto price with related Polymarket prediction markets.
        Args:
            crypto_symbol: Crypto symbol (e.g. 'BTC', 'ETH', 'SOL')
        """
        from tools_crypto import crypto_vs_polymarket as _fn
        return _fn(crypto_symbol)

    return mcp


if __name__ == "__main__":
    mcp = create_server()
    mcp.run()
