"""
STEP 3: Auto-Generate Tamil Voiceover (FREE)
- Uses Google Text-to-Speech (gTTS)
- v3 fixes:
  * slow=False  -- normal speaking speed (was slow=True, too sluggish)
  * atempo=1.10 -- 10% faster than default for energetic news delivery
  * volume=+6dB -- louder via ffmpeg volume filter
  * Strips "cannot fetch", "Tamil News", English error phrases before TTS
  * Minimum 20 char check before TTS call
"""

import json
import os
import re
import subprocess
from datetime import datetime

SCRIPTS_FILE = os.path.join(os.path.dirname(__file__), "../output/scripts.json")
AUDIO_DIR    = os.path.join(os.path.dirname(__file__), "../output/audio")

# ---------------------------------------------------------------------------
# Phrases that must NEVER be spoken (error text, channel IDs, English noise)
# ---------------------------------------------------------------------------
_STRIP_PHRASES = [
    "cannot fetch", "could not fetch", "failed to fetch",
    "tamil news", "tamil news live", "breaking news",
    "error", "exception", "traceback",
    "none", "null", "undefined",
    "http", "https", "www.",
    "hashtags", "caption", "format", "rules",
]

def clean_spoken_text(text: str) -> str:
    """
    Remove lines that contain error phrases or are purely English noise.
    Safe for Tamil -- only matches ASCII-dominated lines.
    """
    lines  = text.split('.')
    clean  = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        line_lower = line.lower()
        # Skip if line is dominated by ASCII (likely English error/noise)
        tamil_chars = sum(1 for c in line if '\u0B80' <= c <= '\u0BFF')
        total_chars = len([c for c in line if c.strip()])
        # If less than 20% Tamil chars AND less than 15 chars total -> skip
        if total_chars > 0 and tamil_chars / total_chars < 0.2 and total_chars < 30:
            print(f"   [Clean] Removed English noise: {line[:50]}")
            continue
        # Skip lines with error phrases
        if any(phrase in line_lower for phrase in _STRIP_PHRASES):
            print(f"   [Clean] Removed error phrase: {line[:50]}")
            continue
        clean.append(line)
    return '. '.join(clean)


def humanize_text_for_tts(text: str) -> str:
    """
    Safely prepare text for gTTS.
    ONLY strips ASCII symbols -- never touches Tamil Unicode.
    """
    # Remove ASCII markdown
    text = re.sub(r'[*_#`~]', '', text)
    # Remove bracket annotations
    text = re.sub(r'\[[^\]]*\]', '', text)
    # Remove section dividers
    lines = text.split('\n')
    lines = [l for l in lines if not re.match(r'^[-=]{3,}\s*$', l.strip())]
    text  = ' '.join(lines)
    # Collapse spaces
    text  = re.sub(r'  +', ' ', text).strip()
    # Clean ending
    if text and text[-1] not in '.!?':
        text += '.'
    return text


def post_process_audio(input_path: str, output_path: str) -> str:
    """
    ffmpeg audio filter chain:
      - volume=2.0    : +6dB boost (louder, broadcast level)
      - equalizer 180Hz +3dB  : bass warmth
      - equalizer 3000Hz +3dB : presence/clarity for Tamil consonants
      - acompressor   : even out volume peaks
      - atempo=1.10   : 10% faster = energetic news delivery pace
    """
    filter_chain = (
        "volume=2.0,"
        "equalizer=f=180:width_type=o:width=2:g=3,"
        "equalizer=f=3000:width_type=o:width=2:g=3,"
        "acompressor=threshold=0.089:ratio=4:attack=5:release=50,"
        "atempo=1.10"
    )
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-af", filter_chain,
        "-ar", "44100", "-ac", "1", "-q:a", "2",
        output_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if res.returncode == 0 and os.path.exists(output_path):
            sz_in  = os.path.getsize(input_path)  / 1024
            sz_out = os.path.getsize(output_path) / 1024
            print(f"   [Audio] Post-processed: {sz_in:.0f}KB -> {sz_out:.0f}KB")
            return output_path
        print(f"   [Audio] ffmpeg failed: {res.stderr[:200]}")
        return input_path
    except FileNotFoundError:
        print("   [Audio] ffmpeg not found -- skipping post-process")
        return input_path
    except Exception as e:
        print(f"   [Audio] Error: {e}")
        return input_path


