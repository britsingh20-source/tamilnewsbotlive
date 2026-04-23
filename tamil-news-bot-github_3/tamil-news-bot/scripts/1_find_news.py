"""
STEP 1: Find Trending Coimbatore News Topics

- Fetches Coimbatore-specific news from RSS feeds and Google News
- Filters for Coimbatore-relevant content
- Saves top 5 topics to topics.json
"""

import json
import os
import requests
import re
from datetime import datetime
import xml.etree.ElementTree as ET

TOPICS_FILE = os.path.join(os.path.dirname(__file__), "../output/topics.json")

# Coimbatore-focused RSS / Google News feeds
RSS_FEEDS = [
    {
        "name": "Google News - Coimbatore",
        "url": "https://news.google.com/rss/search?q=Coimbatore&hl=en-IN&gl=IN&ceid=IN:en"
    },
    {
        "name": "Google News - Coimbatore Tamil",
        "url": "https://news.google.com/rss/search?q=Coimbatore+Tamil+Nadu&hl=en-IN&gl=IN&ceid=IN:en"
    },
    {
        "name": "Times of India - Coimbatore",
        "url": "https://timesofindia.indiatimes.com/rss/2647163.cms"
    },
    {
        "name": "The Hindu - Coimbatore",
        "url": "https://www.thehindu.com/news/cities/Coimbatore/feeder/default.rss"
    },
    {
        "name": "Dinamalar - Tamil Nadu",
        "url": "https://www.dinamalar.com/rss/news_rss.asp"
    },
]

# Keywords to confirm Coimbatore relevance
COIMBATORE_KEYWORDS = [
    "coimbatore", "kovai", "கோயம்புத்தூர்", "கோவை",
    "tirupur", "pollachi", "mettupalayam", "ooty", "nilgiris",
    "erode", "salem", "cbepmc", "ukkadam"
]

def is_coimbatore_related(title, description=""):
    """Check if the article is about Coimbatore or nearby region"""
    text = (title + " " + description).lower()
    return any(kw.lower() in text for kw in COIMBATORE_KEYWORDS)

def clean_html(text):
    """Strip HTML tags and clean whitespace"""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:300]

def fetch_rss_feed(feed):
    """Fetch and parse a single RSS feed, filter for Coimbatore content"""
    topics = []
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; CoimbatoreNewsBot/1.0)"}
        resp = requests.get(feed["url"], headers=headers, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        items = root.findall(".//item")

        for item in items[:20]:  # scan more items to find Coimbatore ones
            title = item.findtext("title", "").strip()
            desc = item.findtext("description", "").strip()
            link = item.findtext("link", "").strip()

            if not title or len(title) < 10:
                continue

            desc_clean = clean_html(desc)

            # For Google News feeds, accept all (already filtered by query)
            # For other feeds, check Coimbatore relevance
            if "google.com/rss/search" in feed["url"] or is_coimbatore_related(title, desc_clean):
                topics.append({
                    "title": title,
                    "description": desc_clean,
                    "source": feed["name"],
                    "url": link
                })

            if len(topics) >= 5:
                break

        print(f"  ✅ {feed['name']}: Found {len(topics)} Coimbatore topics")

    except Exception as e:
        print(f"  ⚠️ {feed['name']}: {e}")

    return topics

def get_fallback_topics():
    """Hardcoded Coimbatore fallback topics"""
    print("  Using Coimbatore fallback topics...")
    return [
        {
            "title": "Coimbatore Smart City Project New Infrastructure Update",
            "description": "Coimbatore Smart City Mission latest infrastructure development and road improvement projects announced",
            "source": "Fallback",
            "url": ""
        },
        {
            "title": "Coimbatore Weather Alert - IMD Issues Warning",
            "description": "India Meteorological Department issues weather alert for Coimbatore and nearby districts",
            "source": "Fallback",
            "url": ""
        },
        {
            "title": "Coimbatore Textile Industry Boom - New Export Records",
            "description": "Coimbatore textile and knitwear industry achieves new export milestone boosting local economy",
            "source": "Fallback",
            "url": ""
        },
        {
            "title": "Coimbatore Traffic Regulation - New One-Way System Announced",
            "description": "Coimbatore city police announce new traffic management rules to ease congestion in key areas",
            "source": "Fallback",
            "url": ""
        },
        {
            "title": "PSG College Coimbatore Achieves National Ranking",
            "description": "Coimbatore educational institutions secure top spots in national rankings for academic excellence",
            "source": "Fallback",
            "url": ""
        }
    ]

def main():
    print("🔍 Finding Trending Coimbatore News Topics...")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    os.makedirs(os.path.dirname(TOPICS_FILE), exist_ok=True)

    all_topics = []

    print("📡 Fetching from RSS feeds (Coimbatore filter active)...")
    for feed in RSS_FEEDS:
        topics = fetch_rss_feed(feed)
        # Deduplicate by title
        existing_titles = {t["title"].lower() for t in all_topics}
        for t in topics:
            if t["title"].lower() not in existing_titles:
                all_topics.append(t)
                existing_titles.add(t["title"].lower())
        if len(all_topics) >= 10:
            break

    if len(all_topics) == 0:
        print("\n⚠️ RSS feeds failed. Using fallback topics...")
        all_topics = get_fallback_topics()

    # Take top 5
    top_topics = all_topics[:5]

    output = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "fetched_at": datetime.now().strftime("%H:%M"),
        "region": "Coimbatore",
        "total_found": len(all_topics),
        "topics": top_topics
    }

    with open(TOPICS_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Top {len(top_topics)} Coimbatore Topics Saved:")
    for i, t in enumerate(top_topics, 1):
        print(f"  {i}. [{t['source']}] {t['title'][:60]}")

    print(f"\n📁 Saved to: {TOPICS_FILE}")

if __name__ == "__main__":
    main()
