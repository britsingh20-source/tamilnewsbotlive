"""
STEP 2: Auto-Write Tamil Script using OpenAI API
- Reads top topic from topics.json
- Calls OpenAI API to generate a 60-sec Tamil Reel script
- Saves script to scripts.json

PATCH 1 applied:
- Content filter blocks inappropriate topics before API call
- filter_script_content() removes any inappropriate lines after generation
- System prompt enforces family-friendly news-only content
"""

import requests
import json
import os
import re
from datetime import datetime

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY_HERE")
TOPICS_FILE  = os.path.join(os.path.dirname(__file__), "../output/topics.json")
SCRIPTS_FILE = os.path.join(os.path.dirname(__file__), "../output/scripts.json")


# ===========================================================================
# PATCH 1A — Content filter
# ===========================================================================
_BLOCKED_WORDS = [
    # Adult / inappropriate
    "condom", "contraceptive", "sex", "sexual", "porn", "nude", "naked",
    "prostitut", "escort", "adult film", "xxx", "erotic",
    "rape", "molest", "assault",
    # Drugs
    "drug deal", "cocaine", "heroin", "narcotic",
    # Extreme violence
    "bomb making", "how to kill", "suicide method",
]

def is_topic_appropriate(topic: str) -> bool:
    """Return False if topic contains any blocked content."""
    topic_lower = topic.lower()
    for word in _BLOCKED_WORDS:
        if word.lower() in topic_lower:
            print(f"  [Filter] BLOCKED topic -- contains '{word}': {topic[:60]}")
            return False
    return True

def filter_script_content(script_text: str) -> str:
    """
    Second-pass safety filter: remove any line in the generated script
    that contains a blocked word. Protects against the LLM sneaking
    inappropriate content into body text even when the topic looks clean.
    """
    lines   = script_text.split("\n")
    clean   = []
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
# PATCH 1B — Safe system prompt (enforces news-only content)
# ===========================================================================
SYSTEM_PROMPT = """You are a professional Tamil news channel script writer for Instagram Reels and YouTube Shorts.

STRICT CONTENT RULES — follow without exception:
- Write ONLY family-friendly news content suitable for ALL ages and all audiences
- NEVER mention: sexual products, contraceptives, adult content, violence details, drugs, alcohol
- NEVER write anything that would embarrass a TV news channel
- Topics must be: politics, economy, sports, weather, education, technology,
  Tamil Nadu local news, business, infrastructure, health (general only), culture
- Tone: formal, respectful, professional Tamil news anchor style
- No sensationalism, no clickbait that involves adult or violent content
- If the given topic is inappropriate, write about the most recent Tamil Nadu government news instead
"""


def generate_tamil_script(topic_title, topic_description=""):
    """Generate a Tamil news Reel script using OpenAI API"""

    prompt = f"""Write a viral Tamil news script for this topic: "{topic_title}"
Additional context: {topic_description}

FORMAT (strictly follow this):
---
HOOK (0-5 sec):
[Write 1 shocking/curious sentence in Tamil to stop the scroll]

STORY (5-45 sec):
[Write 4-5 sentences explaining the news clearly in Tamil. Use simple words. Be factual.]

TRUTH/FACT (if needed):
[Any fact-check or clarification in Tamil]

CTA (45-60 sec):
[Write 2 sentences in Tamil asking to share + follow]

HASHTAGS (in English):
[Write 15 relevant hashtags]

CAPTION (in Tamil + English):
[Write Instagram caption 2-3 lines]
---

Rules:
- Write ONLY in Tamil script (தமிழ்) for the spoken parts
- Keep total speaking time under 60 seconds (roughly 120-140 Tamil words)
- Make it emotional and engaging
- Use simple conversational Tamil, not formal Tamil
- Hashtags in English only"""

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }

    body = {
        "model": "gpt-4o",
        "max_tokens": 1000,
        "messages": [
            # PATCH 1B: system prompt now enforces family-safe content
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt}
        ]
    }

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=body,
            timeout=30
        )
        data        = resp.json()
        script_text = data["choices"][0]["message"]["content"]
        return script_text
    except Exception as e:
        print(f"OpenAI API error: {e}")
        return None


def extract_hook(script_text):
    """Extract just the hook line for video overlay"""
    lines = script_text.split("\n")
    for i, line in enumerate(lines):
        if "HOOK" in line.upper() and i + 1 < len(lines):
            for j in range(i + 1, min(i + 4, len(lines))):
                if lines[j].strip() and not lines[j].startswith("["):
                    return lines[j].strip()
    return ""


def main():
    print("✍️  Generating Tamil Scripts using OpenAI GPT-4o...")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    # Load topics
    try:
        with open(TOPICS_FILE, "r", encoding="utf-8") as f:
            data   = json.load(f)
        topics = data["topics"]
    except FileNotFoundError:
        print("❌ topics.json not found. Run 1_find_news.py first!")
        return

    all_scripts = []

    for i, topic in enumerate(topics[:3], 1):
        print(f"📝 Generating script {i}/3: {topic['title'][:50]}...")

        # PATCH 1A: block inappropriate topics before API call
        if not is_topic_appropriate(topic["title"]):
            print(f"   ⚠️  Skipped -- inappropriate topic")
            continue

        script = generate_tamil_script(
            topic["title"],
            topic.get("description", "")
        )

        if script:
            # PATCH 1A: second-pass filter on generated content
            script = filter_script_content(script)

            all_scripts.append({
                "topic":        topic["title"],
                "script":       script,
                "hook":         extract_hook(script),
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M")
            })
            print(f"   ✅ Script generated!")
        else:
            print(f"   ❌ Failed to generate script")

    # Save all scripts
    with open(SCRIPTS_FILE, "w", encoding="utf-8") as f:
        json.dump({"scripts": all_scripts}, f, ensure_ascii=False, indent=2)

    print(f"\n✅ {len(all_scripts)} scripts saved to: {SCRIPTS_FILE}")

    if all_scripts:
        print(f"\n--- PREVIEW: First Script ---")
        print(f"Topic:         {all_scripts[0]['topic']}")
        print(f"Hook:          {all_scripts[0]['hook']}")
        print(f"Script length: {len(all_scripts[0]['script'])} chars")


if __name__ == "__main__":
    main()
