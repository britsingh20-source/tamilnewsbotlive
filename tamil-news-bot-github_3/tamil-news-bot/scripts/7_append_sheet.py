"""
STEP 7: Append Drive Links → Google Sheet
==========================================
- Reads  logs/drive_links.json  (written by 6_upload_drive.py)
- Scans the Drive-URL column (col C) top-to-bottom
- Finds the LAST row that already has a Drive URL
- Appends new video rows BELOW that last URL row (never overwrites)
- Sets Status  = "Pending"
- Sets Publish = "Pending"

Sheet columns (A–H)
--------------------
A  Date
B  Topic
C  Drive View URL        ← scanned for existing entries
D  Drive Download URL
E  Size (MB)
F  File ID
G  Status               ← written as "Pending"
H  Publish              ← written as "Pending"
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
# CONFIG  — set env vars or edit defaults below
# ─────────────────────────────────────────────────────────────
SPREADSHEET_ID       = os.environ.get("GOOGLE_SHEET_ID",  "YOUR_SPREADSHEET_ID_HERE")
SHEET_TAB_NAME       = os.environ.get("GOOGLE_SHEET_TAB", "VideoLinks")
SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")

# Column positions (0-indexed)
COL_DATE         = 0   # A
COL_TOPIC        = 1   # B
COL_VIEW_URL     = 2   # C  ← Drive view link; checked for existing entries
COL_DOWNLOAD_URL = 3   # D
COL_SIZE_MB      = 4   # E
COL_FILE_ID      = 5   # F
COL_STATUS       = 6   # G  → "Pending"
COL_PUBLISH      = 7   # H  → "Pending"
TOTAL_COLS       = 8

HEADER = [
    "Date", "Topic",
    "Drive View URL", "Drive Download URL",
    "Size (MB)", "File ID",
    "Status", "Publish",
]

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR    = os.path.join(SCRIPTS_DIR, "../logs")
LINKS_FILE  = os.path.join(LOGS_DIR, "drive_links.json")
SCOPES      = ["https://www.googleapis.com/auth/spreadsheets"]


# ── Auth ──────────────────────────────────────────────────────
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
    print("  [Sheets] Authenticated")
    return build("sheets", "v4", credentials=creds)


# ── Read all rows ─────────────────────────────────────────────
def read_all_rows(svc, sid, tab):
    res = svc.spreadsheets().values().get(
        spreadsheetId=sid, range=f"{tab}!A:H"
    ).execute()
    return res.get("values", [])


# ── Ensure tab + header ───────────────────────────────────────
def ensure_tab_and_header(svc, sid, tab):
    meta   = svc.spreadsheets().get(spreadsheetId=sid).execute()
    titles = [s["properties"]["title"] for s in meta["sheets"]]

    if tab not in titles:
        svc.spreadsheets().batchUpdate(
            spreadsheetId=sid,
            body={"requests": [{"addSheet": {"properties": {"title": tab}}}]},
        ).execute()
        print(f"  [Sheets] Created tab: {tab}")

    rows = read_all_rows(svc, sid, tab)
    if not rows:
        svc.spreadsheets().values().update(
            spreadsheetId=sid,
            range=f"{tab}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": [HEADER]},
        ).execute()
        print("  [Sheets] Header row written")


# ── Find insert row ───────────────────────────────────────────
def find_insert_row(rows: list) -> int:
    """
    Returns the 1-based sheet row number to insert at.
    Scans col C (Drive URL) and places new rows BELOW the last existing URL.
    If no URLs exist yet, inserts at row 2 (just after header).
    """
    last_url_row = 1  # header is row 1
    for i, row in enumerate(rows):
        sheet_row = i + 1
        if sheet_row == 1:
            continue
        cell = row[COL_VIEW_URL].strip() if len(row) > COL_VIEW_URL else ""
        if cell.startswith("http"):
            last_url_row = sheet_row
    return last_url_row + 1


# ── Write rows at exact position ──────────────────────────────
def write_rows_at(svc, sid, tab, start_row, rows):
    end_row  = start_row + len(rows) - 1
    range_a1 = f"{tab}!A{start_row}:H{end_row}"
    svc.spreadsheets().values().update(
        spreadsheetId=sid,
        range=range_a1,
        valueInputOption="USER_ENTERED",
        body={"values": rows},
    ).execute()
    print(f"  [Sheets] ✅ Wrote {len(rows)} row(s) at rows {start_row}–{end_row}")


# ── Main ──────────────────────────────────────────────────────
def main():
    print("=" * 65)
    print("Step 7: Append Drive Links → Google Sheet")
    print("=" * 65)

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
    print(f"Videos    : {len(videos)}")
    print(f"Sheet ID  : {SPREADSHEET_ID}")
    print(f"Tab       : {SHEET_TAB_NAME}")

    # Build rows — Status + Publish both set to "Pending"
    new_rows = []
    for v in videos:
        row = [""] * TOTAL_COLS
        row[COL_DATE]         = uploaded_at
        row[COL_TOPIC]        = v.get("topic", "")
        row[COL_VIEW_URL]     = v.get("view_link", "")
        row[COL_DOWNLOAD_URL] = v.get("download_link", "")
        row[COL_SIZE_MB]      = str(v.get("size_mb", ""))
        row[COL_FILE_ID]      = v.get("file_id", "")
        row[COL_STATUS]       = "Pending"
        row[COL_PUBLISH]      = "Pending"
        new_rows.append(row)

    svc = get_service()
    ensure_tab_and_header(svc, SPREADSHEET_ID, SHEET_TAB_NAME)

    existing  = read_all_rows(svc, SPREADSHEET_ID, SHEET_TAB_NAME)
    insert_at = find_insert_row(existing)

    print(f"  [Sheets] Last URL row : {insert_at - 1}  →  inserting at row {insert_at}")
    write_rows_at(svc, SPREADSHEET_ID, SHEET_TAB_NAME, insert_at, new_rows)

    print(f"\n{'='*65}")
    print(f"DONE: {len(new_rows)} row(s) added  |  Status=Pending  |  Publish=Pending")
    print(f"Sheet: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}")
    for v in videos:
        print(f"  • {v.get('topic','')[:55]}")
        print(f"    {v.get('view_link','')}")


if __name__ == "__main__":
    main()
