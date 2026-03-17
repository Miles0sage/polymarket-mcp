import httpx
from typing import Dict, Any, List
import urllib.parse
import json


def search_markets(query: str, max_results: int = 10) -> str:
    """
    Search Polymarket markets by query keyword

    Args:
        query (str): Keyword to search for in question field
        max_results (int): Maximum number of results to return (default 10)

    Returns:
        str: Formatted list of matching markets with condition_id, question, prices, volume, end_date
    """
    try:
        # Using Gamma API as suggested for easier access
        gamma_url = f"https://gamma-api.polymarket.com/markets"

        with httpx.Client() as client:
            response = client.get(gamma_url)
            response.raise_for_status()

        data = response.json()

        # Filter markets by query in the question field
        matching_markets = []
        for market in data:
            if query.lower() in market.get('question', '').lower():
                matching_markets.append(market)

                # Limit results
                if len(matching_markets) >= max_results:
                    break

        if not matching_markets:
            return f"No markets found matching '{query}'"

        # Format the results
        result_lines = [f"Found {len(matching_markets)} markets matching '{query}':\n"]

        for i, market in enumerate(matching_markets, 1):
            condition_id = market.get('condition_id', 'N/A')
            question = market.get('question', 'No question')
            outcome_prices = market.get('outcomePrices', [])
            volume = market.get('volume', 'N/A')
            end_date = market.get('end_date', 'N/A')

            # Extract YES/NO prices from outcomePrices
            yes_price = "N/A"
            no_price = "N/A"
            if len(outcome_prices) >= 2:
                # Assuming first is YES, second is NO
                yes_price = f"{float(outcome_prices[0]):.4f}"
                no_price = f"{float(outcome_prices[1]):.4f}"
            elif len(outcome_prices) == 1:
                # Only one price available
                yes_price = f"{float(outcome_prices[0]):.4f}"

            result_lines.append(f"{i}. Condition ID: {condition_id}")
            result_lines.append(f"   Question: {question}")
            result_lines.append(f"   Prices: YES: {yes_price} | NO: {no_price}")
            result_lines.append(f"   Volume: {volume}")
            result_lines.append(f"   End Date: {end_date}")
            result_lines.append("")

        return "\n".join(result_lines)

    except Exception as e:
        # Fallback to CLOB API if Gamma fails
        try:
            clob_url = f"https://clob.polymarket.com/markets?next_cursor=&limit={max_results}"

            with httpx.Client() as client:
                response = client.get(clob_url)
                response.raise_for_status()

            data = response.json()

            # Filter markets by query in the question field
            matching_markets = []
            for market in data.get('data', []):
                if query.lower() in market.get('question', '').lower():
                    matching_markets.append(market)

                    # Limit results
                    if len(matching_markets) >= max_results:
                        break

            if not matching_markets:
                return f"No markets found matching '{query}'"

            # Format the results
            result_lines = [f"Found {len(matching_markets)} markets matching '{query}':\n"]

            for i, market in enumerate(matching_markets, 1):
                condition_id = market.get('condition_id', 'N/A')
                question = market.get('question', 'No question')
                tokens = market.get('tokens', [])
                volume = market.get('volume', 'N/A')
                end_date = market.get('end_date', 'N/A')

                # Extract YES/NO prices from tokens
                yes_price = "N/A"
                no_price = "N/A"

                for token in tokens:
                    if token.get('type') == 'YES':
                        yes_price = f"{float(token.get('price', 'N/A')):.4f}"
                    elif token.get('type') == 'NO':
                        no_price = f"{float(token.get('price', 'N/A')):.4f}"

                result_lines.append(f"{i}. Condition ID: {condition_id}")
                result_lines.append(f"   Question: {question}")
                result_lines.append(f"   Prices: YES: {yes_price} | NO: {no_price}")
                result_lines.append(f"   Volume: {volume}")
                result_lines.append(f"   End Date: {end_date}")
                result_lines.append("")

            return "\n".join(result_lines)

        except Exception as fallback_error:
            return f"Error searching markets: {str(e)} (fallback also failed: {str(fallback_error)})"


