"""
STEP 3: Auto-Generate Tamil Voiceover (FREE)
- Uses Google Text-to-Speech (gTTS) - completely free
- Reads scripts.json and generates MP3 audio files
- Saves audio to output/audio/ folder

PATCH 2 applied:
- humanize_text_for_tts(): adds natural pauses, cleans symbols before TTS
- post_process_audio(): ffmpeg EQ + compression makes voice warmer, less robotic
- gTTS called with slow=True for more deliberate delivery pace
"""

import json
import os
import re
import subprocess
from datetime import datetime

SCRIPTS_FILE = os.path.join(os.path.dirname(__file__), "../output/scripts.json")
AUDIO_DIR    = os.path.join(os.path.dirname(__file__), "../output/audio")


# ===========================================================================
# PATCH 2A — Humanize text before sending to TTS
# ===========================================================================
def humanize_text_for_tts(text: str) -> str:
    """
    Transform raw script text into TTS-friendly text that sounds
    more natural and less robotic:
      - Strips markdown / symbols that TTS reads literally
      - Adds commas at natural Tamil pause points
      - Breaks very long sentences at conjunctions
      - Ensures clean ending
    """
    # Remove markdown formatting symbols
    text = re.sub(r'[*_#`~]', '', text)

    # Remove bracket annotations like [pause], [music]
    text = re.sub(r'\[.*?\]', '', text)

    # Collapse extra whitespace
    text = re.sub(r' +', ' ', text).strip()

    # Add a pause-comma after common Tamil sentence starters
    starters = [
        "இன்று", "நேற்று", "இதன்படி", "அதன்படி", "இதனால்",
        "மேலும்", "அதாவது", "எனினும்", "ஆனால்", "இருப்பினும்",
        "சென்னை", "கோவை", "தமிழ்நாடு",
    ]
    for s in starters:
        # Only add comma if one isn't already there
        text = re.sub(rf'({s})([^,])', rf'\1,\2', text)

    # Remove duplicate commas
    text = re.sub(r',+', ',', text)
    text = re.sub(r',\s*,', ',', text)

    # Break very long sentences (>180 chars) at Tamil conjunctions
    sentences = re.split(r'(?<=[.!?]) +', text)
    result = []
    for sent in sentences:
        if len(sent) > 180:
            sent = re.sub(
                r'(\s+)(மேலும்|ஆனால்|எனினும்)',
                r'. \2', sent
            )
        result.append(sent)
    text = " ".join(result)

    # Ensure clean ending
    text = text.strip()
    if text and text[-1] not in '.!?':
        text += '.'

    return text


# ===========================================================================
# PATCH 2B — ffmpeg audio post-processing for warmer, less robotic voice
# ===========================================================================
def post_process_audio(input_path: str, output_path: str) -> str:
    """
    Apply ffmpeg audio filter chain to make gTTS less robotic:
      - equalizer 180Hz +3dB  : bass warmth (gTTS is thin/tinny)
      - equalizer 2800Hz +2dB : presence/clarity boost
      - acompressor            : even out volume like a real broadcast
      - atempo 0.94            : slightly slower = more deliberate delivery
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
        print("   [Audio] ffmpeg not found -- skipping post-process (install ffmpeg)")
        return input_path
    except Exception as e:
        print(f"   [Audio] Post-process error: {e}")
        return input_path


def extract_spoken_text(script_text):
    """Extract only the spoken parts (Tamil text) from the full script"""
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
    """Generate audio using Google TTS (free)"""
    try:
        from gtts import gTTS
        # slow=True gives more deliberate delivery -- less robotic feel
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

        # Extract spoken text
        spoken_text = extract_spoken_text(script_data["script"])
        if not spoken_text:
            spoken_text = script_data["script"][:500]

        # PATCH 2A: humanize text before TTS
        spoken_text = humanize_text_for_tts(spoken_text)

        timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
        raw_path    = os.path.join(AUDIO_DIR, f"audio_{i}_{timestamp}_raw.mp3")
        final_path  = os.path.join(AUDIO_DIR, f"audio_{i}_{timestamp}.mp3")

        # Generate TTS audio
        success = generate_audio_gtts(spoken_text, raw_path)

        if success:
            # PATCH 2B: post-process for warmer, less robotic sound
            final_path = post_process_audio(raw_path, final_path)

            # Clean up raw file if post-processing succeeded
            if final_path != raw_path and os.path.exists(raw_path):
                os.remove(raw_path)

            size_kb = os.path.getsize(final_path) / 1024
            audio_files.append({
                "topic":               script_data["topic"],
                "audio_file":          final_path,
                "spoken_text_preview": spoken_text[:100] + "...",
                "size_kb":             round(size_kb, 1)
            })
            print(f"   ✅ Audio saved: {os.path.basename(final_path)} ({size_kb:.0f} KB)")
        else:
            print(f"   ❌ Audio generation failed")

    # Save audio manifest
    manifest_path = os.path.join(AUDIO_DIR, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "audio_files":  audio_files,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M")
        }, f, ensure_ascii=False, indent=2)

    print(f"\n✅ {len(audio_files)} audio files generated!")
    print(f"📁 Audio folder: {AUDIO_DIR}")
    print("\n💡 TIP: For even better voice, use ElevenLabs free tier (10,000 chars/month)")
    print("   Sign up at: https://elevenlabs.io → Choose Tamil voice → Paste script → Download MP3")


if __name__ == "__main__":
    main()
