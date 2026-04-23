"""
STEP 2: Auto-Write English Script using OpenAI API

- Reads top Coimbatore topic from topics.json
- Calls OpenAI API to generate a 60-sec Reel/Shorts script in ENGLISH
- Title, Hashtags, Description, Caption — all in ENGLISH
- Follows Instagram and YouTube community policy
- Saves script to scripts.json
"""

import requests
import json
import os
import re
from datetime import datetime

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY_HERE")
TOPICS_FILE = os.path.join(os.path.dirname(__file__), "../output/topics.json")
SCRIPTS_FILE = os.path.join(os.path.dirname(__file__), "../output/scripts.json")

# ===========================================================================
# Content Safety Filter — Instagram & YouTube Policy Compliance
# ===========================================================================

_BLOCKED_WORDS = [
    # Adult content
    "condom", "contraceptive", "sex", "sexual", "porn", "nude", "naked",
    "prostitut", "escort", "adult film", "xxx", "erotic",
    "rape", "molest", "assault",
    # Drugs
    "drug deal", "cocaine", "heroin", "narcotic",
    # Extreme violence
    "bomb making", "how to kill", "suicide method",
    # Misleading / hate speech (policy violation)
    "fake news", "hoax", "conspiracy", "hate speech",
]

def is_topic_appropriate(topic: str) -> bool:
    """Return False if topic contains blocked content"""
    topic_lower = topic.lower()
    for word in _BLOCKED_WORDS:
        if word.lower() in topic_lower:
            print(f"  [Filter] BLOCKED topic — contains '{word}': {topic[:60]}")
            return False
    return True

def filter_script_content(script_text: str) -> str:
    """Remove any line containing blocked words"""
    lines = script_text.split("\n")
    clean = []
    removed = 0
    for line in lines:
        if any(w.lower() in line.lower() for w in _BLOCKED_WORDS):
            print(f"  [Filter] Removed line: {line[:70]}")
            removed += 1
        else:
            clean.append(line)
    if removed:
        print(f"  [Filter] Removed {removed} inappropriate line(s)")
    return "\n".join(clean)

# ===========================================================================
# System Prompt — Instagram & YouTube Policy Compliant, English Only
# ===========================================================================

SYSTEM_PROMPT = """You are a professional news content creator for Instagram Reels and YouTube Shorts, specializing in Coimbatore local news.

PLATFORM POLICY RULES (strictly follow):
- Write ONLY family-friendly, factual news content suitable for ALL ages
- NEVER mention: sexual content, drugs, extreme violence, hate speech, or misleading information
- NEVER use clickbait that exaggerates or misleads — follow Instagram and YouTube misinformation policies
- Do NOT promote dangerous activities, self-harm, or illegal content
- All content must be respectful, neutral, and factual — like a professional news broadcast

LANGUAGE RULES:
- Write ALL content (hook, story, title, description, hashtags, caption) in ENGLISH ONLY
- Use clear, conversational English suitable for a general audience
- Avoid jargon; keep it accessible to all viewers

CONTENT FOCUS:
- Coimbatore city news: infrastructure, events, business, education, culture, sports, weather
- Positive community stories, civic updates, local achievements
- Tone: engaging, informative, professional news anchor style
"""

def generate_english_script(topic_title, topic_description=""):
    """Generate an English Coimbatore news Reel/Shorts script using OpenAI API"""

    prompt = f"""Write a viral English news script for this Coimbatore topic: "{topic_title}"

Additional context: {topic_description}

Generate ALL sections below in ENGLISH ONLY. Follow Instagram and YouTube community guidelines strictly.

---

VIDEO TITLE:
[Write a compelling, policy-compliant YouTube/Instagram title under 70 characters. No clickbait.]

HOOK (0-5 sec):
[1 attention-grabbing sentence in English to stop the scroll — factual, no misleading claims]

STORY (5-45 sec):
[4-5 clear English sentences explaining the Coimbatore news. Be factual, engaging, concise.]

KEY FACT:
[1 important fact or statistic related to this story]

CALL TO ACTION (45-60 sec):
[2 English sentences: ask viewers to like, share, follow for daily Coimbatore news]

HASHTAGS:
[Write 20 relevant English hashtags. Mix of broad + niche: #Coimbatore #CoimbatoreNews #TamilNadu #IndiaNews #LocalNews #Kovai etc.]

DESCRIPTION:
[Write a 3-4 sentence English YouTube/Instagram description. Include key facts, location context, and a CTA. SEO-friendly. No emojis overload. Policy-compliant.]

CAPTION:
[Write a 2-3 line English Instagram caption. Engaging, concise, ends with CTA. Include 2-3 emojis max.]

---

Rules:
- ALL text must be in English
- Keep speaking script under 60 seconds (roughly 100-120 words spoken)
- No Tamil text anywhere
- No misleading claims, no hate content, no adult content
- Optimized for Instagram Reels + YouTube Shorts algorithm"""

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }

    body = {
        "model": "gpt-4o",
        "max_tokens": 1200,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
    }

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=body,
            timeout=30
        )
        data = resp.json()
        script_text = data["choices"][0]["message"]["content"]
        return script_text
    except Exception as e:
        print(f"  OpenAI API error: {e}")
        return None

