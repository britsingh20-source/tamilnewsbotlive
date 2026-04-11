"""
STEP 6: Upload Videos to Cloudinary
=====================================
- Uploads all rendered videos to Cloudinary (free tier = 25GB storage)
- Gets a public playable/downloadable URL for each video
- Saves links to logs/drive_links.json
- Uses CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET
  (already in your GitHub secrets)
"""

import json, os, sys, urllib.request, urllib.parse, hmac, hashlib, time
from datetime import datetime

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEO_DIR   = os.path.join(SCRIPTS_DIR, "../output/videos")
LOGS_DIR    = os.path.join(SCRIPTS_DIR, "../logs")

CLOUD_NAME  = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
API_KEY     = os.environ.get("CLOUDINARY_API_KEY", "")
API_SECRET  = os.environ.get("CLOUDINARY_API_SECRET", "")


# ===========================================================================
# Upload one video to Cloudinary using signed upload (no SDK needed)
# ===========================================================================
def upload_video(file_path: str, folder: str = "TamilNewsBot") -> dict:
    file_name  = os.path.basename(file_path)
    file_size  = os.path.getsize(file_path) / 1024 / 1024
    public_id  = f"{folder}/{os.path.splitext(file_name)[0]}"
    timestamp  = str(int(time.time()))

    print(f"  [Cloudinary] Uploading: {file_name} ({file_size:.1f} MB)...")

    # Build signature
    params_to_sign = f"public_id={public_id}&timestamp={timestamp}"
    signature = hmac.new(
        API_SECRET.encode(), params_to_sign.encode(), hashlib.sha1
    ).hexdigest()

    # Multipart upload using urllib (no extra packages)
    boundary = "----CloudinaryBoundary"
    fields = {
        "api_key":   API_KEY,
        "timestamp": timestamp,
        "public_id": public_id,
        "signature": signature,
    }

    body  = b""
    for k, v in fields.items():
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()

    with open(file_path, "rb") as f:
        video_data = f.read()

    body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{file_name}\"\r\nContent-Type: video/mp4\r\n\r\n".encode()
    body += video_data
    body += f"\r\n--{boundary}--\r\n".encode()

    url = f"https://api.cloudinary.com/v1_1/{CLOUD_NAME}/video/upload"
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        raise Exception(f"HTTP {e.code}: {error_body}")

    secure_url   = result.get("secure_url", "")
    view_link    = secure_url
    download_link = secure_url.replace("/upload/", "/upload/fl_attachment/")

    print(f"  [Cloudinary] ✅ Uploaded: {file_name}")
    print(f"  [Cloudinary]    View:     {view_link}")
    print(f"  [Cloudinary]    Download: {download_link}")

    return {
        "file_name":     file_name,
        "public_id":     result.get("public_id", ""),
        "size_mb":       round(file_size, 1),
        "view_link":     view_link,
        "download_link": download_link,
    }


# ===========================================================================
# Entry point
# ===========================================================================
def main():
    print("=" * 65)
    print("Step 6: Upload Videos to Cloudinary")
    print("=" * 65)
    print(f"Time      : {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    if not all([CLOUD_NAME, API_KEY, API_SECRET]):
        missing = [k for k, v in {
            "CLOUDINARY_CLOUD_NAME":  CLOUD_NAME,
            "CLOUDINARY_API_KEY":     API_KEY,
            "CLOUDINARY_API_SECRET":  API_SECRET,
        }.items() if not v]
        print(f"ERROR: Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    print(f"Cloud     : {CLOUD_NAME}")

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

    uploaded = []
    for v in videos:
        video_path = v.get("video_file", "")
        if not os.path.exists(video_path):
            print(f"  SKIP: file not found: {video_path}")
            continue
        try:
            result          = upload_video(video_path)
            result["topic"] = v.get("topic", "")
            uploaded.append(result)
        except Exception as e:
            print(f"  ERROR uploading {video_path}: {e}")

    os.makedirs(LOGS_DIR, exist_ok=True)
    output = {
        "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "platform":    "cloudinary",
        "cloud_name":  CLOUD_NAME,
        "count":       len(uploaded),
        "videos":      uploaded,
    }

    links_path = os.path.join(LOGS_DIR, "drive_links.json")
    with open(links_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*65}")
    print(f"DONE: {len(uploaded)}/{len(videos)} videos uploaded to Cloudinary")
    print(f"Links saved: {links_path}")
    for v in uploaded:
        print(f"  • {v['topic'][:50]}")
        print(f"    {v['view_link']}")


if __name__ == "__main__":
    main()