def get_audio_duration(path: str) -> float:
    """Get audio duration in seconds using ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries",
             "format=duration", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=15)
        return float(result.stdout.strip() or "0")
    except Exception:
        return 0.0


def extract_spoken_text(script_text):
    """Extract only the spoken Tamil parts from the full script."""
    lines         = script_text.split("\n")
    spoken_parts  = []
    skip_sections = ["HASHTAGS", "CAPTION", "FORMAT", "RULES"]
    in_skip       = False

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if any(skip in line.upper() for skip in skip_sections):
            in_skip = True
            continue
        if any(line.startswith(s) for s in ["HOOK", "STORY", "CTA", "TRUTH"]):
            in_skip = False
            continue
        if in_skip:
            continue
        if line.startswith("[") and line.endswith("]"):
            continue
        if line.startswith("---") or line.startswith("#"):
            continue
        if line and not line.isupper():
            spoken_parts.append(line)

    return " ".join(spoken_parts)


def generate_audio_gtts(text, output_path, lang="ta"):
    """Generate audio using gTTS. slow=False for natural news pace."""
    try:
        from gtts import gTTS
        tts = gTTS(text=text, lang=lang, slow=False)  # normal speed
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
    print("Generating Tamil Voiceovers...")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    os.makedirs(AUDIO_DIR, exist_ok=True)

    try:
        with open(SCRIPTS_FILE, "r", encoding="utf-8") as f:
            data    = json.load(f)
        scripts = data["scripts"]
    except FileNotFoundError:
        print("scripts.json not found. Run 2_generate_script.py first!")
        return

    audio_files = []

    for i, script_data in enumerate(scripts, 1):
        print(f"Generating audio {i}/{len(scripts)}: {script_data['topic'][:40]}...")

        # Extract spoken text
        spoken_text = extract_spoken_text(script_data["script"])
        if not spoken_text:
            spoken_text = script_data["script"][:500]

        # Humanize (ASCII-safe only)
        spoken_text = humanize_text_for_tts(spoken_text)

        # Strip error phrases / English noise
        spoken_text = clean_spoken_text(spoken_text)

        # Safety check
        if len(spoken_text.strip()) < 20:
            print(f"   WARNING: spoken text too short ({len(spoken_text)} chars)")
            print(f"   Text: {spoken_text[:100]}")
            print(f"   Skipping -- check scripts.json for Tamil content")
            continue

        print(f"   Text length: {len(spoken_text)} chars")
        print(f"   Preview: {spoken_text[:80]}...")

        timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
        raw_path   = os.path.join(AUDIO_DIR, f"audio_{i}_{timestamp}_raw.mp3")
        final_path = os.path.join(AUDIO_DIR, f"audio_{i}_{timestamp}.mp3")

        success = generate_audio_gtts(spoken_text, raw_path)

        if success:
            duration = get_audio_duration(raw_path)
            if duration < 3.0:
                print(f"   WARNING: audio too short ({duration:.1f}s)")
                print(f"   This usually means the text had no Tamil content")
            else:
                print(f"   Duration: {duration:.1f}s -- OK")

            # Post-process: louder + faster + warmer
            final_path = post_process_audio(raw_path, final_path)

            if final_path != raw_path and os.path.exists(raw_path):
                os.remove(raw_path)

            size_kb = os.path.getsize(final_path) / 1024
            audio_files.append({
                "topic":               script_data["topic"],
                "audio_file":          final_path,
                "spoken_text_preview": spoken_text[:100] + "...",
                "size_kb":             round(size_kb, 1)
            })
            print(f"   Saved: {os.path.basename(final_path)} ({size_kb:.0f} KB)")
        else:
            print(f"   FAILED")

    manifest_path = os.path.join(AUDIO_DIR, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "audio_files":  audio_files,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M")
        }, f, ensure_ascii=False, indent=2)

    print(f"\n{len(audio_files)} audio files generated!")
    print(f"Audio folder: {AUDIO_DIR}")

    if len(audio_files) == 0:
        print("\nZERO audio -- likely causes:")
        print("  1. scripts.json has no Tamil text (check 2_generate_script.py output)")
        print("  2. gTTS network error (check internet connection)")
        print("  3. OpenAI returned English instead of Tamil script")


if __name__ == "__main__":
    main()
