"""
STEP 7: Append Drive Links → Google Sheet
==========================================
- Reads  logs/drive_links.json  (written by 6_upload_drive.py)
- Scans Drive-URL column (col B) top-to-bottom
- Appends new rows BELOW the last existing Drive URL row
- Sets Status  = "Pending"
- Sets Publish = "Pending"
- Supports BOTH:
    GOOGLE_SERVICE_ACCOUNT_FILE  (file path  — GitHub Actions)
    GOOGLE_SERVICE_ACCOUNT_JSON  (raw JSON   — local)

Sheet columns (A–M)
--------------------
A  sno
B  drive_url             ← scanned for existing entries
C  status
D  executed_at
E  Video Url
F  l captions
G  l hashtag
H  y title
I  y captions
J  y hashtag
K  f captions
L  f hashtag
M  Publish
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
# CONFIG
# ─────────────────────────────────────────────────────────────
SPREADSHEET_ID = os.environ.get("GOOGLE_SHEET_ID",  "YOUR_SPREADSHEET_ID_HERE")
SHEET_TAB_NAME = os.environ.get("GOOGLE_SHEET_TAB", "tamilnews")

COL_SNO         = 0   # A
COL_DRIVE_URL   = 1   # B ← checked for existing URLs
COL_STATUS      = 2   # C → "Pending"
COL_EXECUTED_AT = 3   # D
COL_VIDEO_URL   = 4   # E
COL_L_CAPTIONS  = 5   # F
COL_L_HASHTAG   = 6   # G
COL_Y_TITLE     = 7   # H
COL_Y_CAPTIONS  = 8   # I
COL_Y_HASHTAG   = 9   # J
COL_F_CAPTIONS  = 10  # K
COL_F_HASHTAG   = 11  # L
COL_PUBLISH     = 12  # M → "Pending"
TOTAL_COLS      = 13

HEADER = [
    "sno", "drive_url", "status", "executed_at",
    "Video Url", "l captions", "l hashtag",
    "y title", "y captions", "y hashtag",
    "f captions", "f hashtag", "Publish",
]

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR    = os.path.join(SCRIPTS_DIR, "../logs")
LINKS_FILE  = os.path.join(LOGS_DIR, "drive_links.json")
SCOPES      = ["https://www.googleapis.com/auth/spreadsheets"]


# ── Auth (file path OR raw JSON) ──────────────────────────────
def get_service():
    sa_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "")
    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")

    if sa_file and os.path.exists(sa_file):
        creds = service_account.Credentials.from_service_account_file(
            sa_file, scopes=SCOPES
        )
        print(f"  [Sheets] Authenticated via file: {sa_file}")
    elif sa_json:
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        tmp.write(sa_json)
        tmp.close()
        creds = service_account.Credentials.from_service_account_file(
            tmp.name, scopes=SCOPES
        )
        os.unlink(tmp.name)
        print("  [Sheets] Authenticated via JSON env var")
    else:
        print("ERROR: Set GOOGLE_SERVICE_ACCOUNT_FILE or GOOGLE_SERVICE_ACCOUNT_JSON")
        sys.exit(1)

    return build("sheets", "v4", credentials=creds)


# ── Read all rows ─────────────────────────────────────────────
def read_all_rows(svc, sid, tab):
    res = svc.spreadsheets().values().get(
        spreadsheetId=sid, range=f"{tab}!A:M"
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


# ── Find insert row (below last existing Drive URL) ───────────
def find_insert_row(rows: list) -> int:
    last_url_row = 1   # header = row 1
    for i, row in enumerate(rows):
        sheet_row = i + 1
        if sheet_row == 1:
            continue
        cell = row[COL_DRIVE_URL].strip() if len(row) > COL_DRIVE_URL else ""
        if cell.startswith("http"):
            last_url_row = sheet_row
    return last_url_row + 1


# ── Get next sno (based on last row's sno) ────────────────────
def get_next_sno(rows: list) -> int:
    last_sno = 0
    for i, row in enumerate(rows):
        if i == 0:
            continue  # skip header
        try:
            val = int(row[COL_SNO]) if len(row) > COL_SNO and row[COL_SNO] else 0
            if val > last_sno:
                last_sno = val
        except (ValueError, TypeError):
            pass
    return last_sno + 1


# ── Write rows at exact position ──────────────────────────────
def write_rows_at(svc, sid, tab, start_row, rows):
    end_row = start_row + len(rows) - 1
    svc.spreadsheets().values().update(
        spreadsheetId=sid,
        range=f"{tab}!A{start_row}:M{end_row}",
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
        print("No videos — nothing to append")
        sys.exit(0)

    uploaded_at = data.get("uploaded_at", datetime.now().strftime("%Y-%m-%d %H:%M"))
    print(f"Videos    : {len(videos)}")
    print(f"Sheet ID  : {SPREADSHEET_ID}")
    print(f"Tab       : {SHEET_TAB_NAME}")

    svc = get_service()
    ensure_tab_and_header(svc, SPREADSHEET_ID, SHEET_TAB_NAME)

    existing  = read_all_rows(svc, SPREADSHEET_ID, SHEET_TAB_NAME)
    insert_at = find_insert_row(existing)
    next_sno  = get_next_sno(existing)

    new_rows = []
    for i, v in enumerate(videos):
        row = [""] * TOTAL_COLS
        row[COL_SNO]         = next_sno + i
        row[COL_DRIVE_URL]   = v.get("view_link", "")
        row[COL_STATUS]      = "Pending"
        row[COL_EXECUTED_AT] = uploaded_at
        row[COL_VIDEO_URL]   = ""                    # filled later (YouTube URL)
        row[COL_L_CAPTIONS]  = ""                    # Instagram captions
        row[COL_L_HASHTAG]   = ""                    # Instagram hashtags
        row[COL_Y_TITLE]     = v.get("topic", "")
        row[COL_Y_CAPTIONS]  = ""                    # YouTube captions
        row[COL_Y_HASHTAG]   = ""                    # YouTube hashtags
        row[COL_F_CAPTIONS]  = ""                    # Facebook captions
        row[COL_F_HASHTAG]   = ""                    # Facebook hashtags
        row[COL_PUBLISH]     = "Pending"
        new_rows.append(row)

    print(f"  [Sheets] Last URL at row {insert_at - 1} → inserting at row {insert_at}")
    write_rows_at(svc, SPREADSHEET_ID, SHEET_TAB_NAME, insert_at, new_rows)

    print(f"\n{'='*65}")
    print(f"DONE: {len(new_rows)} row(s) — Status=Pending | Publish=Pending")
    print(f"Sheet: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}")
    for v in videos:
        print(f"  • {v.get('topic','')[:55]}")
        print(f"    {v.get('view_link','')}")


if __name__ == "__main__":
    main()
