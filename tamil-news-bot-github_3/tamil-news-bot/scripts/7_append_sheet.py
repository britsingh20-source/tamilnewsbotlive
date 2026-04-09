"""
STEP 7: Append Drive Links to Google Sheet
==========================================
Behaviour
---------
- Reads  logs/drive_links.json  (written by 6_upload_drive.py)
- For EACH video:
    • Scans the Drive-URL column top-to-bottom
    • If a URL already exists in that column → appends the new row
      BELOW the last existing URL row (never overwrites)
    • Writes the new row:
        Date | Topic | Drive URL | Download URL | Size MB | File ID | Status | Publish
    • Status  → "Pending"
    • Publish → "Pending"
- Sheet tab + header row are auto-created if they don't exist yet

Column layout (A–H)
-------------------
A  Date
B  Topic
C  Drive View URL        ← "drive url" column — checked for existing entries
D  Drive Download URL
E  Size (MB)
F  File ID
G  Status               ← set to "Pending"
H  Publish              ← set to "Pending"
"""

import json, os, sys, tempfile
from datetime import datetime

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
except ImportError:
    print("ERROR: pip install google-api-python-client google-auth")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────
# CONFIG  ← set these or export as env vars before running
# ─────────────────────────────────────────────────────────────
SPREADSHEET_ID       = os.environ.get("GOOGLE_SHEET_ID", "YOUR_SPREADSHEET_ID_HERE")
SHEET_TAB_NAME       = os.environ.get("GOOGLE_SHEET_TAB", "VideoLinks")
SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")

# Column letters (1-indexed positions inside the script)
COL_DATE         = 0   # A
COL_TOPIC        = 1   # B
COL_VIEW_URL     = 2   # C  ← drive url; checked for existing entries
COL_DOWNLOAD_URL = 3   # D
COL_SIZE_MB      = 4   # E
COL_FILE_ID      = 5   # F
COL_STATUS       = 6   # G
COL_PUBLISH      = 7   # H
TOTAL_COLS       = 8

HEADER = [
    "Date", "Topic",
    "Drive View URL", "Drive Download URL",
    "Size (MB)", "File ID",
    "Status", "Publish",
]

# ─────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR    = os.path.join(SCRIPTS_DIR, "../logs")
LINKS_FILE  = os.path.join(LOGS_DIR, "drive_links.json")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


# ═══════════════════════════════════════════════════════════════
# Auth
# ═══════════════════════════════════════════════════════════════
def get_service():
    if not SERVICE_ACCOUNT_JSON:
        print("ERROR: GOOGLE_SERVICE_ACCOUNT_JSON env var not set")
        sys.exit(1)
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    tmp.write(SERVICE_ACCOUNT_JSON)
    tmp.close()
    creds = service_account.Credentials.from_service_account_file(
        tmp.name, scopes=SCOPES
    )
    os.unlink(tmp.name)
    svc = build("sheets", "v4", credentials=creds)
    print("  [Sheets] Authenticated")
    return svc


# ═══════════════════════════════════════════════════════════════
# Read ALL existing rows from the sheet
# ═══════════════════════════════════════════════════════════════
def read_all_rows(svc, spreadsheet_id: str, tab: str) -> list:
    result = svc.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{tab}!A:H",
    ).execute()
    return result.get("values", [])


# ═══════════════════════════════════════════════════════════════
# Ensure tab exists + header written
# ═══════════════════════════════════════════════════════════════
def ensure_tab_and_header(svc, spreadsheet_id: str, tab: str):
    meta = svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    titles = [s["properties"]["title"] for s in meta["sheets"]]

    if tab not in titles:
        svc.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": tab}}}]},
        ).execute()
        print(f"  [Sheets] Created tab: {tab}")

    rows = read_all_rows(svc, spreadsheet_id, tab)
    if not rows:
        # Write header
        svc.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{tab}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": [HEADER]},
        ).execute()
        print("  [Sheets] Header written")