def get_market(condition_id: str) -> str:
    """
    Get details for a specific Polymarket market by condition_id

    Args:
        condition_id (str): The condition ID of the market to retrieve

    Returns:
        str: Formatted details of the market
    """
    try:
        # Try Gamma API first
        gamma_url = f"https://gamma-api.polymarket.com/markets"

        with httpx.Client() as client:
            response = client.get(gamma_url)
            response.raise_for_status()

        data = response.json()

        # Find the market with the matching condition_id
        market = None
        for m in data:
            if m.get('condition_id') == condition_id:
                market = m
                break

        if market:
            question = market.get('question', 'N/A')
            description = market.get('description', 'N/A')
            outcome_prices = market.get('outcomePrices', [])
            volume = market.get('volume', 'N/A')
            liquidity = market.get('liquidity', 'N/A')
            end_date = market.get('end_date', 'N/A')
            resolution_source = market.get('resolution_source', 'N/A')

            # Extract YES/NO prices
            yes_price = "N/A"
            no_price = "N/A"
            if len(outcome_prices) >= 2:
                yes_price = f"{float(outcome_prices[0]):.4f}"
                no_price = f"{float(outcome_prices[1]):.4f}"
            elif len(outcome_prices) == 1:
                yes_price = f"{float(outcome_prices[0]):.4f}"

            result = f"Market Details:\n"
            result += f"Condition ID: {condition_id}\n"
            result += f"Question: {question}\n"
            result += f"Description: {description}\n"
            result += f"YES Price: {yes_price}\n"
            result += f"NO Price: {no_price}\n"
            result += f"Volume: {volume}\n"
            result += f"Liquidity: {liquidity}\n"
            result += f"End Date: {end_date}\n"
            result += f"Resolution Source: {resolution_source}\n"

            return result

        # If not found in Gamma, try CLOB API
        clob_url = f"https://clob.polymarket.com/markets/{condition_id}"

        with httpx.Client() as client:
            response = client.get(clob_url)
            response.raise_for_status()

        market = response.json()

        question = market.get('question', 'N/A')
        description = market.get('description', 'N/A')
        tokens = market.get('tokens', [])
        volume = market.get('volume', 'N/A')
        liquidity = market.get('liquidity', 'N/A')
        end_date = market.get('end_date', 'N/A')
        resolution_source = market.get('resolution_source', 'N/A')

        # Extract YES/NO prices from tokens
        yes_price = "N/A"
        no_price = "N/A"

        for token in tokens:
            if token.get('type') == 'YES':
                yes_price = f"{float(token.get('price', 'N/A')):.4f}"
            elif token.get('type') == 'NO':
                no_price = f"{float(token.get('price', 'N/A')):.4f}"

        result = f"Market Details:\n"
        result += f"Condition ID: {condition_id}\n"
        result += f"Question: {question}\n"
        result += f"Description: {description}\n"
        result += f"YES Price: {yes_price}\n"
        result += f"NO Price: {no_price}\n"
        result += f"Volume: {volume}\n"
        result += f"Liquidity: {liquidity}\n"
        result += f"End Date: {end_date}\n"
        result += f"Resolution Source: {resolution_source}\n"

        return result

    except Exception as e:
        return f"Error getting market details: {str(e)}"


def get_prices(token_id: str) -> str:
    """
    Get current bid/ask prices for a specific token

    Args:
        token_id (str): The token ID to get prices for

    Returns:
        str: Formatted bid/ask prices
    """
    try:
        # Try CLOB API first
        clob_url = f"https://clob.polymarket.com/price?token_id={token_id}&side=buy"

        with httpx.Client() as client:
            response = client.get(clob_url)
            response.raise_for_status()

        data = response.json()

        # Extract price information
        price = data.get('price', 'N/A')

        result = f"Price Information for Token ID: {token_id}\n"
        result += f"Current Price: {price}\n"

        # Also try to get ask price (usually from selling side)
        ask_url = f"https://clob.polymarket.com/price?token_id={token_id}&side=sell"

        with httpx.Client() as client:
            ask_response = client.get(ask_url)
            ask_response.raise_for_status()

        ask_data = ask_response.json()
        ask_price = ask_data.get('price', 'N/A')

        result += f"Ask Price: {ask_price}\n"
        result += f"Bid Price: {price}\n"

        return result

    except Exception as e:
        return f"Error getting prices: {str(e)}"


