"""
STEP 4: Tamil News Video Creator (v4)
- Tries Pexels video -> Pixabay video -> Pexels photo -> Pixabay photo -> gradient
- Pixabay is 100% FREE (get key at https://pixabay.com/api/docs/)
- Tamil captions rendered with Noto Tamil font
- Footer advertisement: Coimbatore Veedu Builders | 8111024877
- v4: Added Pixabay, bulletproof fallback, verbose ffmpeg logging
"""

import json
import os
import io
import sys
import subprocess
import requests
import numpy as np
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

SCRIPTS_FILE = os.path.join(os.path.dirname(__file__), "../output/scripts.json")
AUDIO_DIR    = os.path.join(os.path.dirname(__file__), "../output/audio")
VIDEO_DIR    = os.path.join(os.path.dirname(__file__), "../output/videos")
ASSETS_DIR   = os.path.join(os.path.dirname(__file__), "../assets")

W, H   = 1080, 1920
FPS    = 24

# Advertisement config
AD_LINE1    = "Coimbatore Veedu Builders"
AD_LINE2    = "Contact: 8111024877"
CHANNEL     = "Tamil News Live"

# API keys
PEXELS_KEY   = os.environ.get("PEXELS_API_KEY", "")
PIXABAY_KEY  = os.environ.get("PIXABAY_API_KEY", "")


def get_topic_keywords(topic):
    """Extract short English-safe keywords from topic for API search."""
    ascii_words = [w for w in topic.split() if all(ord(c) < 128 for c in w) and len(w) > 2]
    if ascii_words:
        return " ".join(ascii_words[:4])
    return "news breaking india city"


def download_pexels_video(keywords, out_path):
    if not PEXELS_KEY:
        print("  [Pexels] No PEXELS_API_KEY set, skipping")
        return False
    try:
        headers = {"Authorization": PEXELS_KEY}
        for query in [keywords, "news television broadcast india"]:
            params = {"query": query, "per_page": 5, "orientation": "portrait"}
            r = requests.get("https://api.pexels.com/videos/search",
                             headers=headers, params=params, timeout=15)
            print(f"  [Pexels video] query='{query}' status={r.status_code}")
            if r.status_code != 200:
                continue
            videos = r.json().get("videos", [])
            if not videos:
                continue
            video = videos[0]
            files = video.get("video_files", [])
            portrait = [f for f in files if f.get("width", 0) < f.get("height", 0)]
            candidates = portrait if portrait else files
            candidates = sorted(candidates, key=lambda f: f.get("width", 9999))
            if not candidates:
                continue
            chosen = candidates[0]
            url = chosen.get("link", "")
            if not url:
                continue
            print(f"  [Pexels video] Downloading {chosen.get('width')}x{chosen.get('height')} ...")
            resp = requests.get(url, stream=True, timeout=90)
            if resp.status_code != 200:
                continue
            downloaded = 0
            with open(out_path, "wb") as f:
                for chunk in resp.iter_content(65536):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if downloaded > 30 * 1024 * 1024:
                        break
            sz = os.path.getsize(out_path)
            print(f"  [Pexels video] Got {sz/1024/1024:.1f} MB")
            return sz > 100_000
    except Exception as e:
        print(f"  [Pexels video] Error: {e}")
    return False


def download_pexels_photo(keywords, out_path):
    if not PEXELS_KEY:
        return False
    try:
        headers = {"Authorization": PEXELS_KEY}
        for query in [keywords, "india news city"]:
            params = {"query": query, "per_page": 3, "orientation": "portrait"}
            r = requests.get("https://api.pexels.com/v1/search",
                             headers=headers, params=params, timeout=15)
            print(f"  [Pexels photo] query='{query}' status={r.status_code}")
            if r.status_code != 200:
                continue
            photos = r.json().get("photos", [])
            if not photos:
                continue
            img_url = photos[0]["src"].get("portrait") or photos[0]["src"].get("large", "")
            if not img_url:
                continue
            resp = requests.get(img_url, timeout=30)
            if resp.status_code != 200:
                continue
            img = Image.open(io.BytesIO(resp.content)).convert("RGB").resize((W, H), Image.LANCZOS)
            img.save(out_path)
            print(f"  [Pexels photo] Saved background photo")
            return True
    except Exception as e:
        print(f"  [Pexels photo] Error: {e}")
    return False


