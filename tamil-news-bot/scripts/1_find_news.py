"""
STEP 1: Find Trending Tamil News Topics
- Uses RSS feeds from BBC Tamil, NewsMinute, Hindu Tamil
- No API key needed - completely free
- Saves top 5 topics to topics.json
"""

import json
import os
import requests
from datetime import datetime
import xml.etree.ElementTree as ET

TOPICS_FILE = os.path.join(os.path.dirname(__file__), "../output/topics.json")

# Free RSS feeds - no API key needed
RSS_FEEDS = [
    {
        "name": "BBC Tamil",
        "url": "https://feeds.bbci.co.uk/tamil/rss.xml"
    },
    {
        "name": "News Minute",
        "url": "https://www.thenewsminute.com/feeds/rss"
    },
    {
        "name": "OneIndia Tamil",
        "url": "https://tamil.oneindia.com/rss/tamil-news-feed.xml"
    },
    {
        "name": "Dinamalar",
        "url": "https://www.dinamalar.com/rss/news_rss.asp"
    },
    {
        "name": "Times of India India",
        "url": "https://timesofindia.indiatimes.com/rss/853121"
    },
]

def fetch_rss_feed(feed):
    """Fetch and parse a single RSS feed"""
    topics = []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"
        }
        resp = requests.get(feed["url"], headers=headers, timeout=15)
        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        items = root.findall(".//item")

        for item in items[:5]:
            title = item.findtext("title", "").strip()
            desc = item.findtext("description", "").strip()
            link = item.findtext("link", "").strip()

            if title and len(title) > 10:
                # Clean HTML from description
                import re
                desc = re.sub(r'<[^>]+>', '', desc)[:300]
                topics.append({
                    "title": title,
                    "description": desc,
                    "source": feed["name"],
                    "url": link
                })

        print(f"  ✅ {feed['name']}: Found {len(topics)} topics")
    except Exception as e:
        print(f"  ⚠️  {feed['name']}: {e}")

    return topics

def get_fallback_topics():
    """Hardcoded trending topics as last resort"""
    print("  Using fallback trending topics...")
    return [
        {
            "title": "இந்தியாவில் பொருளாதார வளர்ச்சி - புதிய அறிவிப்பு",
            "description": "India economy growth new announcement affecting common people",
            "source": "Fallback",
            "url": ""
        },
        {
            "title": "தமிழகத்தில் வானிலை மாற்றம் - எச்சரிக்கை",
            "description": "Tamil Nadu weather change warning issued by meteorological department",
            "source": "Fallback",
            "url": ""
        },
        {
            "title": "பெட்ரோல் டீசல் விலை இன்று - அதிர்ச்சி தகவல்",
            "description": "Petrol diesel price today in Tamil Nadu latest update",
            "source": "Fallback",
            "url": ""
        },
        {
            "title": "கிரிக்கெட் போட்டியில் இந்தியா அபார வெற்றி",
            "description": "India cricket team wins important match latest sports news",
            "source": "Fallback",
            "url": ""
        },
        {
            "title": "தொழில்நுட்பம் - செயற்கை நுண்ணறிவு புதிய திருப்பம்",
            "description": "Artificial intelligence technology new development affecting India",
            "source": "Fallback",
            "url": ""
        }
    ]

def main():
    print("🔍 Finding Trending Topics for Tamil News Channel...")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    os.makedirs(os.path.dirname(TOPICS_FILE), exist_ok=True)

    all_topics = []

    # Try each RSS feed
    print("📡 Fetching from RSS feeds...")
    for feed in RSS_FEEDS:
        topics = fetch_rss_feed(feed)
        all_topics.extend(topics)
        if len(all_topics) >= 10:
            break

    # Use fallback if nothing found
    if len(all_topics) == 0:
        print("\n⚠️  RSS feeds failed. Using fallback topics...")
        all_topics = get_fallback_topics()

    # Take top 5
    top_topics = all_topics[:5]

    # Save to file
    output = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "fetched_at": datetime.now().strftime("%H:%M"),
        "total_found": len(all_topics),
        "topics": top_topics
    }

    with open(TOPICS_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Top {len(top_topics)} Topics Saved:")
    for i, t in enumerate(top_topics, 1):
        print(f"  {i}. [{t['source']}] {t['title'][:60]}")
    print(f"\n📁 Saved to: {TOPICS_FILE}")

if __name__ == "__main__":
    main()
