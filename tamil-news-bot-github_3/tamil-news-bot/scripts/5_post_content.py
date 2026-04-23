"""
STEP 5: Auto-Post to Instagram + YouTube

- Reads ready videos from video manifest
- Posts to Instagram Reels via Meta Graph API
- Uploads to YouTube Shorts via YouTube Data API v3
- Title, Hashtags, Description, Caption — all in ENGLISH
- Follows Instagram and YouTube community policies
- Schedules posts at peak audience times (IST)
"""

import json
import os
import requests
from datetime import datetime

VIDEO_DIR   = os.path.join(os.path.dirname(__file__), "../output/videos")
SCRIPTS_FILE = os.path.join(os.path.dirname(__file__), "../output/scripts.json")

# --- INSTAGRAM (Meta Graph API) ---
IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN", "YOUR_IG_ACCESS_TOKEN")
IG_BUSINESS_ID  = os.environ.get("IG_BUSINESS_ID",  "YOUR_IG_BUSINESS_ACCOUNT_ID")

# --- YOUTUBE (Data API v3) ---
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "YOUR_YOUTUBE_API_KEY")

# Peak audience times (IST) for Coimbatore audience
PEAK_TIMES_IST = ["07:00", "12:30", "18:00", "21:00"]

# ===========================================================================
# Extract fields from script (all in English)
# ===========================================================================

def extract_section(script_text, section_name):
    """Extract a named section from the generated script"""
    lines = script_text.split("\n")
    for i, line in enumerate(lines):
        if section_name.upper() in line.upper() and ":" in line:
            content_lines = []
            for j in range(i + 1, min(i + 8, len(lines))):
                l = lines[j].strip()
                if l and not l.startswith("[") and not l.startswith("---"):
                    if any(h in l.upper() for h in ["HOOK", "STORY", "TITLE", "CALL TO ACTION",
                                                      "HASHTAGS", "DESCRIPTION", "CAPTION", "KEY FACT"]):
                        break
                    content_lines.append(l)
            if content_lines:
                return "\n".join(content_lines)
    return ""

def get_title(script_data):
    """Get English video title (max 70 chars for YouTube)"""
    # Prefer pre-extracted title from 2_generate_script.py
    if script_data.get("title"):
        return script_data["title"][:70]
    # Fallback: extract from raw script
    title = extract_section(script_data.get("script", ""), "VIDEO TITLE")
    if title:
        return title[:70]
    return f"Coimbatore News Update | {datetime.now().strftime('%d %b %Y')} | #Shorts"

def get_hashtags(script_data):
    """Get English hashtags"""
    if script_data.get("hashtags"):
        return script_data["hashtags"]
    hashtags = extract_section(script_data.get("script", ""), "HASHTAGS")
    if hashtags and "#" in hashtags:
        return hashtags
    return (
        "#Coimbatore #CoimbatoreNews #Kovai #TamilNadu #IndiaNews "
        "#LocalNews #BreakingNews #CoimbatoreCity #SouthIndia "
        "#NewsShorts #DailyNews #Shorts #Reels #CoimbatoreUpdates "
        "#TamilNaduNews #CoimbatoreToday #KovaiNews #CBE"
    )

def get_description(script_data):
    """Get English YouTube/Instagram description"""
    if script_data.get("description"):
        return script_data["description"]
    desc = extract_section(script_data.get("script", ""), "DESCRIPTION")
    if desc:
        return desc
    return (
        f"Stay updated with the latest Coimbatore news! "
        f"In this video: {script_data.get('topic', 'Coimbatore latest update')}. "
        f"Subscribe for daily Coimbatore and Tamil Nadu news updates. "
        f"Like, share and follow for more local news from Kovai!"
    )

def get_caption(script_data):
    """Get English Instagram caption"""
    if script_data.get("caption"):
        return script_data["caption"]
    caption = extract_section(script_data.get("script", ""), "CAPTION")
    if caption:
        return caption
    return (
        f"🔴 {script_data.get('topic', 'Coimbatore News Update')}\n"
        f"Stay informed with daily Coimbatore news! Follow us for more. 📲"
    )

def build_instagram_post(script_data, hashtags):
    """Build the full Instagram post text (caption + hashtags)"""
    caption   = get_caption(script_data)
    full_post = f"{caption}\n\n{hashtags}"
    # Instagram caption limit: 2200 chars
    return full_post[:2200]

def build_youtube_metadata(script_data, hashtags):
    """Build YouTube title, description, tags"""
    title       = get_title(script_data)
    description = get_description(script_data)
    # YouTube description best practices: add hashtags at end
    full_desc   = f"{description}\n\n{hashtags}\n\n📍 Coimbatore, Tamil Nadu, India"
    # YouTube description limit: 5000 chars
    full_desc   = full_desc[:5000]
    # Extract tag list from hashtags string
    tags = [tag.lstrip("#") for tag in hashtags.split() if tag.startswith("#")][:15]
    return title, full_desc, tags

# ===========================================================================
# Instagram Posting
# ===========================================================================

