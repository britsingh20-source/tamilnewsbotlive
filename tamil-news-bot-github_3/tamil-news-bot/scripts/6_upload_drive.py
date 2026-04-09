"""
STEP 6: Upload Videos to Google Drive
=======================================
- Uploads all rendered videos to Google Drive
- Sets each file to publicly shareable (anyone with link can download)
- Saves shareable links to a JSON manifest
- Uses Google Drive API with service account (no OAuth needed)
"""

import json, os, sys
from datetime import datetime

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
except ImportError:
    print("ERROR: google-api-python-client not installed.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPTS_DIR = os.path.dirname(__file__)
VIDEO_DIR   = os.path.join(SCRIPTS_DIR, "../output/videos")
LOGS_DIR    = os.path.join(SCRIPTS_DIR, "../logs")

# Google Drive folder name to upload into (will be created if not exists)
DRIVE_FOLDER_NAME = "TamilNewsBot"

# Service account JSON — passed via environment variable
SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")

SCOPES = ["https://www.googleapis.com/auth/drive"]


# ===========================================================================
# Authenticate
# ===========================================================================
def get_drive_service():
    if not SERVICE_ACCOUNT_JSON:
        print("ERROR: GOOGLE_SERVICE_ACCOUNT_JSON env var not set")
        sys.exit(1)

    import tempfile
    # Write JSON to temp file (service account needs a file path)
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    tmp.write(SERVICE_ACCOUNT_JSON)
    tmp.close()

    credentials = service_account.Credentials.from_service_account_file(
        tmp.name, scopes=SCOPES
    )
    os.unlink(tmp.name)

    service = build("drive", "v3", credentials=credentials)
    print("  [Drive] Authenticated via service account")
    return service


# ===========================================================================
# Get or create folder in Drive
# ===========================================================================
def get_or_create_folder(service, folder_name: str) -> str:
    # Search for existing folder
    query = (
        f"name='{folder_name}' "
        f"and mimeType='application/vnd.google-apps.folder' "
        f"and trashed=false"
    )
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files   = results.get("files", [])

    if files:
        folder_id = files[0]["id"]
        print(f"  [Drive] Using existing folder: {folder_name} ({folder_id})")
        return folder_id

    # Create new folder
    folder_meta = {
        "name":     folder_name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    folder = service.files().create(body=folder_meta, fields="id").execute()
    folder_id = folder["id"]
    print(f"  [Drive] Created folder: {folder_name} ({folder_id})")

    # Make folder itself publicly viewable
    service.permissions().create(
        fileId=folder_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()

    return folder_id


# ===========================================================================
# Upload one video and return shareable link
# ===========================================================================
def upload_video(service, file_path: str, folder_id: str) -> dict:
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path) / 1024 / 1024

    print(f"  [Drive] Uploading: {file_name} ({file_size:.1f} MB)...")

    file_meta = {
        "name":    file_name,
        "parents": [folder_id],
    }
    media = MediaFileUpload(file_path, mimetype="video/mp4", resumable=True)

    uploaded = service.files().create(
        body=file_meta,
        media_body=media,
        fields="id, name, size",
    ).execute()

    file_id = uploaded["id"]

    # Set permission: anyone with link can view/download
    service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()

    # Build shareable links
    view_link     = f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
    download_link = f"https://drive.google.com/uc?export=download&id={file_id}"

    print(f"  [Drive] ✅ Uploaded: {file_name}")
    print(f"  [Drive]    View:     {view_link}")
    print(f"  [Drive]    Download: {download_link}")

    return {
        "file_name":     file_name,
        "file_id":       file_id,
        "size_mb":       round(file_size, 1),
        "view_link":     view_link,
        "download_link": download_link,
    }


# ===========================================================================
# Entry point
# ===========================================================================
def main():
    print("=" * 65)
    print("Step 6: Upload Videos to Google Drive")
    print("=" * 65)
    print(f"Time      : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Video dir : {VIDEO_DIR}")

    # Load video manifest
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

    # Authenticate
    service = get_drive_service()

    # Get/create folder
    folder_id = get_or_create_folder(service, DRIVE_FOLDER_NAME)

    # Upload each video
    uploaded = []
    for v in videos:
        video_path = v.get("video_file", "")
        if not os.path.exists(video_path):
            print(f"  SKIP: file not found: {video_path}")
            continue
        try:
            result = upload_video(service, video_path, folder_id)
            result["topic"] = v.get("topic", "")
            uploaded.append(result)
        except Exception as e:
            print(f"  ERROR uploading {video_path}: {e}")

    # Save results
    os.makedirs(LOGS_DIR, exist_ok=True)
    output = {
        "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "folder_name": DRIVE_FOLDER_NAME,
        "folder_id":   folder_id,
        "count":       len(uploaded),
        "videos":      uploaded,
    }

    links_path = os.path.join(LOGS_DIR, "drive_links.json")
    with open(links_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*65}")
    print(f"DONE: {len(uploaded)}/{len(videos)} videos uploaded to Google Drive")
    print(f"Links saved to: {links_path}")
    print(f"\n📁 Folder: https://drive.google.com/drive/folders/{folder_id}")
    print("\n📋 Shareable download links:")
    for v in uploaded:
        print(f"  • {v['topic'][:50]}")
        print(f"    {v['download_link']}")


if __name__ == "__main__":
    main()
