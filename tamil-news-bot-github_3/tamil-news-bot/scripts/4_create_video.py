"""
STEP 1: Find Trending Tamil News Topics
- Uses RSS feeds from BBC Tamil, NewsMinute, OneIndia Tamil, Dinamalar, Times of India
- No API key needed - completely free
- Saves top 5 topics to topics.json
- v9: Also captures article image URLs from RSS enclosures/media tags for blue screen display
"""

import json
import os
import requests
import re
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

# XML namespaces for media/enclosure tags
NS = {
    "media":   "http://search.yahoo.com/mrss/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "enclosure": ""
}


def _extract_image_url(item, ns=""):
    """
    Try to extract article image URL from RSS item in multiple ways:
      1. <media:thumbnail> or <media:content> (Yahoo Media RSS)
      2. <enclosure> with image type
      3. First <img src=> found in description HTML
    Returns URL string or "".
    """
    # 1. media:thumbnail or media:content
    for tag in ["media:thumbnail", "media:content"]:
        try:
            el = item.find(tag, {"media": "http://search.yahoo.com/mrss/"})
            if el is not None:
                url = el.get("url", "")
                if url: return url
        except Exception:
            pass
        # Try with explicit namespace
        for ns_uri in ["http://search.yahoo.com/mrss/", "http://www.rssboard.org/media-rss"]:
            try:
                el = item.find("{" + ns_uri + "}" + tag.split(":")[-1])
                if el is not None:
                    url = el.get("url", "")
                    if url: return url
            except Exception:
                pass

    # 2. enclosure with image
    enc = item.find("enclosure")
    if enc is not None:
        enc_type = enc.get("type", "")
        enc_url  = enc.get("url", "")
        if "image" in enc_type and enc_url:
            return enc_url

    # 3. First img in description
    desc = item.findtext("description", "")
    if desc:
        match = re.search(r'<img[^>]+src=["\'](https?://[^"\' >]+)["\'\s]', desc)
        if match:
            return match.group(1)

    return ""


def fetch_rss_feed(feed):
    """Fetch and parse a single RSS feed, including article image URLs."""
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
            desc  = item.findtext("description", "").strip()
            link  = item.findtext("link", "").strip()

            if title and len(title) > 10:
                # Clean HTML from description
                clean_desc = re.sub(r'<[^>]+>', '', desc)[:300]
                # Get article image URL
                img_url = _extract_image_url(item)

                topics.append({
                    "title":             title,
                    "description":       clean_desc,
                    "source":            feed["name"],
                    "url":               link,
                    "article_image_url": img_url
                })

        print(f"  + {feed['name']}: Found {len(topics)} topics")
    except Exception as e:
        print(f"  ! {feed['name']}: {e}")

    return topics


def get_fallback_topics():
    """Hardcoded trending topics as last resort."""
    print("  Using fallback trending topics...")
    return [
        {
            "title":             "India Economy News Today",
            "description":       "India economy growth new announcement affecting common people",
            "source":            "Fallback",
            "url":               "",
            "article_image_url": ""
        },
        {
            "title":             "Tamil Nadu Weather Update",
            "description":       "Tamil Nadu weather change warning issued by meteorological department",
            "source":            "Fallback",
            "url":               "",
            "article_image_url": ""
        },
        {
            "title":             "Petrol Diesel Price Today",
            "description":       "Petrol diesel price today in Tamil Nadu latest update",
            "source":            "Fallback",
            "url":               "",
            "article_image_url": ""
        },
        {
            "title":             "India Cricket Match Latest",
            "description":       "India cricket team wins important match latest sports news",
            "source":            "Fallback",
            "url":               "",
            "article_image_url": ""
        },
        {
            "title":             "Tamil Nadu Politics Today",
            "description":       "Tamil Nadu politics government latest news update today",
            "source":            "Fallback",
            "url":               "",
            "article_image_url": ""
        },
    ]


def main():
    print("Finding Tamil News Topics...")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    os.makedirs(os.path.dirname(TOPICS_FILE), exist_ok=True)

    all_topics = []
    for feed in RSS_FEEDS:
        topics = fetch_rss_feed(feed)
        all_topics.extend(topics)

    if not all_topics:
        all_topics = get_fallback_topics()

    # Deduplicate by title
    seen   = set()
    unique = []
    for t in all_topics:
        title_lower = t["title"].lower()[:50]
        if title_lower not in seen:
            seen.add(title_lower)
            unique.append(t)

    # Save top 5 topics
    final_topics = unique[:5]

    data = {
        "topics":       final_topics,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_found":  len(all_topics)
    }

    with open(TOPICS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n+ {len(final_topics)} topics saved to: {TOPICS_FILE}")
    print(f"\n--- Topics Preview ---")
    for i, t in enumerate(final_topics, 1):
        print(f"  {i}. [{t['source']}] {t['title'][:60]}")
        if t.get('article_image_url'):
            print(f"     Image: {t['article_image_url'][:60]}...")


if __name__ == "__main__":
    main()