def download_pixabay_video(keywords, out_path):
    if not PIXABAY_KEY:
        print("  [Pixabay] No PIXABAY_API_KEY set -- get free key at pixabay.com/api/docs/")
        return False
    try:
        for query in [keywords, "india news city people"]:
            params = {
                "key": PIXABAY_KEY,
                "q": query,
                "video_type": "film",
                "per_page": 5,
                "safesearch": "true",
            }
            r = requests.get("https://pixabay.com/api/videos/", params=params, timeout=15)
            print(f"  [Pixabay video] query='{query}' status={r.status_code}")
            if r.status_code != 200:
                continue
            hits = r.json().get("hits", [])
            if not hits:
                continue
            videos_info = hits[0].get("videos", {})
            chosen_url = (
                videos_info.get("medium", {}).get("url")
                or videos_info.get("small", {}).get("url")
                or videos_info.get("large", {}).get("url")
            )
            if not chosen_url:
                continue
            print(f"  [Pixabay video] Downloading ...")
            resp = requests.get(chosen_url, stream=True, timeout=90)
            if resp.status_code != 200:
                continue
            downloaded = 0
            with open(out_path, "wb") as f:
                for chunk in resp.iter_content(65536):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if downloaded > 30 * 1024 * 1024:
                        break
            sz = os.path.getsize(out_path)
            print(f"  [Pixabay video] Got {sz/1024/1024:.1f} MB")
            return sz > 100_000
    except Exception as e:
        print(f"  [Pixabay video] Error: {e}")
    return False


def download_pixabay_photo(keywords, out_path):
    if not PIXABAY_KEY:
        return False
    try:
        for query in [keywords, "india city news"]:
            params = {
                "key": PIXABAY_KEY,
                "q": query,
                "image_type": "photo",
                "per_page": 5,
                "safesearch": "true",
                "orientation": "vertical",
            }
            r = requests.get("https://pixabay.com/api/", params=params, timeout=15)
            print(f"  [Pixabay photo] query='{query}' status={r.status_code}")
            if r.status_code != 200:
                continue
            hits = r.json().get("hits", [])
            if not hits:
                continue
            img_url = hits[0].get("largeImageURL") or hits[0].get("webformatURL", "")
            if not img_url:
                continue
            resp = requests.get(img_url, timeout=30)
            if resp.status_code != 200:
                continue
            img = Image.open(io.BytesIO(resp.content)).convert("RGB").resize((W, H), Image.LANCZOS)
            img.save(out_path)
            print(f"  [Pixabay photo] Saved background photo")
            return True
    except Exception as e:
        print(f"  [Pixabay photo] Error: {e}")
    return False


