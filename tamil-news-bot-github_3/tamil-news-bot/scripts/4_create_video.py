"""
STEP 4: Auto-Create Tamil News Video (FIXED)
- Creates professional Tamil news-style animated background
- Overlays Tamil script text as captions synced to audio duration
- News header + breaking news ticker
- NO random dummy videos — visuals match the news content
- Outputs 9:16 vertical video for Reels/Shorts
"""

import json
import os
import numpy as np
from datetime import datetime

SCRIPTS_FILE = os.path.join(os.path.dirname(__file__), "../output/scripts.json")
AUDIO_DIR = os.path.join(os.path.dirname(__file__), "../output/audio")
VIDEO_DIR = os.path.join(os.path.dirname(__file__), "../output/videos")

W, H = 1080, 1920
FPS = 24
CHANNEL_NAME = "Tamil News Live"  # Change to your channel name


def wrap_tamil_text(text, max_chars=28):
    """Wrap Tamil text into lines of max_chars characters."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 <= max_chars:
            current = (current + " " + word).strip()
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def split_script_into_segments(spoken_text, num_segments):
    """Split spoken Tamil text into N roughly equal caption segments."""
    words = spoken_text.split()
    if not words:
        return [""] * num_segments
    chunk_size = max(1, len(words) // num_segments)
    segments = []
    for i in range(num_segments):
        start = i * chunk_size
        end = start + chunk_size if i < num_segments - 1 else len(words)
        segments.append(" ".join(words[start:end]))
    return segments


def create_news_video(audio_path, spoken_text, topic, output_path):
    """Create a professional Tamil news video with captions synced to audio."""
    try:
        from moviepy.editor import (
            VideoClip, AudioFileClip, CompositeVideoClip,
            TextClip, ColorClip
        )

        # Load audio to get exact duration
        audio = AudioFileClip(audio_path)
        duration = audio.duration
        print(f"  Audio duration: {duration:.1f}s")

        # --- Split script into caption segments ---
        num_segments = max(1, int(duration / 4))  # 1 caption every ~4 seconds
        caption_segments = split_script_into_segments(spoken_text, num_segments)
        segment_duration = duration / num_segments

        # ── 1. ANIMATED BACKGROUND ──────────────────────────────────────────
        def make_bg_frame(t):
            frame = np.zeros((H, W, 3), dtype=np.uint8)

            # Animated dark blue-to-black gradient
            pulse = int(10 * np.sin(t * 0.8))
            for y in range(H):
                ratio = y / H
                r = int(5 + 10 * ratio + pulse)
                g = int(10 + 20 * ratio + pulse)
                b = int(40 + 60 * ratio + pulse * 2)
                frame[y, :] = [
                    max(0, min(255, r)),
                    max(0, min(255, g)),
                    max(0, min(255, b))
                ]

            # Animated side accent lines
            for x_line in [0, 1, 2, W-3, W-2, W-1]:
                frame[:, x_line] = [200, 30, 30]

            # Top header bar
            frame[0:160, :] = [15, 30, 100]
            frame[155:165, :] = [220, 40, 40]  # Red divider

            # Bottom ticker bar
            frame[H-130:H, :] = [180, 20, 20]
            frame[H-135:H-130, :] = [220, 220, 220]  # White top edge

            return frame

        bg_clip = VideoClip(make_bg_frame, duration=duration)

        # ── 2. TEXT OVERLAYS ─────────────────────────────────────────────────

        text_clips = []

        # Channel name in header
        try:
            channel_clip = TextClip(
                CHANNEL_NAME,
                fontsize=52,
                color="white",
                font="DejaVu-Sans-Bold",
                method="caption",
                size=(W - 80, 120)
            ).set_position((40, 20)).set_duration(duration)
            text_clips.append(channel_clip)
        except Exception:
            pass  # Skip if font unavailable

        # BREAKING NEWS label
        try:
            breaking_clip = TextClip(
                "🔴 BREAKING NEWS",
                fontsize=38,
                color="#FF4444",
                font="DejaVu-Sans-Bold",
            ).set_position((40, 110)).set_duration(duration)
            text_clips.append(breaking_clip)
        except Exception:
            pass

        # Topic title (below header bar)
        try:
            topic_short = topic[:55] + "..." if len(topic) > 55 else topic
            topic_clip = TextClip(
                topic_short,
                fontsize=44,
                color="#FFDD44",
                font="DejaVu-Sans-Bold",
                method="caption",
                size=(W - 80, 160),
                align="West"
            ).set_position((40, 175)).set_duration(duration)
            text_clips.append(topic_clip)
        except Exception:
            pass

        # Caption segments (main body — synced to audio timing)
        for idx, segment_text in enumerate(caption_segments):
            if not segment_text.strip():
                continue
            seg_start = idx * segment_duration
            seg_end = min((idx + 1) * segment_duration, duration)
            seg_len = seg_end - seg_start

            lines = wrap_tamil_text(segment_text, max_chars=26)
            display_text = "\n".join(lines[:4])  # Max 4 lines

            try:
                cap_clip = TextClip(
                    display_text,
                    fontsize=54,
                    color="white",
                    font="DejaVu-Sans",
                    method="caption",
                    size=(W - 100, 700),
                    align="center",
                    stroke_color="black",
                    stroke_width=2,
                    interline=10
                ).set_position(("center", 400)).set_start(seg_start).set_duration(seg_len)
                text_clips.append(cap_clip)
            except Exception as e:
                print(f"  Caption segment {idx+1} skipped: {e}")

        # Bottom ticker text
        try:
            ticker_text = f"📰 {topic}"
            ticker_clip = TextClip(
                ticker_text,
                fontsize=38,
                color="white",
                font="DejaVu-Sans-Bold",
                method="caption",
                size=(W - 40, 110)
            ).set_position((20, H - 125)).set_duration(duration)
            text_clips.append(ticker_clip)
        except Exception:
            pass

        # Timestamp watermark
        try:
            ts_clip = TextClip(
                datetime.now().strftime("%d %b %Y"),
                fontsize=30,
                color="#AAAAAA",
                font="DejaVu-Sans",
            ).set_position((W - 220, H - 170)).set_duration(duration)
            text_clips.append(ts_clip)
        except Exception:
            pass

        # ── 3. COMPOSITE + AUDIO ────────────────────────────────────────────
        all_clips = [bg_clip] + text_clips
        final = CompositeVideoClip(all_clips, size=(W, H))
        final = final.set_audio(audio)

        final.write_videofile(
            output_path,
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            logger=None,
            threads=2,
            preset="ultrafast"
        )

        audio.close()
        final.close()

        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"  ✅ Video created: {size_mb:.1f} MB")
        return True

    except Exception as e:
        print(f"  ❌ Video creation error: {e}")
        import traceback
        traceback.print_exc()
        return False


def extract_spoken_text(script_text):
    """Extract only the Tamil spoken lines from the full script."""
    lines = script_text.split("\n")
    spoken_parts = []
    skip_sections = ["HASHTAGS", "CAPTION", "FORMAT", "RULES"]
    in_skip = False

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if any(skip in line.upper() for skip in skip_sections):
            in_skip = True
            continue
        if line.startswith("HOOK") or line.startswith("STORY") or \
           line.startswith("CTA") or line.startswith("TRUTH"):
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


def main():
    print("🎬 Creating Tamil News Videos (FIXED — captions match audio)...")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    os.makedirs(VIDEO_DIR, exist_ok=True)

    # Load scripts
    try:
        with open(SCRIPTS_FILE, "r", encoding="utf-8") as f:
            scripts_data = json.load(f)["scripts"]
    except FileNotFoundError:
        print("❌ scripts.json not found. Run 2_generate_script.py first!")
        return

    # Load audio manifest
    try:
        with open(os.path.join(AUDIO_DIR, "manifest.json"), "r") as f:
            audio_files = json.load(f)["audio_files"]
    except FileNotFoundError:
        print("❌ Audio manifest not found. Run 3_generate_voice.py first!")
        return

    print(f"Found {len(scripts_data)} scripts and {len(audio_files)} audio files\n")
    created_videos = []

    for i, (script_data, audio_data) in enumerate(zip(scripts_data, audio_files), 1):
        topic = script_data["topic"]
        print(f"🎥 Video {i}/{len(scripts_data)}: {topic[:50]}...")

        audio_path = audio_data["audio_file"]
        if not os.path.exists(audio_path):
            print(f"  ❌ Audio missing: {audio_path}")
            continue

        spoken_text = extract_spoken_text(script_data["script"])
        if not spoken_text:
            spoken_text = script_data["script"][:500]

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(VIDEO_DIR, f"reel_{i}_{timestamp}.mp4")

        success = create_news_video(audio_path, spoken_text, topic, output_path)

        if success and os.path.exists(output_path):
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            created_videos.append({
                "topic": topic,
                "video_file": output_path,
                "size_mb": round(size_mb, 1)
            })
            print(f"  ✅ Done! {size_mb:.1f} MB\n")
        else:
            print(f"  ❌ Failed\n")

    # Save manifest
    manifest_path = os.path.join(VIDEO_DIR, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "videos": created_videos,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
        }, f, ensure_ascii=False, indent=2)

    print(f"✅ {len(created_videos)} videos ready!")
    print(f"📁 Folder: {VIDEO_DIR}")


if __name__ == "__main__":
    main()
