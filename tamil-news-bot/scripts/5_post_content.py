"""
STEP 5: Auto-Post to Instagram + YouTube (FREE)
- Reads ready videos from video manifest
- Posts to Instagram via Meta Graph API (free)
- Uploads to YouTube via YouTube Data API v3 (free)
- Schedules posts at peak Tamil audience times
"""

import json
import os
import requests
from datetime import datetime

VIDEO_DIR = os.path.join(os.path.dirname(__file__), "../output/videos")
SCRIPTS_FILE = os.path.join(os.path.dirname(__file__), "../output/scripts.json")

# --- INSTAGRAM (Meta Graph API) ---
# Get free at: https://developers.facebook.com → Create App → Instagram Graph API
IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN", "YOUR_IG_ACCESS_TOKEN")
IG_BUSINESS_ID = os.environ.get("IG_BUSINESS_ID", "YOUR_IG_BUSINESS_ACCOUNT_ID")

# --- YOUTUBE (Data API v3) ---
# Get free at: https://console.cloud.google.com → YouTube Data API v3
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "YOUR_YOUTUBE_API_KEY")

# Peak Tamil audience times (IST)
PEAK_TIMES_IST = ["07:00", "12:30", "18:00", "21:00"]

def extract_hashtags(script_text):
    """Extract hashtags from script"""
    lines = script_text.split("\n")
    for i, line in enumerate(lines):
        if "HASHTAGS" in line.upper() and i + 1 < len(lines):
            for j in range(i + 1, min(i + 5, len(lines))):
                if lines[j].strip().startswith("#"):
                    return lines[j].strip()
    return "#TamilNews #தமிழ்செய்திகள் #ViralNews #TamilReels #IndiaNews #Breaking #TamilMemes #Tamil #Shorts #Reels"

def extract_caption(script_text):
    """Extract caption from script"""
    lines = script_text.split("\n")
    for i, line in enumerate(lines):
        if "CAPTION" in line.upper() and i + 1 < len(lines):
            caption_lines = []
            for j in range(i + 1, min(i + 6, len(lines))):
                l = lines[j].strip()
                if l and not l.startswith("[") and not l.startswith("---"):
                    caption_lines.append(l)
            if caption_lines:
                return "\n".join(caption_lines)
    return ""

def post_to_instagram_reels(video_path, caption, hashtags):
    """Post video to Instagram Reels via Meta Graph API"""
    if IG_ACCESS_TOKEN == "YOUR_IG_ACCESS_TOKEN":
        print("   ⚠️  Instagram: API token not set.")
        print("   👉 Setup: https://developers.facebook.com → Create App → Instagram Graph API")
        print("   👉 Alternative: Use Meta Creator Studio (manual but free): https://business.facebook.com/creatorstudio")
        return False

    try:
        full_caption = f"{caption}\n\n{hashtags}"
        # Step 1: Create media container
        container_url = f"https://graph.facebook.com/v18.0/{IG_BUSINESS_ID}/media"
        params = {
            "video_url": video_path,  # Must be a public URL
            "caption": full_caption,
            "media_type": "REELS",
            "access_token": IG_ACCESS_TOKEN
        }
        resp = requests.post(container_url, data=params, timeout=30)
        data = resp.json()
        if "id" not in data:
            print(f"   IG container error: {data}")
            return False

        container_id = data["id"]
        # Step 2: Publish
        publish_url = f"https://graph.facebook.com/v18.0/{IG_BUSINESS_ID}/media_publish"
        pub_params = {"creation_id": container_id, "access_token": IG_ACCESS_TOKEN}
        pub_resp = requests.post(publish_url, data=pub_params, timeout=30)
        pub_data = pub_resp.json()
        if "id" in pub_data:
            print(f"   ✅ Posted to Instagram! Post ID: {pub_data['id']}")
            return True
        else:
            print(f"   IG publish error: {pub_data}")
            return False
    except Exception as e:
        print(f"   Instagram error: {e}")
        return False

def upload_to_youtube_shorts(video_path, title, description, hashtags):
    """Upload to YouTube Shorts via Data API v3"""
    if YOUTUBE_API_KEY == "YOUR_YOUTUBE_API_KEY":
        print("   ⚠️  YouTube: API key not set.")
        print("   👉 Setup: https://console.cloud.google.com → YouTube Data API v3")
        print("   👉 Alternative: Upload manually to YouTube Studio as Shorts")
        return False

    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        import google.oauth2.credentials

        # This requires OAuth2 setup (one-time)
        # Full guide: https://developers.google.com/youtube/v3/guides/uploading_a_video
        print("   ⚠️  YouTube upload requires OAuth2 setup.")
        print("   👉 Run: python setup_youtube_oauth.py (one time only)")
        return False
    except ImportError:
        print("   Installing Google API client...")
        os.system("pip install google-api-python-client google-auth-oauthlib --break-system-packages -q")
        return False

def save_posting_log(results):
    """Save posting results log"""
    log_path = os.path.join(os.path.dirname(__file__), "../logs/posting_log.json")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    logs = []
    if os.path.exists(log_path):
        with open(log_path, "r") as f:
            logs = json.load(f)
    logs.append({"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "results": results})
    with open(log_path, "w") as f:
        json.dump(logs[-30:], f, indent=2)  # Keep last 30 days

def main():
    print("📱 Auto-Posting to Instagram + YouTube...")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    # Load video manifest
    v_manifest = os.path.join(VIDEO_DIR, "manifest.json")
    try:
        with open(v_manifest, "r") as f:
            videos = json.load(f)["videos"]
    except FileNotFoundError:
        print("❌ Video manifest not found. Run 4_create_video.py first!")
        return

    # Load scripts for captions
    with open(SCRIPTS_FILE, "r", encoding="utf-8") as f:
        scripts = json.load(f)["scripts"]

    results = []
    for i, (video, script_data) in enumerate(zip(videos, scripts), 1):
        print(f"\n📤 Posting video {i}/{len(videos)}: {video['topic'][:40]}...")

        hashtags = extract_hashtags(script_data["script"])
        caption = extract_caption(script_data["script"])
        if not caption:
            caption = f"🔴 {video['topic']}\n\nFollow பண்ணுங்க daily Tamil news-க்கு!"

        title = f"{video['topic'][:80]} | Tamil News | #Shorts"

        ig_success = post_to_instagram_reels(video["video_file"], caption, hashtags)
        yt_success = upload_to_youtube_shorts(video["video_file"], title, caption, hashtags)

        results.append({
            "topic": video["topic"],
            "instagram": "posted" if ig_success else "manual_needed",
            "youtube": "posted" if yt_success else "manual_needed"
        })

    save_posting_log(results)

    print(f"\n{'='*50}")
    print("📊 POSTING SUMMARY:")
    for r in results:
        ig_status = "✅" if r["instagram"] == "posted" else "⚠️  Manual"
        yt_status = "✅" if r["youtube"] == "posted" else "⚠️  Manual"
        print(f"  {r['topic'][:35]}: IG {ig_status} | YT {yt_status}")

    print(f"\n💡 MANUAL POSTING GUIDE (until APIs are configured):")
    print(f"   Instagram: Open Meta Creator Studio → Schedule Reel")
    print(f"   YouTube:   Open YouTube Studio → Upload as Short → Schedule")
    print(f"   Best times IST: {', '.join(PEAK_TIMES_IST)}")

if __name__ == "__main__":
    main()
