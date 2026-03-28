# 🎬 Tamil News Channel — Full Automation System
**Automatically creates 3-5 Tamil Reels/Shorts daily — ₹0 cost**

---

## 📁 Folder Structure
```
tamil-news-bot/
├── scripts/
│   ├── run_all.py              ← Run this daily (master script)
│   ├── 1_find_news.py          ← Finds trending topics
│   ├── 2_generate_script.py    ← Writes Tamil scripts (Claude AI)
│   ├── 3_generate_voice.py     ← Creates Tamil voiceover (Google TTS)
│   ├── 4_create_video.py       ← Creates videos with captions
│   └── 5_post_content.py       ← Posts to Instagram + YouTube
├── output/
│   ├── topics.json             ← Today's trending topics
│   ├── scripts.json            ← Tamil scripts
│   ├── audio/                  ← MP3 voiceover files
│   └── videos/                 ← Final Reels ready to post
├── assets/                     ← Downloaded stock footage
├── logs/                       ← Daily run logs
└── README.md                   ← This file
```

---

## ⚙️ SETUP (One-Time — 30 minutes)

### Step 1: Install Python
Download Python 3.9+ from https://python.org/downloads

### Step 2: Install Required Libraries
```bash
pip install requests gtts moviepy anthropic
```

### Step 3: Get Free API Keys

| API | Where to Get | Cost |
|-----|-------------|------|
| **Claude AI** | https://console.anthropic.com | Free $5 credit (~500 scripts) |
| **Pexels Video** | https://www.pexels.com/api | Completely FREE |
| **Instagram** | https://developers.facebook.com | FREE |
| **ElevenLabs Voice** | https://elevenlabs.io | FREE (10K chars/month) |

### Step 4: Add API Keys
Open `scripts/run_all.py` and replace these:
```python
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-xxxxx")
os.environ.setdefault("PEXELS_API_KEY",    "xxxxxxxxxx")
os.environ.setdefault("IG_ACCESS_TOKEN",   "EAAxxxxxxx")
os.environ.setdefault("IG_BUSINESS_ID",    "1234567890")
```

### Step 5: Test Run
```bash
cd tamil-news-bot
python scripts/run_all.py
```

---

## ⏰ SCHEDULE DAILY (Automatic)

### On Windows (Task Scheduler):
1. Open Task Scheduler
2. Create Basic Task → Daily → 7:00 AM
3. Action: Start Program → `python`
4. Arguments: `C:\path\to\tamil-news-bot\scripts\run_all.py`

### On Mac/Linux (Cron):
```bash
crontab -e
# Add this line (runs at 7am daily):
0 7 * * * cd /path/to/tamil-news-bot && python scripts/run_all.py
```

---

## 📱 INSTAGRAM SETUP (Free)

1. Convert your Instagram to **Business Account**
   - Instagram → Settings → Account → Switch to Professional Account

2. Create a Facebook App
   - Go to https://developers.facebook.com
   - Create App → Business → Add Instagram Graph API

3. Get Access Token
   - Add Instagram Basic Display product
   - Generate User Token
   - Copy to `IG_ACCESS_TOKEN`

4. Get Business Account ID
   - Graph API Explorer → `/me/accounts`
   - Copy your Instagram Business Account ID

**Alternative (No Code):** Use **Meta Creator Studio**
- https://business.facebook.com/creatorstudio
- Upload videos manually or schedule them
- Completely free!

---

## 🎙️ BETTER VOICE (Optional — Free)

**ElevenLabs Tamil Voice (better quality):**
1. Sign up free at https://elevenlabs.io
2. Go to Voice Library → Search "Tamil"
3. Choose a Tamil voice
4. Paste your script → Download MP3
5. Replace the Google TTS audio in `output/audio/`

**TikTok Voice (also works for Reels):**
- Use TikTok app to add voiceover → Export without watermark

---

## 📊 EXPECTED RESULTS

| Metric | Timeline |
|--------|----------|
| First 1K followers | 2-4 weeks |
| 10K followers | 2-3 months |
| Monetization eligible | 3-6 months |
| Daily views | 5K-50K (by month 3) |

**Best posting times (IST):** 7am, 12:30pm, 6pm, 9pm

---

## 💡 TIPS FOR GROWTH

1. **Consistency** — Post every day without fail
2. **Trending first** — Always pick the #1 trending topic
3. **Hook is everything** — First 3 seconds decide everything
4. **Tamil caption** — Always write caption in Tamil
5. **Hashtags** — Use 15-20 hashtags every post
6. **Reply to comments** — Boosts algorithm reach
7. **Collab** — Duet/collab with other Tamil creators

---

## 🆘 TROUBLESHOOTING

**"Module not found" error:**
```bash
pip install requests gtts moviepy --break-system-packages
```

**"API key invalid" error:**
- Double check your API key in `run_all.py`
- Make sure no extra spaces around the key

**Video not generating:**
- Check if `output/audio/` has MP3 files
- Make sure MoviePy installed correctly

**Instagram posting fails:**
- Use Meta Creator Studio manually until API is set up
- Verify your account is Business, not Personal

---

## 📞 DAILY WORKFLOW (15 minutes only)

```
7:00 AM  → Script runs automatically
7:15 AM  → Check output/videos/ folder
7:20 AM  → Quick review of 3 videos
7:30 AM  → Post or schedule via Creator Studio
Done! ✅
```

---

*Built with Claude AI | Free forever | ₹0/month*
