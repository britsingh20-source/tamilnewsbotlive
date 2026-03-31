"""
STEP 4: Tamil News Video Creator (v3)
- Downloads relevant video from Pexels using PEXELS_API_KEY
- Falls back to relevant photo if no video found
- Falls back to gradient background as last resort
- Tamil captions rendered with Noto Tamil font
- Footer advertisement: Coimbatore Veedu Builders | 8111024877
"""

import json
import os
import io
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

AD_LINE1    = "Coimbatore Veedu Builders"
AD_LINE2    = "Contact: 8111024877"
CHANNEL     = "Tamil News Live"
PEXELS_KEY  = os.environ.get("PEXELS_API_KEY", "")


def get_topic_keywords(topic):
    ascii_words = [w for w in topic.split() if all(ord(c) < 128 for c in w)]
    return " ".join(ascii_words[:4]) if ascii_words else "news breaking india"


def download_pexels_video(keywords, out_path):
    if not PEXELS_KEY:
        print("  No PEXELS_API_KEY, skipping"); return False
    try:
        headers = {"Authorization": PEXELS_KEY}
        videos = []
        for query in [keywords, "news television broadcast"]:
            r = requests.get("https://api.pexels.com/videos/search", headers=headers,
                             params={"query": query, "per_page": 5, "orientation": "portrait"}, timeout=15)
            if r.status_code == 200:
                videos = r.json().get("videos", [])
                if videos: break
        if not videos: return False
        files = videos[0].get("video_files", [])
        portrait = [f for f in files if f.get("width", 0) < f.get("height", 0)]
        cands = sorted(portrait or files, key=lambda f: f.get("width", 0))
        url = cands[0].get("link", "")
        if not url: return False
        print(f"  Downloading Pexels video...")
        resp = requests.get(url, stream=True, timeout=60)
        if resp.status_code != 200: return False
        downloaded = 0
        with open(out_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk); downloaded += len(chunk)
                if downloaded > 30 * 1024 * 1024: break
        return os.path.getsize(out_path) > 100000
    except Exception as e:
        print(f"  Pexels video error: {e}"); return False


def download_pexels_photo(keywords, out_path):
    if not PEXELS_KEY: return False
    try:
        headers = {"Authorization": PEXELS_KEY}
        r = requests.get("https://api.pexels.com/v1/search", headers=headers,
                         params={"query": keywords, "per_page": 3, "orientation": "portrait"}, timeout=15)
        if r.status_code != 200: return False
        photos = r.json().get("photos", [])
        if not photos: return False
        img_url = photos[0]["src"].get("portrait") or photos[0]["src"]["large"]
        resp = requests.get(img_url, timeout=30)
        if resp.status_code != 200: return False
        img = Image.open(io.BytesIO(resp.content)).convert("RGB").resize((W, H), Image.LANCZOS)
        img.save(out_path)
        print("  Downloaded Pexels photo background"); return True
    except Exception as e:
        print(f"  Pexels photo error: {e}"); return False


def load_font(size, tamil=False):
    paths = ([
        "/usr/share/fonts/truetype/noto/NotoSansTamil-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansTamil-Regular.otf",
        "/usr/share/fonts/truetype/lohit-tamil/Lohit-Tamil.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ] if tamil else [
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ])
    for p in paths:
        if os.path.exists(p):
            try:
                font = ImageFont.truetype(p, size)
                print(f"  Font OK: {os.path.basename(p)} sz={size}"); return font
            except Exception: continue
    print(f"  WARNING: default font sz={size}"); return ImageFont.load_default()


