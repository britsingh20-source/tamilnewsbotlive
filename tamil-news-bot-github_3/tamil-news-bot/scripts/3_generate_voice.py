"""
STEP 3: Auto-Generate Tamil Voiceover (FREE)
- Uses Google Text-to-Speech (gTTS) - completely free
- Reads scripts.json and generates MP3 audio files
- Saves audio to output/audio/ folder

v2 patch (safe):
- humanize_text_for_tts() now only strips ASCII symbols -- never touches Tamil Unicode
- post_process_audio() ffmpeg chain: warmth EQ + compression + slight slowdown
- gTTS slow=True for more deliberate delivery
"""

import json
import os
import re
import subprocess
from datetime import datetime

SCRIPTS_FILE = os.path.join(os.path.dirname(__file__), "../output/scripts.json")
AUDIO_DIR    = os.path.join(os.path.dirname(__file__), "../output/audio")


# ===========================================================================
# Safe humanize -- ONLY strips ASCII noise, never touches Tamil characters
# ===========================================================================
def humanize_text_for_tts(text: str) -> str:
    """
    Safely prepare text for gTTS. Rules:
      - Remove ASCII markdown symbols (* _ # ` ~)
      - Remove [bracket annotations] which are ASCII only
      - Collapse multiple spaces
      - Ensure ends with a period
      - NEVER modify Tamil Unicode characters (U+0B80–U+0BFF range)
    """
    # Remove ASCII markdown formatting only
    text = re.sub(r'[*_#`~]', '', text)

    # Remove bracket annotations (ASCII brackets only, safe for Tamil)
    text = re.sub(r'\[[^\]]*\]', '', text)

    # Remove lines that are purely dashes/equals (section dividers)
    lines = text.split('\n')
    lines = [l for l in lines if not re.match(r'^[-=]{3,}\s*$', l.strip())]
    text  = ' '.join(lines)

    # Collapse multiple spaces
    text = re.sub(r'  +', ' ', text).strip()

    # Ensure clean ending
    if text and text[-1] not in '.!?':
        text += '.'

    return text


# ===========================================================================
# ffmpeg post-processing for warmer, less robotic voice
# ===========================================================================
def post_process_audio(input_path: str, output_path: str) -> str:
    """
    Apply ffmpeg audio filters:
      - equalizer 180Hz +3dB  : bass warmth
      - equalizer 2800Hz +2dB : presence clarity
      - acompressor            : even broadcast-style volume
      - atempo 0.94            : 6% slower = more deliberate delivery
    Returns output_path on success, input_path on failure.
    """
    filter_chain = (
        "equalizer=f=180:width_type=o:width=2:g=3,"
        "equalizer=f=2800:width_type=o:width=2:g=2,"
        "acompressor=threshold=0.089:ratio=4:attack=5:release=50,"
        "atempo=0.94"
    )
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-af", filter_chain,
        "-ar", "44100", "-ac", "1", "-q:a", "3",
        output_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if res.returncode == 0 and os.path.exists(output_path):
            sz_in  = os.path.getsize(input_path)  / 1024
            sz_out = os.path.getsize(output_path) / 1024
            print(f"   [Audio] Post-processed: {sz_in:.0f}KB -> {sz_out:.0f}KB")
            return output_path
        else:
            print(f"   [Audio] Post-process failed: {res.stderr[:200]}")
            return input_path
    except FileNotFoundError:
        print("   [Audio] ffmpeg not found -- skipping (install ffmpeg)")
        return input_path
    except Exception as e:
        print(f"   [Audio] Post-process error: {e}")
        return input_path


def extract_spoken_text(script_text):
    """Extract only the spoken Tamil parts from the full script"""
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
        if line.startswith("HOOK") or line.startswith("STORY") \
                or line.startswith("CTA") or line.startswith("TRUTH"):
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
    """Generate audio using Google TTS (free), slow=True for natural pace"""
    try:
        from gtts import gTTS
        tts = gTTS(text=text, lang=lang, slow=True)
        tts.save(output_path)
        return True
    except ImportError:
        print("   Installing gTTS...")
        os.system("pip install gtts --break-system-packages -q")
        try:
            from gtts import gTTS
            tts = gTTS(text=text, lang=lang, slow=True)
            tts.save(output_path)
            return True
        except Exception as e:
            print(f"   gTTS error: {e}")
            return False
    except Exception as e:
        print(f"   Audio generation error: {e}")
        return False


def main():
    print("Generating Tamil Voiceovers (FREE via Google TTS)...")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    os.makedirs(AUDIO_DIR, exist_ok=True)

    try:
        with open(SCRIPTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        scripts = data["scripts"]
    except FileNotFoundError:
        print("scripts.json not found. Run 2_generate_script.py first!")
        return

    audio_files = []

    for i, script_data in enumerate(scripts, 1):
        print(f"Generating audio {i}/{len(scripts)}: {script_data['topic'][:40]}...")

        spoken_text = extract_spoken_text(script_data["script"])
        if not spoken_text:
            spoken_text = script_data["script"][:500]

        # Safe humanize -- strips ASCII noise only, never touches Tamil
        spoken_text = humanize_text_for_tts(spoken_text)

        # Verify we have enough text before calling TTS
        if len(spoken_text.strip()) < 20:
            print(f"   WARNING: spoken text too short ({len(spoken_text)} chars) -- skipping")
            continue

        print(f"   Text length: {len(spoken_text)} chars")

        timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
        raw_path   = os.path.join(AUDIO_DIR, f"audio_{i}_{timestamp}_raw.mp3")
        final_path = os.path.join(AUDIO_DIR, f"audio_{i}_{timestamp}.mp3")

        success = generate_audio_gtts(spoken_text, raw_path)

        if success:
            # Verify audio is long enough (>3 seconds minimum)
            try:
                result = subprocess.run(
                    ["ffprobe", "-v", "quiet", "-show_entries",
                     "format=duration", "-of", "csv=p=0", raw_path],
                    capture_output=True, text=True, timeout=15
                )
                duration = float(result.stdout.strip() or "0")
                if duration < 3.0:
                    print(f"   WARNING: audio too short ({duration:.1f}s) -- text may be corrupted")
                else:
                    print(f"   Audio duration: {duration:.1f}s -- OK")
            except Exception:
                pass

            # Post-process for warmer sound
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
            print(f"   Audio saved: {os.path.basename(final_path)} ({size_kb:.0f} KB)")
        else:
            print(f"   Audio generation FAILED")

    manifest_path = os.path.join(AUDIO_DIR, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "audio_files":  audio_files,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M")
        }, f, ensure_ascii=False, indent=2)

    print(f"\n{len(audio_files)} audio files generated!")
    print(f"Audio folder: {AUDIO_DIR}")

    if len(audio_files) == 0:
        print("\nZERO audio files -- check that scripts.json has Tamil text content")


if __name__ == "__main__":
    main()