def extract_section(script_text, section_name):
    """Extract a named section from the script"""
    lines = script_text.split("\n")
    for i, line in enumerate(lines):
        if section_name.upper() in line.upper() and ":" in line:
            content_lines = []
            for j in range(i + 1, min(i + 8, len(lines))):
                l = lines[j].strip()
                if l and not l.startswith("[") and not l.startswith("---"):
                    # Stop if we hit another section header
                    if any(h in l.upper() for h in ["HOOK", "STORY", "TITLE", "CALL TO ACTION",
                                                      "HASHTAGS", "DESCRIPTION", "CAPTION", "KEY FACT"]):
                        break
                    content_lines.append(l)
            if content_lines:
                return "\n".join(content_lines)
    return ""

def extract_title(script_text):
    """Extract video title from script"""
    title = extract_section(script_text, "VIDEO TITLE")
    if not title:
        # Fallback: use first non-empty line
        for line in script_text.split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and len(line) > 10:
                return line[:70]
    return title[:70]

def extract_hashtags(script_text):
    """Extract hashtags from script"""
    lines = script_text.split("\n")
    for i, line in enumerate(lines):
        if "HASHTAGS" in line.upper() and i + 1 < len(lines):
            for j in range(i + 1, min(i + 6, len(lines))):
                if lines[j].strip().startswith("#"):
                    return lines[j].strip()
    return "#Coimbatore #CoimbatoreNews #Kovai #TamilNadu #IndiaNews #LocalNews #BreakingNews #CoimbatoreCity #SouthIndia #NewsShorts #DailyNews #Shorts #Reels #CoimbatoreUpdates #TamilNaduNews"

def extract_description(script_text):
    """Extract YouTube/Instagram description from script"""
    return extract_section(script_text, "DESCRIPTION")

def extract_caption(script_text):
    """Extract Instagram caption from script"""
    return extract_section(script_text, "CAPTION")

def extract_hook(script_text):
    """Extract hook line for video overlay"""
    return extract_section(script_text, "HOOK")

def main():
    print("✍️ Generating English Coimbatore News Scripts using OpenAI GPT-4o...")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    try:
        with open(TOPICS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            topics = data["topics"]
    except FileNotFoundError:
        print("❌ topics.json not found. Run 1_find_news.py first!")
        return

    all_scripts = []

    for i, topic in enumerate(topics[:3], 1):
        print(f"📝 Generating script {i}/3: {topic['title'][:60]}...")

        if not is_topic_appropriate(topic["title"]):
            print(f"  ⚠️ Skipped — inappropriate topic")
            continue

        script = generate_english_script(
            topic["title"],
            topic.get("description", "")
        )

        if script:
            script = filter_script_content(script)

            title     = extract_title(script)
            hashtags  = extract_hashtags(script)
            desc      = extract_description(script)
            caption   = extract_caption(script)
            hook      = extract_hook(script)

            all_scripts.append({
                "topic":       topic["title"],
                "title":       title,
                "hashtags":    hashtags,
                "description": desc,
                "caption":     caption,
                "hook":        hook,
                "script":      script,
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M")
            })
            print(f"  ✅ Script generated!")
            print(f"     Title: {title}")
        else:
            print(f"  ❌ Failed to generate script")

    with open(SCRIPTS_FILE, "w", encoding="utf-8") as f:
        json.dump({"scripts": all_scripts}, f, ensure_ascii=False, indent=2)

    print(f"\n✅ {len(all_scripts)} scripts saved to: {SCRIPTS_FILE}")

    if all_scripts:
        s = all_scripts[0]
        print(f"\n--- PREVIEW: First Script ---")
        print(f"Topic:       {s['topic']}")
        print(f"Title:       {s['title']}")
        print(f"Hook:        {s['hook']}")
        print(f"Hashtags:    {s['hashtags'][:80]}...")
        print(f"Description: {s['description'][:100]}...")
        print(f"Caption:     {s['caption'][:100]}...")

if __name__ == "__main__":
    main()
