"""Polymarket MCP Server — AI-powered prediction market tools."""

from mcp.server.fastmcp import FastMCP


def create_server():
    mcp = FastMCP("polymarket-mcp")

    @mcp.tool()
    def search_markets(query: str, max_results: int = 10) -> str:
        """Search Polymarket for prediction markets by keyword.
        Args:
            query: Search query (e.g. 'Trump', 'Fed rate', 'Bitcoin')
            max_results: Max markets to return
        """
        try:
            from tools_markets import search_markets as _sm
            return _sm(query, max_results)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def get_market(condition_id: str) -> str:
        """Get full details of a Polymarket market.
        Args:
            condition_id: Market condition ID from search results
        """
        try:
            from tools_markets import get_market as _gm
            return _gm(condition_id)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def trending_markets(max_results: int = 10) -> str:
        """Get top Polymarket markets by trading volume."""
        try:
            from tools_markets import trending_markets as _tm
            return _tm(max_results)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def calculate_ev(yes_price: float, estimated_probability: float) -> str:
        """Calculate expected value + Kelly sizing for a Polymarket bet.
        Args:
            yes_price: Current YES price (0-1, e.g. 0.65 = 65 cents)
            estimated_probability: Your estimated true probability (0-1)
        """
        try:
            from tools_analysis import calculate_ev as _ev
            return _ev(yes_price, estimated_probability)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def kelly_size(bankroll: float, probability: float, odds: float) -> str:
        """Calculate Kelly criterion bet sizing.
        Args:
            bankroll: Total bankroll in USD
            probability: Estimated win probability (0-1)
            odds: Decimal odds (e.g. 2.5 means 2.5x payout)
        """
        try:
            from tools_analysis import kelly_size as _ks
            return _ks(bankroll, probability, odds)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def arbitrage_scan(yes_prices: str) -> str:
        """Check for arbitrage opportunities. Input comma-separated YES prices of all outcomes.
        Args:
            yes_prices: Comma-separated prices (e.g. '0.65, 0.30, 0.08')
        """
        try:
            from tools_analysis import arbitrage_scan as _arb
            return _arb(yes_prices)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def market_summary(question: str, yes_price: float, volume: float = 0, end_date: str = "") -> str:
        """Get human-readable market summary with implied probability.
        Args:
            question: Market question
            yes_price: Current YES price (0-1)
            volume: Trading volume in USD (optional)
            end_date: Resolution date (optional)
        """
        try:
            from tools_analysis import market_summary as _ms
            return _ms(question, yes_price, volume, end_date)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def research_market(question: str) -> str:
        """Research a Polymarket question — searches news + YouTube for edge finding.
        Args:
            question: The market question to research
        """
        try:
            from tools_research import research_market as _rm
            return _rm(question)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def edge_finder(markets_json: str) -> str:
        """Find mispriced Polymarket contracts using news sentiment analysis.
        Args:
            markets_json: JSON array of {question, yes_price} objects
        """
        try:
            from tools_research import edge_finder as _ef
            return _ef(markets_json)
        except Exception as e:
            return f"Error: {e}"

    return mcp


if __name__ == "__main__":
    mcp = create_server()
    mcp.run()