# ═══════════════════════════════════════════════════════════════
# Find the next empty row AFTER the last row that has a Drive URL
# ═══════════════════════════════════════════════════════════════
def find_insert_row(rows: list) -> int:
    """
    Returns the 1-based sheet row number where the new data should go.
    - Skips row 1 (header).
    - Scans column C (COL_VIEW_URL) downward.
    - If any URL exists → insert BELOW the last URL row.
    - If no URLs yet → insert after header (row 2).
    """
    last_url_row = 1  # row 1 is header

    for i, row in enumerate(rows):
        sheet_row = i + 1  # 1-based
        if sheet_row == 1:
            continue  # skip header
        # Pad row if it's shorter than expected
        url_val = row[COL_VIEW_URL].strip() if len(row) > COL_VIEW_URL else ""
        if url_val.startswith("http"):
            last_url_row = sheet_row

    return last_url_row + 1   # insert on the row right after the last URL


# ═══════════════════════════════════════════════════════════════
# Write rows at a specific sheet row (batchUpdate for precision)
# ═══════════════════════════════════════════════════════════════
def write_rows_at(svc, spreadsheet_id: str, tab: str, start_row: int, rows: list):
    """Write `rows` starting at `start_row` (1-based), column A."""
    end_row = start_row + len(rows) - 1
    range_a1 = f"{tab}!A{start_row}:H{end_row}"

    svc.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=range_a1,
        valueInputOption="USER_ENTERED",
        body={"values": rows},
    ).execute()
    print(f"  [Sheets] Wrote {len(rows)} row(s) at row {start_row} → {end_row}")


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════
def main():
    print("=" * 65)
    print("Step 7: Append Drive Links → Google Sheet")
    print("=" * 65)

    # ── load drive_links.json ──────────────────────────────────
    if not os.path.exists(LINKS_FILE):
        print(f"ERROR: {LINKS_FILE} not found — run 6_upload_drive.py first")
        sys.exit(1)

    with open(LINKS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    videos = data.get("videos", [])
    if not videos:
        print("No videos in drive_links.json — nothing to append")
        sys.exit(0)

    uploaded_at = data.get("uploaded_at", datetime.now().strftime("%Y-%m-%d %H:%M"))
    print(f"Videos       : {len(videos)}")
    print(f"Uploaded at  : {uploaded_at}")
    print(f"Sheet ID     : {SPREADSHEET_ID}")
    print(f"Tab          : {SHEET_TAB_NAME}")

    # ── build new rows ─────────────────────────────────────────
    new_rows = []
    for v in videos:
        row = [""] * TOTAL_COLS
        row[COL_DATE]         = uploaded_at
        row[COL_TOPIC]        = v.get("topic", "")
        row[COL_VIEW_URL]     = v.get("view_link", "")
        row[COL_DOWNLOAD_URL] = v.get("download_link", "")
        row[COL_SIZE_MB]      = str(v.get("size_mb", ""))
        row[COL_FILE_ID]      = v.get("file_id", "")
        row[COL_STATUS]       = "Pending"   # ← Status column
        row[COL_PUBLISH]      = "Pending"   # ← Publish column
        new_rows.append(row)

    # ── authenticate ───────────────────────────────────────────
    svc = get_service()

    # ── ensure tab + header exist ──────────────────────────────
    ensure_tab_and_header(svc, SPREADSHEET_ID, SHEET_TAB_NAME)

    # ── read current sheet state ───────────────────────────────
    existing_rows = read_all_rows(svc, SPREADSHEET_ID, SHEET_TAB_NAME)
    insert_at     = find_insert_row(existing_rows)

    print(f"  [Sheets] Last Drive URL found at row: {insert_at - 1}")
    print(f"  [Sheets] Inserting new rows at     : {insert_at}")

    # ── write ──────────────────────────────────────────────────
    write_rows_at(svc, SPREADSHEET_ID, SHEET_TAB_NAME, insert_at, new_rows)

    sheet_url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}"
    print(f"\n{'='*65}")
    print(f"DONE: {len(new_rows)} row(s) added — Status=Pending, Publish=Pending")
    print(f"Sheet: {sheet_url}")
    print()
    for v in videos:
        print(f"  • {v.get('topic','')[:55]}")
        print(f"    {v.get('view_link','')}")


if __name__ == "__main__":
    main()
