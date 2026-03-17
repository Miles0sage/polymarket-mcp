"""Polymarket edge research — combines market data with news for edge finding."""

import urllib.request
import urllib.parse
import json
import re


def research_market(question: str) -> str:
    """Research a Polymarket question using Google News + YouTube."""
    results = []
    results.append(f"Research Brief: {question}\n{'='*50}\n")

    # 1. Google News search
    results.append("NEWS:")
    try:
        encoded = urllib.parse.quote(question)
        url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            xml = resp.read().decode("utf-8", errors="ignore")

        titles = re.findall(r"<title>(.*?)</title>", xml)
        for i, title in enumerate(titles[2:7], 1):  # skip feed title + channel title
            results.append(f"  {i}. {title}")

        if len(titles) <= 2:
            results.append("  No recent news found")
    except Exception as e:
        results.append(f"  News search failed: {e}")

    # 2. YouTube search
    results.append("\nVIDEOS:")
    try:
        import scrapetube
        videos = list(scrapetube.get_search(question, limit=3))
        for i, v in enumerate(videos, 1):
            title = v.get("title", {}).get("runs", [{}])[0].get("text", "?")
            vid = v.get("videoId", "")
            results.append(f"  {i}. {title}")
            results.append(f"     https://youtube.com/watch?v={vid}")
    except Exception as e:
        results.append(f"  YouTube search failed: {e}")

    # 3. Sentiment assessment
    results.append("\nSENTIMENT:")
    news_text = " ".join(results).lower()
    positive = sum(1 for w in ["confirms", "likely", "passes", "wins", "approved", "yes"] if w in news_text)
    negative = sum(1 for w in ["unlikely", "fails", "rejects", "loses", "denied", "no"] if w in news_text)

    if positive > negative:
        results.append("  News sentiment: POSITIVE (supports YES)")
    elif negative > positive:
        results.append("  News sentiment: NEGATIVE (supports NO)")
    else:
        results.append("  News sentiment: NEUTRAL (no clear direction)")

    return "\n".join(results)


def edge_finder(markets_json: str) -> str:
    """Find mispriced markets. Input: JSON array of {question, yes_price}."""
    try:
        markets = json.loads(markets_json)
    except json.JSONDecodeError:
        return "Error: provide valid JSON array of {question, yes_price} objects"

    edges = []
    for m in markets[:10]:
        question = m.get("question", "")
        yes_price = m.get("yes_price", 0.5)
        if not question:
            continue

        # Quick news check
        try:
            encoded = urllib.parse.quote(question[:100])
            url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                xml = resp.read().decode("utf-8", errors="ignore")

            titles = re.findall(r"<title>(.*?)</title>", xml)
            news_text = " ".join(titles).lower()

            pos = sum(1 for w in ["confirms", "likely", "passes", "wins", "approved", "yes", "will"] if w in news_text)
            neg = sum(1 for w in ["unlikely", "fails", "rejects", "loses", "denied", "won't", "no"] if w in news_text)

            if pos > neg and yes_price < 0.6:
                edge = 0.7 - yes_price
                edges.append({"question": question, "price": yes_price, "edge": edge, "direction": "YES underpriced"})
            elif neg > pos and yes_price > 0.4:
                edge = yes_price - 0.3
                edges.append({"question": question, "price": yes_price, "edge": edge, "direction": "NO underpriced"})
        except Exception:
            continue

    if not edges:
        return "No obvious edges found in the provided markets."

    edges.sort(key=lambda x: -x["edge"])
    lines = ["Potential Edges Found:\n"]
    for i, e in enumerate(edges, 1):
        lines.append(f"{i}. {e['question'][:80]}")
        lines.append(f"   Price: {e['price']:.0%} | Edge: {e['edge']:.0%} | {e['direction']}")
        lines.append("")

    return "\n".join(lines)
