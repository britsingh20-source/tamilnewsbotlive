"""
STEP 6: Upload Videos to Google Drive
=======================================
- Uploads into a user-owned folder shared with the service account
  (avoids the "Service Accounts have no storage quota" 403 error)
- Sets each file to publicly shareable (anyone with link)
- Saves shareable links to logs/drive_links.json
"""

import json, os, sys
from datetime import datetime

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
except ImportError:
    print("ERROR: pip install google-api-python-client google-auth")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEO_DIR   = os.path.join(SCRIPTS_DIR, "../output/videos")
LOGS_DIR    = os.path.join(SCRIPTS_DIR, "../logs")

# ---------------------------------------------------------------------------
# Folder resolution (priority order):
#   1. GOOGLE_DRIVE_FOLDER_ID env var  ← YOUR shared folder ID  ✅ use this
#   2. Create a new folder (fails for service accounts without quota)
# ---------------------------------------------------------------------------
DRIVE_FOLDER_ID   = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "")
DRIVE_FOLDER_NAME = "TamilNewsBot"   # used only if creating a new folder

SCOPES = ["https://www.googleapis.com/auth/drive"]


# ===========================================================================
# Authenticate — file path OR raw JSON string
# ===========================================================================
def get_drive_service():
    sa_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "")
    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")

    if sa_file and os.path.exists(sa_file):
        creds = service_account.Credentials.from_service_account_file(
            sa_file, scopes=SCOPES
        )
        print(f"  [Drive] Authenticated via file: {sa_file}")
    elif sa_json:
        import tempfile
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        tmp.write(sa_json)
        tmp.close()
        creds = service_account.Credentials.from_service_account_file(
            tmp.name, scopes=SCOPES
        )
        os.unlink(tmp.name)
        print("  [Drive] Authenticated via JSON env var")
    else:
        print("ERROR: Set GOOGLE_SERVICE_ACCOUNT_FILE or GOOGLE_SERVICE_ACCOUNT_JSON")
        sys.exit(1)

    return build("drive", "v3", credentials=creds)


# ===========================================================================
# Resolve folder — use env var ID first (shared folder in user's Drive)
# ===========================================================================
def resolve_folder(service) -> str:
    if DRIVE_FOLDER_ID:
        print(f"  [Drive] Using shared folder from env: {DRIVE_FOLDER_ID}")
        print(f"  [Drive] ⚠️  Make sure this folder is shared with the service account!")
        return DRIVE_FOLDER_ID

    # Fallback: try to find or create (only works on Shared Drives / Workspace)
    print(f"  [Drive] GOOGLE_DRIVE_FOLDER_ID not set — searching for '{DRIVE_FOLDER_NAME}'...")
    query = (
        f"name='{DRIVE_FOLDER_NAME}' "
        f"and mimeType='application/vnd.google-apps.folder' "
        f"and trashed=false"
    )
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files   = results.get("files", [])

    if files:
        folder_id = files[0]["id"]
        print(f"  [Drive] Found folder: {DRIVE_FOLDER_NAME} ({folder_id})")
        return folder_id

    print("ERROR: No GOOGLE_DRIVE_FOLDER_ID set and no existing folder found.")
    print("Fix: Create a folder in YOUR Google Drive, share it with the service")
    print("     account email (Editor), then set GOOGLE_DRIVE_FOLDER_ID secret.")
    sys.exit(1)


# ===========================================================================
# Upload one video
# ===========================================================================
def upload_video(service, file_path: str, folder_id: str) -> dict:
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path) / 1024 / 1024

    print(f"  [Drive] Uploading: {file_name} ({file_size:.1f} MB)...")

    file_meta = {"name": file_name, "parents": [folder_id]}
    media     = MediaFileUpload(file_path, mimetype="video/mp4", resumable=True)

    uploaded = service.files().create(
        body=file_meta,
        media_body=media,
        fields="id, name, size",
    ).execute()

    file_id = uploaded["id"]

    # Make publicly accessible (anyone with link)
    service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()

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

    service   = get_drive_service()
    folder_id = resolve_folder(service)

    uploaded = []
    for v in videos:
        video_path = v.get("video_file", "")
        if not os.path.exists(video_path):
            print(f"  SKIP: file not found: {video_path}")
            continue
        try:
            result          = upload_video(service, video_path, folder_id)
            result["topic"] = v.get("topic", "")
            uploaded.append(result)
        except Exception as e:
            print(f"  ERROR uploading {video_path}: {e}")

    os.makedirs(LOGS_DIR, exist_ok=True)
    output = {
        "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "folder_id":   folder_id,
        "count":       len(uploaded),
        "videos":      uploaded,
    }

    links_path = os.path.join(LOGS_DIR, "drive_links.json")
    with open(links_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*65}")
    print(f"DONE: {len(uploaded)}/{len(videos)} videos uploaded to Google Drive")
    print(f"Links saved: {links_path}")
    if uploaded:
        print(f"\n📁 Folder: https://drive.google.com/drive/folders/{folder_id}")
        for v in uploaded:
            print(f"  • {v['topic'][:50]}")
            print(f"    {v['download_link']}")


if __name__ == "__main__":
    main()
