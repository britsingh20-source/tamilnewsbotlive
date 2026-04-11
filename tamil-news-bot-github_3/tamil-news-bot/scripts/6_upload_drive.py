"""
STEP 6: Upload Videos to Cloudflare R2
========================================
- Uploads all rendered videos to Cloudflare R2 bucket
- Generates public URLs via the r2.dev public bucket URL
- Saves links to logs/drive_links.json (picked up by Step 7)
- Uses boto3 (S3-compatible) — R2 is fully S3-compatible

REQUIRED GitHub Secrets:
  R2_ACCOUNT_ID        → Cloudflare dashboard right sidebar
  R2_ACCESS_KEY_ID     → R2 → Manage R2 API Tokens → Create Token
  R2_SECRET_ACCESS_KEY → same token creation page
  R2_BUCKET_NAME       → tamil-news-bot
  R2_PUBLIC_URL        → https://pub-fcdf5dbf0c144198809ee28705191b02.r2.dev
"""

import json, os, sys
from datetime import datetime

try:
    import boto3
    from botocore.config import Config
except ImportError:
    print("boto3 not installed — installing now...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "boto3", "-q"])
    import boto3
    from botocore.config import Config

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEO_DIR   = os.path.join(SCRIPTS_DIR, "../output/videos")
LOGS_DIR    = os.path.join(SCRIPTS_DIR, "../logs")

ACCOUNT_ID  = os.environ.get("R2_ACCOUNT_ID", "")
ACCESS_KEY  = os.environ.get("R2_ACCESS_KEY_ID", "")
SECRET_KEY  = os.environ.get("R2_SECRET_ACCESS_KEY", "")
BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "tamil-news-bot")
PUBLIC_URL  = os.environ.get("R2_PUBLIC_URL",
              "https://pub-fcdf5dbf0c144198809ee28705191b02.r2.dev").rstrip("/")


# ===========================================================================
# Get R2 client (S3-compatible)
# ===========================================================================
def get_r2_client():
    if not all([ACCOUNT_ID, ACCESS_KEY, SECRET_KEY]):
        missing = [k for k, v in {
            "R2_ACCOUNT_ID":        ACCOUNT_ID,
            "R2_ACCESS_KEY_ID":     ACCESS_KEY,
            "R2_SECRET_ACCESS_KEY": SECRET_KEY,
        }.items() if not v]
        print(f"ERROR: Missing secrets: {', '.join(missing)}")
        sys.exit(1)

    endpoint = f"https://{ACCOUNT_ID}.r2.cloudflarestorage.com"
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )
    print(f"  [R2] Authenticated → bucket: {BUCKET_NAME}")
    return client


# ===========================================================================
# Upload one video
# ===========================================================================
def upload_video(client, file_path: str) -> dict:
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path) / 1024 / 1024
    object_key = f"TamilNewsBot/{file_name}"

    print(f"  [R2] Uploading: {file_name} ({file_size:.1f} MB)...")

    client.upload_file(
        file_path,
        BUCKET_NAME,
        object_key,
        ExtraArgs={"ContentType": "video/mp4"},
    )

    view_link     = f"{PUBLIC_URL}/{object_key}"
    download_link = f"{PUBLIC_URL}/{object_key}"

    print(f"  [R2] ✅ Uploaded: {file_name}")
    print(f"  [R2]    URL: {view_link}")

    return {
        "file_name":     file_name,
        "object_key":    object_key,
        "size_mb":       round(file_size, 1),
        "view_link":     view_link,
        "download_link": download_link,
    }


# ===========================================================================
# Entry point
# ===========================================================================
def main():
    print("=" * 65)
    print("Step 6: Upload Videos to Cloudflare R2")
    print("=" * 65)
    print(f"Time      : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Bucket    : {BUCKET_NAME}")
    print(f"Public URL: {PUBLIC_URL}")

    manifest_path = os.path.join(VIDEO_DIR, "manifest.json")
    if not os.path.exists(manifest_path):
        print(f"ERROR: {manifest_path} not found — run 4_create_video.py first")
        sys.exit(1)

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    videos = manifest.get("videos", [])
    if not videos:
        print("No videos in manifest — nothing to upload")
        sys.exit(0)

    print(f"Videos to upload: {len(videos)}")

    client   = get_r2_client()
    uploaded = []

    for v in videos:
        video_path = v.get("video_file", "")
        if not os.path.exists(video_path):
            print(f"  SKIP: file not found: {video_path}")
            continue
        try:
            result          = upload_video(client, video_path)
            result["topic"] = v.get("topic", "")
            uploaded.append(result)
        except Exception as e:
            print(f"  ERROR uploading {video_path}: {e}")

    # Save results — same format Step 7 expects
    os.makedirs(LOGS_DIR, exist_ok=True)
    output = {
        "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "platform":    "cloudflare_r2",
        "bucket":      BUCKET_NAME,
        "count":       len(uploaded),
        "videos":      uploaded,
    }

    links_path = os.path.join(LOGS_DIR, "drive_links.json")
    with open(links_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*65}")
    print(f"DONE: {len(uploaded)}/{len(videos)} videos uploaded to Cloudflare R2")
    print(f"Links saved: {links_path}")
    for v in uploaded:
        print(f"  • {v['topic'][:55]}")
        print(f"    {v['view_link']}")


if __name__ == "__main__":
    main()