def twidth(draw, text, font):
    try:
        b = draw.textbbox((0, 0), text, font=font); return b[2] - b[0]
    except Exception: return len(text) * max(8, getattr(font, 'size', 10) // 2)


def theight(draw, text, font):
    try:
        b = draw.textbbox((0, 0), text, font=font); return b[3] - b[1]
    except Exception: return max(12, getattr(font, 'size', 12) + 4)


def wrap(draw, text, font, max_w):
    if not text.strip(): return []
    words = text.split(); lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if twidth(draw, test, font) <= max_w: cur = test
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines or [text[:40]]


def shadow(draw, xy, text, font, fill=(255,255,255), shd=(0,0,0), off=2):
    x, y = xy
    for dx in (-off, 0, off):
        for dy in (-off, 0, off):
            if dx or dy: draw.text((x+dx, y+dy), text, font=font, fill=shd)
    draw.text((x, y), text, font=font, fill=fill)


def center_shadow(draw, text, font, y, fill=(255,255,255)):
    w = twidth(draw, text, font); x = max(20, (W - w) // 2)
    shadow(draw, (x, y), text, font, fill=fill)


def make_gradient(t):
    p = int(8 * np.sin(t * 0.7))
    arr = np.zeros((H, W, 3), dtype=np.uint8)
    ratio = np.arange(H, dtype=np.float32) / H
    arr[:, :, 0] = np.clip(10 + (ratio * 20).astype(int) + p, 0, 255)[:, None]
    arr[:, :, 1] = np.clip(10 + (ratio * 15).astype(int), 0, 255)[:, None]
    arr[:, :, 2] = np.clip(50 + (ratio * 80).astype(int) + p*2, 0, 255)[:, None]
    return arr


def compose(bg_arr, topic, caption, font_ch, font_topic, font_cap, font_ad, font_ad2):
    img = Image.fromarray(bg_arr.astype(np.uint8)).convert("RGBA")
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 100))
    img = Image.alpha_composite(img, ov).convert("RGB")
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, W, 130], fill=(10, 20, 80))
    draw.rectangle([0, 128, W, 138], fill=(220, 30, 30))
    shadow(draw, (30, 15), CHANNEL, font_ch)
    shadow(draw, (30, 78), "BREAKING NEWS", font_ad2, fill=(255, 80, 80))

    draw.rectangle([0, 138, W, 265], fill=(0, 0, 0, 170))
    ty = 148
    for line in wrap(draw, topic[:80], font_topic, W-60)[:2]:
        shadow(draw, (30, ty), line, font_topic, fill=(255, 215, 0)); ty += 56

    if caption.strip():
        cap_lines = wrap(draw, caption, font_cap, W-80)[:5]
        lh = theight(draw, "A", font_cap) + 18
        total = len(cap_lines) * lh
        cy = max(350, (H - total)//2 + 40)
        draw.rectangle([25, cy-18, W-25, cy+total+18], fill=(0, 0, 0, 150))
        for line in cap_lines:
            center_shadow(draw, line, font_cap, cy); cy += lh

    ft = H - 165
    draw.rectangle([0, ft, W, H], fill=(180, 10, 10))
    draw.rectangle([0, ft, W, ft+5], fill=(255, 215, 0))
    center_shadow(draw, AD_LINE1, font_ad, ft+18, fill=(255, 255, 255))
    center_shadow(draw, AD_LINE2, font_ad2, ft+85, fill=(255, 230, 0))

    return np.array(img)


def extract_spoken(script_text):
    lines, parts, in_skip = script_text.split("\n"), [], False
    skip_kw = ["HASHTAGS", "CAPTION", "FORMAT", "RULES"]
    for line in lines:
        line = line.strip()
        if not line: continue
        if any(k in line.upper() for k in skip_kw): in_skip = True; continue
        if line.startswith(("HOOK","STORY","CTA","TRUTH")): in_skip = False; continue
        if in_skip or line.startswith(("[","---","#")): continue
        if line and not line.isupper(): parts.append(line)
    return " ".join(parts)


def make_segments(text, n):
    words = text.split()
    if not words: return [""] * n
    c = max(1, len(words)//n); segs = []
    for i in range(n):
        s, e = i*c, (i*c+c if i < n-1 else len(words))
        segs.append(" ".join(words[s:e]))
    return segs


def create_video(audio_path, spoken, topic, out_path, bg_vid=None, bg_photo=None):
    from moviepy.editor import VideoClip, AudioFileClip, VideoFileClip, concatenate_videoclips
    audio = AudioFileClip(audio_path)
    dur = audio.duration
    print(f"  Duration: {dur:.1f}s")
    n = max(1, int(dur/4))
    segs = make_segments(spoken, n)
    seg_d = dur / n
    font_ch    = load_font(50)
    font_topic = load_font(42)
    font_cap   = load_font(54, tamil=True)
    font_ad    = load_font(50)
    font_ad2   = load_font(36)
    vc = None
    if bg_vid and os.path.exists(bg_vid):
        try:
            raw = VideoFileClip(bg_vid)
            if raw.duration < dur:
                loops = int(dur/raw.duration) + 2
                raw = concatenate_videoclips([raw]*loops)
            raw = raw.subclip(0, dur).resize(height=H)
            if raw.w > W: raw = raw.crop(x_center=raw.w/2, width=W)
            elif raw.w < W: raw = raw.resize(width=W)
            vc = raw; print("  BG: Pexels video")
        except Exception as e:
            print(f"  BG video err: {e}")
    static_bg = None
    if vc is None and bg_photo and os.path.exists(bg_photo):
        try:
            static_bg = np.array(Image.open(bg_photo).convert("RGB").resize((W,H),Image.LANCZOS))
            print("  BG: Pexels photo")
        except Exception as e:
            print(f"  BG photo err: {e}")

    def make_frame(t):
        if vc is not None:
            frame = vc.get_frame(t)
            if frame.shape[:2] != (H, W):
                frame = np.array(Image.fromarray(frame).resize((W,H),Image.LANCZOS))
        elif static_bg is not None:
            frame = static_bg.copy()
        else:
            frame = make_gradient(t)
        idx = min(int(t/seg_d), n-1)
        return compose(frame, topic, segs[idx], font_ch, font_topic, font_cap, font_ad, font_ad2)

    clip = VideoClip(make_frame, duration=dur)
    final = clip.set_audio(audio)
    final.write_videofile(out_path, fps=FPS, codec="libx264",
                          audio_codec="aac", logger=None, threads=2, preset="ultrafast")
    audio.close(); final.close()
    if vc: vc.close()
    mb = os.path.getsize(out_path)/(1024*1024)
    print(f"  Done: {mb:.1f} MB"); return True


def main():
    print("Tamil News Video v3 - Pexels BG + Tamil captions + Ad footer")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    os.makedirs(VIDEO_DIR, exist_ok=True)
    os.makedirs(ASSETS_DIR, exist_ok=True)
    with open(SCRIPTS_FILE, "r", encoding="utf-8") as f:
        scripts = json.load(f)["scripts"]
    with open(os.path.join(AUDIO_DIR, "manifest.json"), "r") as f:
        audios = json.load(f)["audio_files"]
    print(f"Scripts: {len(scripts)} | Audio: {len(audios)}\n")
    created = []
    for i, (sd, ad) in enumerate(zip(scripts, audios), 1):
        topic = sd["topic"]
        print(f"\nVideo {i}: {topic[:55]}...")
        apath = ad["audio_file"]
        if not os.path.exists(apath):
            print(f"  Missing audio: {apath}"); continue
        spoken = extract_spoken(sd["script"]) or sd["script"][:500]
        kw = get_topic_keywords(topic)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        vid_bg   = os.path.join(ASSETS_DIR, f"bg_vid_{i}.mp4")
        photo_bg = os.path.join(ASSETS_DIR, f"bg_photo_{i}.jpg")
        out = os.path.join(VIDEO_DIR, f"reel_{i}_{ts}.mp4")
        print(f"  Searching Pexels: '{kw}'")
        has_vid   = download_pexels_video(kw, vid_bg)
        has_photo = download_pexels_photo(kw, photo_bg) if not has_vid else False
        try:
            create_video(apath, spoken, topic, out,
                         bg_vid=vid_bg   if has_vid   else None,
                         bg_photo=photo_bg if has_photo else None)
            if os.path.exists(out):
                mb = os.path.getsize(out)/(1024*1024)
                created.append({"topic": topic, "video_file": out, "size_mb": round(mb,1)})
        except Exception as e:
            print(f"  FAILED: {e}")
            import traceback; traceback.print_exc()
    with open(os.path.join(VIDEO_DIR,"manifest.json"),"w",encoding="utf-8") as f:
        json.dump({"videos": created, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")},
                  f, ensure_ascii=False, indent=2)
    print(f"\n{len(created)} videos done -> {VIDEO_DIR}")


if __name__ == "__main__":
    main()
