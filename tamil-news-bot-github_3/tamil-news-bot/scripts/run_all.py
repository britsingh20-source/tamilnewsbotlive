"""
🤖 TAMIL NEWS CHANNEL - DAILY AUTO-RUN MASTER SCRIPT
Runs all 5 steps automatically:
  1. Find trending news
  2. Generate Tamil scripts (OpenAI GPT-4o)
  3. Create Tamil voiceover (Google TTS)
  4. Create videos with captions (MoviePy)
  5. Post to Instagram + YouTube

SETUP INSTRUCTIONS:
1. Install Python 3.9+
2. Run: pip install requests gtts moviepy --break-system-packages
3. Set your API keys below OR as environment variables
4. Run: python run_all.py
5. Schedule daily: crontab -e → add line:
   0 7 * * * cd /path/to/tamil-news-bot && python scripts/run_all.py

REQUIRED API KEYS (ALL FREE):
- OPENAI_API_KEY: https://platform.openai.com/api-keys
- PEXELS_API_KEY:    https://www.pexels.com/api (completely free)
- IG_ACCESS_TOKEN:   https://developers.facebook.com (free)
- IG_BUSINESS_ID:    Your Instagram Business Account ID
"""

import subprocess
import sys
import os
import json
from datetime import datetime

# ============================================================
# SET YOUR API KEYS HERE (or use environment variables)
# ============================================================
os.environ.setdefault("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY")
os.environ.setdefault("PEXELS_API_KEY", "YOUR_PEXELS_API_KEY")
os.environ.setdefault("IG_ACCESS_TOKEN", "YOUR_IG_ACCESS_TOKEN")
os.environ.setdefault("IG_BUSINESS_ID", "YOUR_IG_BUSINESS_ID")
# ============================================================

SCRIPTS_DIR = os.path.dirname(__file__)
LOG_DIR = os.path.join(SCRIPTS_DIR, "../logs")
os.makedirs(LOG_DIR, exist_ok=True)

STEPS = [
    ("1_find_news.py",       "🔍 Finding trending news"),
    ("2_generate_script.py", "✍️  Generating Tamil scripts"),
    ("3_generate_voice.py",  "🎙️  Creating Tamil voiceover"),
    ("4_create_video.py",    "🎬 Creating videos"),
    ("5_post_content.py",    "📱 Posting to Instagram + YouTube"),
]

def run_step(script_name, description):
    """Run a single automation step"""
    print(f"\n{'='*55}")
    print(f"{description}")
    print(f"{'='*55}")
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    result = subprocess.run(
        [sys.executable, script_path],
        capture_output=False,
        text=True,
        env=os.environ.copy()
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
    for script_name, description in STEPS:
        success = run_step(script_name, description)
        results[script_name] = "✅ Done" if success else "❌ Failed"
        if not success and script_name in ["1_find_news.py", "2_generate_script.py"]:
            print(f"\n⚠️  Critical step failed. Stopping pipeline.")
            break

    # Final summary
    end_time = datetime.now()
    duration = (end_time - start_time).seconds // 60
    print(f"""
╔══════════════════════════════════════════════════════╗
║     📊 DAILY RUN COMPLETE — {duration} minutes                ║
╚══════════════════════════════════════════════════════╝
""")
    for step, status in results.items():
        print(f"  {status}  {step}")

    # Save daily log
    log_entry = {
        "date": start_time.strftime("%Y-%m-%d"),
        "start": start_time.strftime("%H:%M"),
        "end": end_time.strftime("%H:%M"),
        "duration_min": duration,
        "steps": results
    }
    log_file = os.path.join(LOG_DIR, "daily_run.json")
    logs = []
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            logs = json.load(f)
    logs.append(log_entry)
    with open(log_file, "w") as f:
        json.dump(logs[-30:], f, indent=2)

    print(f"\n📁 Output folder: {os.path.join(SCRIPTS_DIR, '../output/videos')}")
    print(f"📋 Run log saved to: {log_file}")

if __name__ == "__main__":
    main()