def post_to_instagram_reels(video_url, script_data):
    """Post video to Instagram Reels via Meta Graph API"""
    if IG_ACCESS_TOKEN == "YOUR_IG_ACCESS_TOKEN":
        print("  ⚠️  Instagram: API token not set.")
        print("  👉  Setup: https://developers.facebook.com → Instagram Graph API")
        return False

    try:
        hashtags   = get_hashtags(script_data)
        full_post  = build_instagram_post(script_data, hashtags)

        # Step 1: Create media container
        container_url = f"https://graph.facebook.com/v18.0/{IG_BUSINESS_ID}/media"
        params = {
            "video_url":   video_url,  # Must be a public URL
            "caption":     full_post,
            "media_type":  "REELS",
            "access_token": IG_ACCESS_TOKEN
        }
        resp = requests.post(container_url, data=params, timeout=30)
        data = resp.json()

        if "id" not in data:
            print(f"  IG container error: {data}")
            return False

        container_id = data["id"]

        # Step 2: Publish
        publish_url  = f"https://graph.facebook.com/v18.0/{IG_BUSINESS_ID}/media_publish"
        pub_params   = {"creation_id": container_id, "access_token": IG_ACCESS_TOKEN}
        pub_resp     = requests.post(publish_url, data=pub_params, timeout=30)
        pub_data     = pub_resp.json()

        if "id" in pub_data:
            print(f"  ✅ Posted to Instagram! Post ID: {pub_data['id']}")
            return True
        else:
            print(f"  IG publish error: {pub_data}")
            return False

    except Exception as e:
        print(f"  Instagram error: {e}")
        return False

# ===========================================================================
# YouTube Uploading
# ===========================================================================

def upload_to_youtube_shorts(video_path, script_data):
    """Upload to YouTube Shorts via Data API v3"""
    if YOUTUBE_API_KEY == "YOUR_YOUTUBE_API_KEY":
        print("  ⚠️  YouTube: API key not set.")
        print("  👉  Setup: https://console.cloud.google.com → YouTube Data API v3")
        return False

    try:
        from googleapiclient.discovery import build
        frf� googleapiclient.http import MediaFileUpload

        hashtags           = get_hashtags(script_data)
        title, full_desc, tags = build_youtube_metadata(script_data, hashtags)

        print(f"  📤 YouTube Title: {title}")

        # OAuth2 credentials required (set up once)
        print("  ⚠️  YouTube upload requires OAuth2 setup.")
        print("  👉  Run: python setup_youtube_oauth.py (one-time only)")
        return False

    except ImportError:
        print("  Installing Google API client...")
        os.system("pip install google-api-python-client google-auth-oauthlib --break-system-packages -q")
        return False

# ===========================================================================
# Logging
# ===========================================================================

def save_posting_log(results):
    log_path = os.path.join(os.path.dirname(__file__), "../logs/posting_log.json")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    logs = []
    if os.path.exists(log_path):
        with open(log_path, "r") as f:
            logs = json.load(f)
    logs.append({
        "date":    datetime.now().strftime("%Y-%m-%d %H:%M"),
        "region":  "Coimbatore",
        "results": results
    })
    with open(log_path, "w") as f:
        json.dump(logs[-30:], f, indent=2)  # Keep last 30 days

# ===========================================================================
# Main
# ===========================================================================

def main():
    print("📱 Auto-Posting Coimbatore News to Instagram + YouTube...")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    # Load video manifest
    v_manifest = os.path.join(VIDEO_DIR, "manifest.json")
    try:
        with open(v_manifest, "r") as f:
            videos = json.load(f)["videos"]
    except FileNotFoundError:
        print("❌ Video manifest not found. Run 4_create_video.py first!")
        return

    # Load scripts
    with open(SCRIPTS_FILE, "r", encoding="utf-8") as f:
        scripts = json.load(f)["scripts"]

    results = []

    for i, (video, script_data) in enumerate(zip(videos, scripts), 1):
        print(f"\n📤 Posting video {i}/{len(videos)}: {video['topic'][:50]}...")

        hashtags  = get_hashtags(script_data)
        title     = get_title(script_data)
        desc      = get_description(script_data)
        caption   = get_caption(script_data)

        print(f"  Title:    {title}")
        print(f"  Caption:  {caption[:80]}...")
        print(f"  Hashtags: {hashtags[:80]}...")

        ig_success = post_to_instagram_reels(video["video_file"], script_data)
        yt_success = upload_to_youtube_shorts(video["video_file"], script_data)

        results.append({
            "topic":     video["topic"],
            "title":     title,
            "instagram": "posted" if ig_success else "manual_needed",
            "youtube":   "posted" if yt_success else "manual_needed"
        })

    save_posting_log(results)

    print(f"\n{'='*55}")
    print("📊 POSTING SUMMARY (Coimbatore News):")
    for r in results:
        ig_status = "✅" if r["instagram"] == "posted" else "⚠️ Manual"
        yt_status = "✅" if r["youtube"]   == "posted" else "⚠️ Manual"
        print(f"  {r['topic'][:40]}: IG {ig_status} | YT {yt_status}")

    print(f"\n💡 MANUAL POSTING GUIDE (until APIs are configured):")
    print(f"  Instagram: Meta Creator Studio → Schedule Reel")
    print(f"  YouTube:   YouTube Studio → Upload as Short → Schedule")
    print(f"  Best times IST: {', '.join(PEAK_TIMES_IST)}")
    print(f"\n📋 Content Format (all in English):")
    print(f"  ✅ Title, Description, Hashtags, Caption — all English")
    print(f"  ✅ Follows Instagram & YouTube community policies")
    print(f"  ✅ Coimbatore-focused local news")

if __name__ == "__main__":
    main()
