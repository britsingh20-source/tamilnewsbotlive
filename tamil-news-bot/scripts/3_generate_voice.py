"""
STEP 3: Auto-Generate Tamil Voiceover (FREE)
- Uses Google Text-to-Speech (gTTS) - completely free
- Reads scripts.json and generates MP3 audio files
- Saves audio to output/audio/ folder
"""

import json
import os
from datetime import datetime

SCRIPTS_FILE = os.path.join(os.path.dirname(__file__), "../output/scripts.json")
AUDIO_DIR = os.path.join(os.path.dirname(__file__), "../output/audio")

def extract_spoken_text(script_text):
    """Extract only the spoken parts (Tamil text) from the full script"""
    lines = script_text.split("\n")
    spoken_parts = []
    skip_sections = ["HASHTAGS", "CAPTION", "FORMAT", "RULES"]
    in_skip = False

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Skip section headers and English-only sections
        if any(skip in line.upper() for skip in skip_sections):
            in_skip = True
            continue
        # Resume on next Tamil section
        if line.startswith("HOOK") or line.startswith("STORY") or line.startswith("CTA") or line.startswith("TRUTH"):
            in_skip = False
            continue
        if in_skip:
            continue
        # Skip bracketed instructions
        if line.startswith("[") and line.endswith("]"):
            continue
        # Skip lines with only English/numbers/dashes
        if line.startswith("---") or line.startswith("#"):
            continue
        # Keep Tamil text lines
        if line and not line.isupper():
            spoken_parts.append(line)

    return " ".join(spoken_parts)

def generate_audio_gtts(text, output_path, lang="ta"):
    """Generate audio using Google TTS (free)"""
    try:
        from gtts import gTTS
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.save(output_path)
        return True
    except ImportError:
        print("   Installing gTTS...")
        os.system("pip install gtts --break-system-packages -q")
        try:
            from gtts import gTTS
            tts = gTTS(text=text, lang=lang, slow=False)
            tts.save(output_path)
            return True
        except Exception as e:
            print(f"   gTTS error: {e}")
            return False
    except Exception as e:
        print(f"   Audio generation error: {e}")
        return False

def main():
    print("🎙️  Generating Tamil Voiceovers (FREE via Google TTS)...")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    os.makedirs(AUDIO_DIR, exist_ok=True)

    # Load scripts
    try:
        with open(SCRIPTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        scripts = data["scripts"]
    except FileNotFoundError:
        print("❌ scripts.json not found. Run 2_generate_script.py first!")
        return

    audio_files = []

    for i, script_data in enumerate(scripts, 1):
        print(f"🔊 Generating audio {i}/{len(scripts)}: {script_data['topic'][:40]}...")

        spoken_text = extract_spoken_text(script_data["script"])
        if not spoken_text:
            spoken_text = script_data["script"][:500]

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"audio_{i}_{timestamp}.mp3"
        output_path = os.path.join(AUDIO_DIR, filename)

        success = generate_audio_gtts(spoken_text, output_path)

        if success:
            size_kb = os.path.getsize(output_path) / 1024
            audio_files.append({
                "topic": script_data["topic"],
                "audio_file": output_path,
                "spoken_text_preview": spoken_text[:100] + "...",
                "size_kb": round(size_kb, 1)
            })
            print(f"   ✅ Audio saved: {filename} ({size_kb:.0f} KB)")
        else:
            print(f"   ❌ Audio generation failed")

    # Save audio manifest
    manifest_path = os.path.join(AUDIO_DIR, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({"audio_files": audio_files, "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M")}, f, ensure_ascii=False, indent=2)

    print(f"\n✅ {len(audio_files)} audio files generated!")
    print(f"📁 Audio folder: {AUDIO_DIR}")
    print("\n💡 TIP: For better voice quality, use ElevenLabs free tier (10,000 chars/month)")
    print("   Sign up at: https://elevenlabs.io → Choose Tamil voice → Paste script → Download MP3")

if __name__ == "__main__":
    main()
