"""
🤖 TAMIL NEWS CHANNEL - DAILY AUTO-RUN MASTER SCRIPT
Runs all 7 steps automatically:
  1. Find trending news
  2. Generate Tamil scripts (OpenAI GPT-4o)
  3. Create Tamil voiceover (Google TTS)
  4. Create videos with captions (MoviePy)
  5. Post to Instagram + YouTube
  6. Upload videos to Google Drive (shareable links)
  7. Append Drive links to Google Sheet (Status=Pending, Publish=Pending)

REQUIRED ENV VARS:
  OPENAI_API_KEY, PEXELS_API_KEY, IG_ACCESS_TOKEN, IG_BUSINESS_ID
  GOOGLE_SERVICE_ACCOUNT_JSON, GOOGLE_SHEET_ID, GOOGLE_SHEET_TAB
"""

import subprocess, sys, os, json
from datetime import datetime

# ============================================================
# SET YOUR API KEYS HERE (or export as environment variables)
# ============================================================
os.environ.setdefault("OPENAI_API_KEY",              "YOUR_OPENAI_API_KEY")
os.environ.setdefault("PEXELS_API_KEY",              "YOUR_PEXELS_API_KEY")
os.environ.setdefault("IG_ACCESS_TOKEN",             "YOUR_IG_ACCESS_TOKEN")
os.environ.setdefault("IG_BUSINESS_ID",              "YOUR_IG_BUSINESS_ID")
os.environ.setdefault("GOOGLE_SERVICE_ACCOUNT_JSON", "")   # paste full JSON string
os.environ.setdefault("GOOGLE_SHEET_ID",             "YOUR_SPREADSHEET_ID_HERE")
os.environ.setdefault("GOOGLE_SHEET_TAB",            "VideoLinks")
# ============================================================

SCRIPTS_DIR = os.path.dirname(__file__)
LOG_DIR     = os.path.join(SCRIPTS_DIR, "../logs")
os.makedirs(LOG_DIR, exist_ok=True)

# (script_name, description, stop_pipeline_on_failure)
STEPS = [
    ("1_find_news.py",       "🔍 Finding trending news",                          True),
    ("2_generate_script.py", "✍️  Generating Tamil scripts",                       True),
    ("3_generate_voice.py",  "🎙️  Creating Tamil voiceover",                      False),
    ("4_create_video.py",    "🎬 Creating videos",                                 False),
    ("5_post_content.py",    "📱 Posting to Instagram + YouTube",                  False),
    ("6_upload_drive.py",    "☁️  Uploading videos to Google Drive",               False),
    ("7_append_sheet.py",    "📊 Appending Drive links → Google Sheet (Pending)",  False),
]


def run_step(script_name, description):
    print(f"\n{'='*55}\n{description}\n{'='*55}")
    result = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS_DIR, script_name)],
        capture_output=False, text=True, env=os.environ.copy(),
    )
    return result.returncode == 0


def main():
    start_time = datetime.now()
    print(f"""
╔══════════════════════════════════════════════════════╗
║     🎬 TAMIL NEWS CHANNEL - DAILY AUTO-RUN           ║
║     {start_time.strftime('%Y-%m-%d %H:%M')}                              ║
╚══════════════════════════════════════════════════════╝
""")

    results = {}
    for script_name, description, is_critical in STEPS:
        success = run_step(script_name, description)
        results[script_name] = "✅ Done" if success else "❌ Failed"
        if not success and is_critical:
            print(f"\n⚠️  Critical step failed ({script_name}). Stopping pipeline.")
            break

    end_time = datetime.now()
    duration = (end_time - start_time).seconds // 60
    print(f"""
╔══════════════════════════════════════════════════════╗
║     📊 DAILY RUN COMPLETE — {duration} min                    ║
╚══════════════════════════════════════════════════════╝
""")
    for step, status in results.items():
        print(f"  {status}  {step}")

    log_entry = {
        "date": start_time.strftime("%Y-%m-%d"),
        "start": start_time.strftime("%H:%M"),
        "end": end_time.strftime("%H:%M"),
        "duration_min": duration,
        "steps": results,
    }
    log_file = os.path.join(LOG_DIR, "daily_run.json")
    logs = []
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            logs = json.load(f)
    logs.append(log_entry)
    with open(log_file, "w") as f:
        json.dump(logs[-30:], f, indent=2)

    print(f"\n📁 Videos : {os.path.join(SCRIPTS_DIR, '../output/videos')}")
    print(f"📋 Run log: {log_file}")


if __name__ == "__main__":
    main()
