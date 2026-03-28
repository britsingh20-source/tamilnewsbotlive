"""
STEP 1: Auto-Find Trending News
- Fetches trending topics from Google Trends (India)
- Filters for viral/high-interest stories
- Saves top 5 topics to topics.json
"""

import requests
import json
import xml.etree.ElementTree as ET
from datetime import datetime
import os

OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "../output/topics.json")

GOOGLE_TRENDS_RSS = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=IN"

INSHORTS_CATEGORIES = [
    "https://inshorts.com/api/en/news?category=all&max_limit=10&include_card_data=true",
]

def fetch_google_trends():
    """Fetch trending searches from Google Trends India RSS"""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(GOOGLE_TRENDS_RSS, headers=headers, timeout=10)
        root = ET.fromstring(resp.content)
        topics = []
        for item in root.findall(".//item"):
            title = item.find("title")
            traffic = item.find("{https://trends.google.com/trends/trendingsearches/daily}approx_traffic")
            if title is not None:
                topics.append({
                    "title": title.text,
                    "traffic": traffic.text if traffic is not None else "N/A",
                    "source": "Google Trends India"
                })
        return topics[:10]
    except Exception as e:
        print(f"Google Trends error: {e}")
        return []

def fetch_inshorts():
    """Fetch latest viral news from Inshorts API"""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(INSHORTS_CATEGORIES[0], headers=headers, timeout=10)
        data = resp.json()
        topics = []
        news_list = data.get("data", {}).get("news_list", [])
        for item in news_list[:5]:
            news = item.get("news_obj", {})
            topics.append({
                "title": news.get("title", ""),
                "description": news.get("content", ""),
                "source": "Inshorts"
            })
        return topics
    except Exception as e:
        print(f"Inshorts error: {e}")
        return []

def score_virality(topic):
    """Score topics by viral potential"""
    viral_keywords = [
        "viral", "shocking", "breaking", "exclusive", "exposed",
        "scam", "arrest", "died", "crash", "ban", "free",
        "record", "first", "biggest", "warning", "alert",
        "lockdown", "war", "explosion", "resign", "win"
    ]
    title_lower = topic["title"].lower()
    score = sum(1 for kw in viral_keywords if kw in title_lower)
    if topic.get("traffic", "N/A") != "N/A":
        try:
            traffic_str = topic["traffic"].replace("+", "").replace("K", "000").replace("M", "000000")
            score += min(int(traffic_str) // 100000, 5)
        except:
            pass
    return score

def main():
    print("🔍 Finding trending topics for Tamil News Channel...")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    all_topics = []

    print("Fetching Google Trends India...")
    trends = fetch_google_trends()
    all_topics.extend(trends)
    print(f"  Found {len(trends)} trending topics")

    print("Fetching Inshorts viral news...")
    inshorts = fetch_inshorts()
    all_topics.extend(inshorts)
    print(f"  Found {len(inshorts)} viral stories")

    # Score and sort
    for topic in all_topics:
        topic["viral_score"] = score_virality(topic)
    all_topics.sort(key=lambda x: x["viral_score"], reverse=True)

    top_5 = all_topics[:5]

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "topics": top_5
        }, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Top 5 Viral Topics Saved:\n")
    for i, t in enumerate(top_5, 1):
        print(f"  {i}. {t['title']} (score: {t['viral_score']})")

    print(f"\n📁 Saved to: {OUTPUT_FILE}")
    return top_5

if __name__ == "__main__":
    main()