def trending_markets(max_results: int = 10) -> str:
    """
    Get trending markets sorted by volume

    Args:
        max_results (int): Maximum number of results to return (default 10)

    Returns:
        str: Formatted list of trending markets
    """
    try:
        # Using Gamma API for easier access
        gamma_url = f"https://gamma-api.polymarket.com/markets"

        with httpx.Client() as client:
            response = client.get(gamma_url)
            response.raise_for_status()

        data = response.json()

        # Sort markets by volume in descending order
        sorted_markets = sorted(
            data,
            key=lambda x: float(x.get('volume', 0)) if x.get('volume') else 0,
            reverse=True
        )

        # Take the top max_results
        top_markets = sorted_markets[:max_results]

        if not top_markets:
            return "No trending markets found"

        # Format the results
        result_lines = [f"Top {len(top_markets)} trending markets by volume:\n"]

        for i, market in enumerate(top_markets, 1):
            condition_id = market.get('condition_id', 'N/A')
            question = market.get('question', 'No question')
            outcome_prices = market.get('outcomePrices', [])
            volume = market.get('volume', 'N/A')
            liquidity = market.get('liquidity', 'N/A')
            end_date = market.get('end_date', 'N/A')

            # Extract YES/NO prices from outcomePrices
            yes_price = "N/A"
            no_price = "N/A"
            if len(outcome_prices) >= 2:
                yes_price = f"{float(outcome_prices[0]):.4f}"
                no_price = f"{float(outcome_prices[1]):.4f}"
            elif len(outcome_prices) == 1:
                yes_price = f"{float(outcome_prices[0]):.4f}"

            result_lines.append(f"{i}. Condition ID: {condition_id}")
            result_lines.append(f"   Question: {question}")
            result_lines.append(f"   Prices: YES: {yes_price} | NO: {no_price}")
            result_lines.append(f"   Volume: {volume}")
            result_lines.append(f"   Liquidity: {liquidity}")
            result_lines.append(f"   End Date: {end_date}")
            result_lines.append("")

        return "\n".join(result_lines)

    except Exception as e:
        # Fallback to CLOB API with volume sorting
        try:
            clob_url = f"https://clob.polymarket.com/markets?next_cursor=&limit=20&order=volume&ascending=false"

            with httpx.Client() as client:
                response = client.get(clob_url)
                response.raise_for_status()

            data = response.json()

            markets = data.get('data', [])
            # Limit to max_results
            top_markets = markets[:max_results]

            if not top_markets:
                return "No trending markets found"

            # Format the results
            result_lines = [f"Top {len(top_markets)} trending markets by volume:\n"]

            for i, market in enumerate(top_markets, 1):
                condition_id = market.get('condition_id', 'N/A')
                question = market.get('question', 'No question')
                tokens = market.get('tokens', [])
                volume = market.get('volume', 'N/A')
                liquidity = market.get('liquidity', 'N/A')
                end_date = market.get('end_date', 'N/A')

                # Extract YES/NO prices from tokens
                yes_price = "N/A"
                no_price = "N/A"

                for token in tokens:
                    if token.get('type') == 'YES':
                        yes_price = f"{float(token.get('price', 'N/A')):.4f}"
                    elif token.get('type') == 'NO':
                        no_price = f"{float(token.get('price', 'N/A')):.4f}"

                result_lines.append(f"{i}. Condition ID: {condition_id}")
                result_lines.append(f"   Question: {question}")
                result_lines.append(f"   Prices: YES: {yes_price} | NO: {no_price}")
                result_lines.append(f"   Volume: {volume}")
                result_lines.append(f"   Liquidity: {liquidity}")
                result_lines.append(f"   End Date: {end_date}")
                result_lines.append("")

            return "\n".join(result_lines)

        except Exception as fallback_error:
            return f"Error getting trending markets: {str(e)} (fallback also failed: {str(fallback_error)})"


if __name__ == "__main__":
    # Example usage
    print("Polymarket Tools Demo")
    print("\n1. Searching for 'election' markets:")
    print(search_markets("election", 3))

    print("\n2. Getting top trending markets:")
    print(trending_markets(3))

    print("\n3. Getting a specific market (example condition_id):")
    # Note: This is just an example, replace with an actual condition_id
    # print(get_market("some-condition-id"))

    print("\n4. Getting prices for a token (example token_id):")
    # Note: This is just an example, replace with an actual token_id
    # print(get_prices("some-token-id"))