def load_font(size, tamil=False):
    candidates = []
    if tamil:
        candidates = [
            "/usr/share/fonts/truetype/noto/NotoSansTamil-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansTamil[wdth,wght].ttf",
            "/usr/share/fonts/opentype/noto/NotoSansTamil-Regular.otf",
            "/usr/share/fonts/truetype/lohit-tamil/Lohit-Tamil.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        ]
    for path in candidates:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
                tmp  = Image.new("RGB", (10, 10))
                ImageDraw.Draw(tmp).text((0, 0), "A", font=font)
                print(f"  Font: {os.path.basename(path)} size={size}")
                return font
            except Exception:
                continue
    print(f"  WARNING: default font (size={size})")
    return ImageFont.load_default()


def text_w(draw, text, font):
    try:
        b = draw.textbbox((0, 0), text, font=font)
        return b[2] - b[0]
    except Exception:
        return len(text) * max(getattr(font, "size", 12), 8)


def text_h(draw, text, font):
    try:
        b = draw.textbbox((0, 0), text, font=font)
        return b[3] - b[1]
    except Exception:
        return max(getattr(font, "size", 12), 8) + 4


def wrap_text(draw, text, font, max_w):
    if not text.strip():
        return []
    words, lines, cur = text.split(), [], ""
    for word in words:
        test = (cur + " " + word).strip()
        if text_w(draw, test, font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [text]


def shadow_text(draw, xy, text, font, fill=(255, 255, 255), shadow=(0, 0, 0), off=2):
    x, y = xy
    for dx in [-off, 0, off]:
        for dy in [-off, 0, off]:
            if dx or dy:
                draw.text((x + dx, y + dy), text, font=font, fill=shadow)
    draw.text((x, y), text, font=font, fill=fill)


def center_shadow(draw, text, font, y, fill=(255, 255, 255)):
    tw = text_w(draw, text, font)
    x  = max(20, (W - tw) // 2)
    shadow_text(draw, (x, y), text, font, fill=fill)


def make_gradient_frame(t):
    """Animated dark-blue gradient -- always works, no API needed."""
    try:
        pulse = int(8 * np.sin(t * 0.7))
        arr   = np.zeros((H, W, 3), dtype=np.uint8)
        ys    = np.arange(H, dtype=np.float32) / H
        arr[:, :, 0] = np.clip(10 + (ys * 20).astype(int) + pulse, 0, 255)[:, None]
        arr[:, :, 1] = np.clip(10 + (ys * 15).astype(int),         0, 255)[:, None]
        arr[:, :, 2] = np.clip(50 + (ys * 80).astype(int) + pulse * 2, 0, 255)[:, None]
        return arr
    except Exception:
        arr = np.zeros((H, W, 3), dtype=np.uint8)
        arr[:, :, 2] = 80
        return arr


def compose_frame(bg_frame, topic, caption_text,
                  font_ch, font_topic, font_cap, font_ad, font_ad2):
    try:
        img = Image.fromarray(bg_frame.astype(np.uint8), "RGB")
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 110))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(img)

        draw.rectangle([0, 0, W, 130], fill=(10, 20, 80))
        draw.rectangle([0, 128, W, 138], fill=(220, 30, 30))
        shadow_text(draw, (30, 15),  CHANNEL,         font_ch,  fill=(255, 255, 255))
        shadow_text(draw, (30, 82),  "BREAKING NEWS", font_ad2, fill=(255, 80, 80))

        draw.rectangle([0, 138, W, 270], fill=(0, 0, 0, 170))
        ty = 148
        for line in wrap_text(draw, topic[:80], font_topic, W - 60)[:2]:
            shadow_text(draw, (30, ty), line, font_topic, fill=(255, 215, 0))
            ty += 58

        if caption_text.strip():
            cap_lines = wrap_text(draw, caption_text, font_cap, W - 80)[:5]
            lh        = text_h(draw, "A", font_cap) + 18
            total_h   = len(cap_lines) * lh
            cy        = (H - total_h) // 2 + 60
            pad       = 22
            draw.rectangle([30, cy - pad, W - 30, cy + total_h + pad], fill=(0, 0, 0, 160))
            for line in cap_lines:
                center_shadow(draw, line, font_cap, cy, fill=(255, 255, 255))
                cy += lh

        ft = H - 160
        draw.rectangle([0, ft, W, H],        fill=(180, 10, 10))
        draw.rectangle([0, ft, W, ft + 4],   fill=(255, 215, 0))
        center_shadow(draw, AD_LINE1, font_ad,  ft + 20,  fill=(255, 255, 255))
        center_shadow(draw, AD_LINE2, font_ad2, ft + 88,  fill=(255, 230, 0))

        return np.array(img)
    except Exception as e:
        print(f"  [compose] frame error: {e}")
        return bg_frame.astype(np.uint8)


def extract_spoken_text(script_text):
    lines, spoken, skip = script_text.split("\n"), [], False
    skip_kw = ["HASHTAGS", "CAPTION", "FORMAT", "RULES"]
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if any(k in line.upper() for k in skip_kw):
            skip = True; continue
        if line.startswith(("HOOK", "STORY", "CTA", "TRUTH")):
            skip = False; continue
        if skip or line.startswith(("[", "---", "#")):
            continue
        if not line.isupper():
            spoken.append(line)
    return " ".join(spoken)


def split_into_segments(text, n):
    words = text.split()
    if not words:
        return [""] * n
    chunk = max(1, len(words) // n)
    segs  = []
    for i in range(n):
        s = i * chunk
        e = s + chunk if i < n - 1 else len(words)
        segs.append(" ".join(words[s:e]))
    return segs


def check_ffmpeg():
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=10)
        print(f"  ffmpeg: {result.stdout.splitlines()[0] if result.stdout else 'found'}")
        return True
    except Exception as e:
        print(f"  WARNING: ffmpeg check failed: {e}")
        return False


def create_news_video(audio_path, spoken_text, topic, output_path,
                      bg_video_path=None, bg_photo_path=None):
    from moviepy.editor import VideoClip, AudioFileClip, VideoFileClip, concatenate_videoclips

    print(f"  Loading audio: {audio_path}")
    audio    = AudioFileClip(audio_path)
    duration = audio.duration
    print(f"  Duration: {duration:.1f}s")

    num_segs = max(1, int(duration / 4))
    segments = split_into_segments(spoken_text or topic, num_segs)
    seg_dur  = duration / num_segs

    print("  Loading fonts ...")
    font_ch    = load_font(52)
    font_topic = load_font(44)
    font_cap   = load_font(56, tamil=True)
    font_ad    = load_font(52)
    font_ad2   = load_font(38)

    bg_clip = None
    if bg_video_path and os.path.exists(bg_video_path):
        try:
            raw = VideoFileClip(bg_video_path)
            print(f"  BG video: {raw.w}x{raw.h} {raw.duration:.1f}s")
            if raw.duration < duration:
                loops = int(duration / raw.duration) + 2
                raw   = concatenate_videoclips([raw] * loops)
            raw = raw.subclip(0, duration)
            if raw.h < H:
                raw = raw.resize(height=H)
            if raw.w < W:
                raw = raw.resize(width=W)
            if raw.w > W:
                raw = raw.crop(x_center=raw.w / 2, width=W)
            if raw.h > H:
                raw = raw.crop(y_center=raw.h / 2, height=H)
            bg_clip = raw
            print(f"  BG video ready: {bg_clip.w}x{bg_clip.h}")
        except Exception as e:
            print(f"  BG video failed: {e}")
            bg_clip = None

    bg_photo = None
    if bg_clip is None and bg_photo_path and os.path.exists(bg_photo_path):
        try:
            img      = Image.open(bg_photo_path).convert("RGB").resize((W, H), Image.LANCZOS)
            bg_photo = np.array(img)
            print("  BG photo ready")
        except Exception as e:
            print(f"  BG photo failed: {e}")

    if bg_clip is None and bg_photo is None:
        print("  Using animated gradient background (no external API needed)")

    def make_frame(t):
        try:
            if bg_clip is not None:
                raw = bg_clip.get_frame(t)
                if raw.shape[:2] != (H, W):
                    raw = np.array(Image.fromarray(raw).resize((W, H), Image.LANCZOS))
            elif bg_photo is not None:
                raw = bg_photo.copy()
            else:
                raw = make_gradient_frame(t)
        except Exception as e:
            print(f"  make_frame bg error at t={t:.2f}: {e}")
            raw = make_gradient_frame(t)

        seg_idx = min(int(t / seg_dur), num_segs - 1)
        return compose_frame(raw, topic, segments[seg_idx],
                             font_ch, font_topic, font_cap, font_ad, font_ad2)

    print("  Building VideoClip ...")
    clip  = VideoClip(make_frame, duration=duration)
    final = clip.set_audio(audio)

    print(f"  Writing -> {output_path}")
    final.write_videofile(
        output_path,
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        logger="bar",
        threads=2,
        preset="ultrafast",
    )
    audio.close()
    final.close()
    if bg_clip:
        bg_clip.close()

    if os.path.exists(output_path):
        sz = os.path.getsize(output_path) / (1024 * 1024)
        print(f"  Video written: {sz:.1f} MB")
        return True
    else:
        print("  ERROR: Output file not found after write!")
        return False


def main():
    print("Tamil News Video Creator v4 (Pexels + Pixabay BG + Gradient fallback)")
    print(f"Time : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"PEXELS_API_KEY  : {'SET' if PEXELS_KEY  else 'NOT SET'}")
    print(f"PIXABAY_API_KEY : {'SET' if PIXABAY_KEY else 'NOT SET -- gradient will be used'}")

    check_ffmpeg()
    os.makedirs(VIDEO_DIR,  exist_ok=True)
    os.makedirs(ASSETS_DIR, exist_ok=True)

    try:
        with open(SCRIPTS_FILE, "r", encoding="utf-8") as f:
            scripts_data = json.load(f)["scripts"]
    except FileNotFoundError:
        print("ERROR: scripts.json not found!"); sys.exit(1)

    try:
        with open(os.path.join(AUDIO_DIR, "manifest.json"), "r") as f:
            audio_files = json.load(f)["audio_files"]
    except FileNotFoundError:
        print("ERROR: Audio manifest not found!"); sys.exit(1)

    print(f"\nScripts: {len(scripts_data)}  Audio: {len(audio_files)}\n")
    created_videos = []

    for i, (script_data, audio_data) in enumerate(zip(scripts_data, audio_files), 1):
        topic = script_data.get("topic", f"News {i}")
        print(f"\n{'='*60}")
        print(f"Video {i}/{len(scripts_data)}: {topic[:60]}")
        print(f"{'='*60}")

        audio_path = audio_data.get("audio_file", "")
        if not os.path.exists(audio_path):
            print(f"  ERROR: Audio not found: {audio_path}"); continue

        spoken_text = extract_spoken_text(script_data.get("script", "")) or topic
        keywords    = get_topic_keywords(topic)
        timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")

        bg_vid_path    = os.path.join(ASSETS_DIR, f"bg_video_{i}.mp4")
        bg_photo_path  = os.path.join(ASSETS_DIR, f"bg_photo_{i}.jpg")
        pix_vid_path   = os.path.join(ASSETS_DIR, f"pbay_video_{i}.mp4")
        pix_photo_path = os.path.join(ASSETS_DIR, f"pbay_photo_{i}.jpg")
        output_path    = os.path.join(VIDEO_DIR, f"reel_{i}_{timestamp}.mp4")

        print(f"  Keywords: '{keywords}'")

        got_video = got_photo = False
        final_vid = final_photo = None

        print("  Trying Pexels video ...")
        if download_pexels_video(keywords, bg_vid_path):
            got_video = True; final_vid = bg_vid_path

        if not got_video:
            print("  Trying Pixabay video ...")
            if download_pixabay_video(keywords, pix_vid_path):
                got_video = True; final_vid = pix_vid_path

        if not got_video:
            print("  Trying Pexels photo ...")
            if download_pexels_photo(keywords, bg_photo_path):
                got_photo = True; final_photo = bg_photo_path

        if not got_video and not got_photo:
            print("  Trying Pixabay photo ...")
            if download_pixabay_photo(keywords, pix_photo_path):
                got_photo = True; final_photo = pix_photo_path

        if not got_video and not got_photo:
            print("  No external background -- using animated gradient")

        try:
            success = create_news_video(
                audio_path, spoken_text, topic, output_path,
                bg_video_path = final_vid,
                bg_photo_path = final_photo,
            )
            if success and os.path.exists(output_path):
                sz = os.path.getsize(output_path) / (1024 * 1024)
                created_videos.append({
                    "topic":      topic,
                    "video_file": output_path,
                    "size_mb":    round(sz, 1),
                    "bg_source":  "video" if got_video else ("photo" if got_photo else "gradient"),
                })
                print(f"  Done: {sz:.1f} MB saved")
            else:
                print(f"  FAILED: Video not created for: {topic}")
        except Exception as e:
            print(f"  Exception: {e}")
            import traceback; traceback.print_exc()

    manifest_path = os.path.join(VIDEO_DIR, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "videos":     created_videos,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "count":      len(created_videos),
        }, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"DONE: {len(created_videos)}/{len(scripts_data)} videos created -> {VIDEO_DIR}")
    if not created_videos:
        print("ZERO videos created -- check logs above for errors")
        sys.exit(1)


if __name__ == "__main__":
    main()
