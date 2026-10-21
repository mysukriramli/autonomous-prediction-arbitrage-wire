#!/usr/bin/env python3
"""
Autonomous Prediction Market Arbitrage Wire
Cross-references live Polymarket odds, breaking global news, and Polygon gas fees 
to calculate executable arbitrage directives for autonomous trading agents.
"""

import os
import json
import logging
from datetime import datetime, timezone
import requests
import feedparser
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DATA_DIR = "data"
ARCHIVE_DIR = os.path.join(DATA_DIR, "archive")
os.makedirs(ARCHIVE_DIR, exist_ok=True)


class ArbitrageSignal(BaseModel):
    market_id: str
    event_title: str
    current_yes_probability: float
    market_volume_usd: float
    breaking_news_context: str
    polygon_gas_fee_usd: float
    detected_mispricing_confidence: float  # 0.0 to 100.0
    expected_value_roi: float
    agent_directive: str


def fetch_polymarket_events() -> list:
    """Source 1: Live Prediction Market Odds (Free Public Gamma API)."""
    # Fetches highly liquid, active global events
    url = "https://gamma-api.polymarket.com/events?closed=false&active=true&limit=15"
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        events = res.json()
        markets = []
        for e in events:
            # We extract the primary market for the event
            primary_market = e.get("markets", [{}])[0]
            try:
                odds = json.loads(primary_market.get("outcomePrices", '["0.5", "0.5"]'))
                yes_prob = float(odds[0])
            except:
                yes_prob = 0.5
                
            markets.append({
                "id": e.get("id"),
                "title": e.get("title"),
                "volume": float(e.get("volume", 0)),
                "yes_probability": yes_prob
            })
        return markets
    except Exception as e:
        logging.error(f"Polymarket fetch failed: {e}")
        return []


def fetch_breaking_news() -> str:
    """Source 2: Live Ground-Truth Reality (Global RSS)."""
    urls = [
        "http://feeds.bbci.co.uk/news/world/rss.xml",
        "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114"
    ]
    headlines = []
    try:
        for url in urls:
            feed = feedparser.parse(url)
            for entry in feed.entries[:8]:
                headlines.append(f"- {entry.title}: {entry.summary}")
        return "\n".join(headlines)
    except Exception as e:
        logging.error(f"News fetch failed: {e}")
        return "No recent news available."


def fetch_polygon_gas_fee() -> float:
    """Source 3: Live Blockchain Transaction Cost (Polygon Gas Station)."""
    # Predicts the USD cost of executing a trade on the Polygon network
    url = "https://gasstation.polygon.technology/v2"
    try:
        res = requests.get(url, timeout=5)
        res.raise_for_status()
        data = res.json()
        fast_gwei = data.get("fast", {}).get("maxFee", 30.0)
        # Roughly convert GWEI to USD based on an estimated MATIC/POL price (simplified for example)
        estimated_usd_cost = (fast_gwei * 21000 * 1e-9) * 0.50 
        return round(max(estimated_usd_cost, 0.01), 4)
    except Exception as e:
        logging.warning(f"Gas fetch failed: {e}")
        return 0.05


def analyze_arbitrage(markets: list, news: str, gas_fee: float) -> list:
    """The LLM Brain: Correlates the three streams to find mispriced odds."""
    api_key = os.getenv("LLM_API_KEY")
    api_base = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    if not api_key:
        return []

    system_prompt = (
        "You are an elite quantitative arbitrage agent. I will provide active prediction markets with their current 'Yes' probabilities, "
        "along with the latest breaking global news and the network gas fee. "
        "Analyze the news to see if it definitively resolves or shifts the outcome of any provided market. "
        "If the news contradicts the current market probability (e.g., news confirms X happened, but odds are only 40%), "
        "calculate the expected ROI minus the gas fee. "
        "Output JSON strictly conforming to this schema: {\"signals\": [{\"market_id\": str, \"event_title\": str, \"breaking_news_context\": str, "
        "\"detected_mispricing_confidence\": float, \"expected_value_roi\": float, \"agent_directive\": str}]}. "
        "Only output signals with a confidence > 60.0. If no arbitrage exists, return {\"signals\": []}."
    )
    
    user_prompt = f"Markets:\n{json.dumps(markets)}\n\nBreaking News:\n{news}\n\nTransaction Gas Fee: ${gas_fee}"

    try:
        res = requests.post(
            f"{api_base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": 0.0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            },
            timeout=25
        )
        data = json.loads(res.json()["choices"][0]["message"]["content"])
        
        signals = []
        for s in data.get("signals", []):
            # Match back to original market data
            market_data = next((m for m in markets if str(m["id"]) == str(s["market_id"])), None)
            if market_data:
                signals.append(ArbitrageSignal(
                    market_id=str(market_data["id"]),
                    event_title=market_data["title"],
                    current_yes_probability=market_data["yes_probability"],
                    market_volume_usd=market_data["volume"],
                    breaking_news_context=s["breaking_news_context"],
                    polygon_gas_fee_usd=gas_fee,
                    detected_mispricing_confidence=s["detected_mispricing_confidence"],
                    expected_value_roi=s["expected_value_roi"],
                    agent_directive=s["agent_directive"]
                ))
        return signals
    except Exception as e:
        logging.error(f"Arbitrage analysis failed: {e}")
        return []


def run():
    logging.info("Initiating Autonomous Arbitrage Radar...")
    
    markets = fetch_polymarket_events()
    if not markets:
        return
        
    news = fetch_breaking_news()
    gas_fee = fetch_polygon_gas_fee()
    
    signals = analyze_arbitrage(markets, news, gas_fee)
    
    # Sort by highest expected ROI
    signals.sort(key=lambda x: x.expected_value_roi, reverse=True)

    md_lines = [
        "# Autonomous Prediction Arbitrage Radar",
        "> Real-time cross-referencing of breaking news, prediction market odds, and blockchain gas fees to generate actionable trading directives.\n",
        f"**Current Network Execution Cost:** ${gas_fee} USD\n",
        "## Active Arbitrage Signals"
    ]

    for s in signals:
        md_lines.extend([
            f"### {s.event_title} (Current Odds: {s.current_yes_probability*100:.1f}%)",
            f"- **Market ID:** `{s.market_id}` | **Volume:** ${s.market_volume_usd:,.2f}",
            f"- **Mispricing Confidence:** {s.detected_mispricing_confidence}%",
            f"- **Expected ROI:** {s.expected_value_roi}%",
            f"- **News Catalyst:** {s.breaking_news_context}",
            f"- **Execution Directive:** `{s.agent_directive}`\n"
        ])

    if not signals:
        md_lines.append("_No actionable mispricings detected in the current news cycle._")

    now = datetime.now(timezone.utc)
    payload = {
        "metadata": {
            "generated_at": now.isoformat(),
            "data_sources": ["Polymarket API", "Global News RSS", "Polygon Gas Station API"],
            "network_gas_fee_usd": gas_fee,
            "schema_version": "1.0.0"
        },
        "arbitrage_signals": [s.model_dump() for s in signals]
    }

    # Save outputs
    with open(os.path.join(DATA_DIR, "today.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    with open(os.path.join(DATA_DIR, "llms.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    month_dir = os.path.join(ARCHIVE_DIR, now.strftime("%Y"), now.strftime("%m"))
    os.makedirs(month_dir, exist_ok=True)
    with open(os.path.join(month_dir, f"{now.strftime('%Y-%m-%d')}.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    logging.info(f"Arbitrage cycle complete. Found {len(signals)} actionable signals.")

if __name__ == "__main__":
    run()
