"""
STEP 4: Auto-Create Tamil News Video (FIXED v2 - PIL text, no ImageMagick)
- Animated dark news background
- Tamil captions drawn directly with PIL (Pillow) — works on GitHub Actions
- News header, topic title, breaking news ticker
- NO random dummy videos
- Outputs 9:16 vertical video for Reels/Shorts
"""

import json
import os
import numpy as np
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

SCRIPTS_FILE = os.path.join(os.path.dirname(__file__), "../output/scripts.json")
AUDIO_DIR    = os.path.join(os.path.dirname(__file__), "../output/audio")
VIDEO_DIR    = os.path.join(os.path.dirname(__file__), "../output/videos")

W, H = 1080, 1920
FPS  = 24
CHANNEL_NAME = "Tamil News Live"


def get_font(size=48):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def get_tamil_font(size=54):
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoSansTamil-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/lohit-tamil/Lohit-Tamil.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_text_with_shadow(draw, xy, text, font, fill=(255, 255, 255),
                           shadow=(0, 0, 0), shadow_offset=3):
    x, y = xy
    draw.text((x + shadow_offset, y + shadow_offset), text, font=font, fill=shadow)
    draw.text((x, y), text, font=font, fill=fill)


def draw_centered_text(draw, text, font, y, width,
                        fill=(255, 255, 255), shadow=(0, 0, 0)):
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    x = max(0, (width - text_w) // 2)
    draw_text_with_shadow(draw, (x, y), text, font, fill=fill, shadow=shadow)


def build_frame(t, duration, topic, caption_text,
                font_header, font_topic, font_caption, font_ticker):
    pulse = int(10 * np.sin(t * 0.8))
    img = Image.new("RGB", (W, H))
    pixels = img.load()
    for y in range(H):
        ratio = y / H
        r = max(0, min(255, int(5  + 10 * ratio + pulse)))
        g = max(0, min(255, int(10 + 20 * ratio + pulse)))
        b = max(0, min(255, int(40 + 60 * ratio + pulse * 2)))
        for x in range(W):
            pixels[x, y] = (r, g, b)

    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 4, H], fill=(200, 30, 30))
    draw.rectangle([W - 5, 0, W, H], fill=(200, 30, 30))
    draw.rectangle([0, 0, W, 160], fill=(15, 30, 100))
    draw.rectangle([0, 155, W, 168], fill=(220, 40, 40))
    draw.rectangle([0, H - 135, W, H - 130], fill=(220, 220, 220))
    draw.rectangle([0, H - 130, W, H], fill=(180, 20, 20))

    draw_text_with_shadow(draw, (40, 18), CHANNEL_NAME, font_header, fill=(255, 255, 255))
    draw_text_with_shadow(draw, (40, 108), "BREAKING NEWS", font_ticker, fill=(255, 100, 100))

    topic_short = topic[:52] + "..." if len(topic) > 52 else topic
    topic_lines = wrap_text(draw, topic_short, font_topic, W - 80)
    ty = 178
    for line in topic_lines[:2]:
        draw_text_with_shadow(draw, (40, ty), line, font_topic, fill=(255, 221, 68))
        ty += 58

    if caption_text.strip():
        cap_lines = wrap_text(draw, caption_text, font_caption, W - 100)
        total_h = len(cap_lines[:5]) * 72
        cy = max(380, (H - total_h) // 2 - 50)
        for line in cap_lines[:5]:
            draw_centered_text(draw, line, font_caption, cy, W, fill=(255, 255, 255), shadow=(0, 0, 0))
            cy += 72

    ticker = f"  {topic}  "
    ticker_lines = wrap_text(draw, ticker, font_ticker, W - 40)
    draw_text_with_shadow(draw, (20, H - 122), ticker_lines[0] if ticker_lines else ticker, font_ticker, fill=(255, 255, 255))

    ts = datetime.now().strftime("%d %b %Y")
    ts_bbox = draw.textbbox((0, 0), ts, font=font_ticker)
    ts_w = ts_bbox[2] - ts_bbox[0]
    draw.text((W - ts_w - 20, H - 180), ts, font=font_ticker, fill=(170, 170, 170))

    return np.array(img)


def split_into_segments(text, num_segments):
    words = text.split()
    if not words:
        return [""] * num_segments
    chunk = max(1, len(words) // num_segments)
    segs = []
    for i in range(num_segments):
        start = i * chunk
        end = start + chunk if i < num_segments - 1 else len(words)
        segs.append(" ".join(words[start:end]))
    return segs


def create_news_video(audio_path, spoken_text, topic, output_path):
    try:
        from moviepy.editor import VideoClip, AudioFileClip
        audio = AudioFileClip(audio_path)
        duration = audio.duration
        print(f"  Audio duration: {duration:.1f}s")

        num_segs = max(1, int(duration / 4))
        segments = split_into_segments(spoken_text, num_segs)
        seg_dur  = duration / num_segs

        font_header  = get_font(52)
        font_topic   = get_font(44)
        font_caption = get_tamil_font(56)
        font_ticker  = get_font(36)

        def make_frame(t):
            seg_idx = min(int(t / seg_dur), num_segs - 1)
            return build_frame(t, duration, topic, segments[seg_idx],
                               font_header, font_topic, font_caption, font_ticker)

        clip  = VideoClip(make_frame, duration=duration)
        final = clip.set_audio(audio)
        final.write_videofile(output_path, fps=FPS, codec="libx264",
                              audio_codec="aac", logger=None, threads=2, preset="ultrafast")
        audio.close()
        final.close()
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"  Video created: {size_mb:.1f} MB")
        return True
    except Exception as e:
        print(f"  Video creation error: {e}")
        import traceback
        traceback.print_exc()
        return False


def extract_spoken_text(script_text):
    lines = script_text.split("\n")
    spoken_parts = []
    skip_sections = ["HASHTAGS", "CAPTION", "FORMAT", "RULES"]
    in_skip = False
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if any(s in line.upper() for s in skip_sections):
            in_skip = True
            continue
        if line.startswith(("HOOK", "STORY", "CTA", "TRUTH")):
            in_skip = False
            continue
        if in_skip:
            continue
        if line.startswith(("[", "---", "#")):
            continue
        if line and not line.isupper():
            spoken_parts.append(line)
    return " ".join(spoken_parts)


def main():
    print("Creating Tamil News Videos (v2 - PIL text, no ImageMagick)...")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    os.makedirs(VIDEO_DIR, exist_ok=True)

    try:
        with open(SCRIPTS_FILE, "r", encoding="utf-8") as f:
            scripts_data = json.load(f)["scripts"]
    except FileNotFoundError:
        print("scripts.json not found!")
        return

    try:
        with open(os.path.join(AUDIO_DIR, "manifest.json"), "r") as f:
            audio_files = json.load(f)["audio_files"]
    except FileNotFoundError:
        print("Audio manifest not found!")
        return

    print(f"Found {len(scripts_data)} scripts and {len(audio_files)} audio files\n")
    created_videos = []

    for i, (script_data, audio_data) in enumerate(zip(scripts_data, audio_files), 1):
        topic = script_data["topic"]
        print(f"Video {i}/{len(scripts_data)}: {topic[:50]}...")
        audio_path = audio_data["audio_file"]
        if not os.path.exists(audio_path):
            print(f"  Audio missing: {audio_path}")
            continue
        spoken_text = extract_spoken_text(script_data["script"])
        if not spoken_text:
            spoken_text = script_data["script"][:500]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(VIDEO_DIR, f"reel_{i}_{timestamp}.mp4")
        success = create_news_video(audio_path, spoken_text, topic, output_path)
        if success and os.path.exists(output_path):
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            created_videos.append({"topic": topic, "video_file": output_path, "size_mb": round(size_mb, 1)})
            print(f"  Done! {size_mb:.1f} MB\n")
        else:
            print(f"  Failed\n")

    manifest_path = os.path.join(VIDEO_DIR, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({"videos": created_videos, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")}, f, ensure_ascii=False, indent=2)

    print(f"{len(created_videos)} videos ready!")
    print(f"Folder: {VIDEO_DIR}")


if __name__ == "__main__":
    main()
