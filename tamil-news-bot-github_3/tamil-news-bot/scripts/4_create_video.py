"""
STEP 4: Tamil News Video Creator (v5 - Wav2Lip)
Priority: Wav2Lip talking head -> Pexels/Pixabay video -> photo -> gradient
- News anchor face auto-downloaded from Pexels/Pixabay
- Wav2Lip generates lip-synced talking head from face + audio
- Tamil captions synced every ~4 seconds
- Footer: Coimbatore Veedu Builders | 8111024877
"""

import json, os, io, sys, subprocess, requests, numpy as np
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

SCRIPTS_FILE = os.path.join(os.path.dirname(__file__), "../output/scripts.json")
AUDIO_DIR    = os.path.join(os.path.dirname(__file__), "../output/audio")
VIDEO_DIR    = os.path.join(os.path.dirname(__file__), "../output/videos")
ASSETS_DIR   = os.path.join(os.path.dirname(__file__), "../assets")

W, H = 1080, 1920
FPS  = 25   # Wav2Lip default is 25fps

AD_LINE1 = "Coimbatore Veedu Builders"
AD_LINE2 = "Contact: 8111024877"
CHANNEL  = "Tamil News Live"

PEXELS_KEY  = os.environ.get("PEXELS_API_KEY", "")
PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY", "")

WAV2LIP_DIR        = "/tmp/Wav2Lip"
WAV2LIP_CHECKPOINT = os.path.join(WAV2LIP_DIR, "checkpoints/wav2lip.pth")


# -- Face image (news anchor) --
def get_anchor_face(assets_dir):
    face_path = os.path.join(assets_dir, "anchor_face.jpg")
    if os.path.exists(face_path) and os.path.getsize(face_path) > 5000:
        print(f"  [Face] Using cached face: {face_path}")
        return face_path

    searches = [
        ("pexels_video", "woman news presenter professional portrait"),
        ("pexels_video", "female news anchor"),
        ("pixabay",      "woman portrait professional"),
    ]
    for src, query in searches:
        try:
            if src == "pexels_video" and PEXELS_KEY:
                headers = {"Authorization": PEXELS_KEY}
                params  = {"query": query, "per_page": 3, "orientation": "portrait"}
                r = requests.get("https://api.pexels.com/v1/search",
                                 headers=headers, params=params, timeout=15)
                if r.status_code == 200:
                    photos = r.json().get("photos", [])
                    for ph in photos:
                        url = ph["src"].get("medium") or ph["src"].get("large", "")
                        if not url:
                            continue
                        resp = requests.get(url, timeout=30)
                        if resp.status_code == 200:
                            img = Image.open(io.BytesIO(resp.content)).convert("RGB")
                            iw, ih = img.size
                            size = min(iw, ih)
                            left = (iw - size) // 2
                            top  = max(0, (ih - size) // 4)
                            img  = img.crop((left, top, left + size, min(ih, top + int(size * 1.3))))
                            img  = img.resize((480, 640), Image.LANCZOS)
                            img.save(face_path, quality=95)
                            print(f"  [Face] Downloaded from Pexels: {query}")
                            return face_path
            elif src == "pixabay" and PIXABAY_KEY:
                params = {"key": PIXABAY_KEY, "q": query, "image_type": "photo",
                          "per_page": 3, "safesearch": "true", "orientation": "vertical"}
                r = requests.get("https://pixabay.com/api/", params=params, timeout=15)
                if r.status_code == 200:
                    hits = r.json().get("hits", [])
                    for hit in hits:
                        url = hit.get("webformatURL", "")
                        if not url:
                            continue
                        resp = requests.get(url, timeout=30)
                        if resp.status_code == 200:
                            img = Image.open(io.BytesIO(resp.content)).convert("RGB")
                            img = img.resize((480, 640), Image.LANCZOS)
                            img.save(face_path, quality=95)
                            print(f"  [Face] Downloaded from Pixabay")
                            return face_path
        except Exception as e:
            print(f"  [Face] Error ({src}): {e}")

    print("  [Face] Could not download face image")
    return None


# -- Wav2Lip inference --
def run_wav2lip(face_path, audio_path, output_path):
    if not os.path.exists(WAV2LIP_DIR):
        print("  [Wav2Lip] Not installed at /tmp/Wav2Lip -- skipping")
        return False
    if not os.path.exists(WAV2LIP_CHECKPOINT):
        print(f"  [Wav2Lip] Checkpoint missing: {WAV2LIP_CHECKPOINT}")
        return False
    if not face_path or not os.path.exists(face_path):
        print("  [Wav2Lip] No face image -- skipping")
        return False

    wav_path = audio_path.rsplit('.', 1)[0] + '_wl16k.wav'
    print("  [Wav2Lip] Converting audio to 16kHz WAV...")
    conv = subprocess.run(
        ['ffmpeg', '-y', '-i', audio_path, '-ar', '16000', '-ac', '1', wav_path],
        capture_output=True, text=True, timeout=60
    )
    if conv.returncode != 0:
        print(f"  [Wav2Lip] Audio conversion failed: {conv.stderr[:300]}")
        return False

    cmd = [
        sys.executable, 'inference.py',
        '--checkpoint_path', WAV2LIP_CHECKPOINT,
        '--face', face_path,
        '--audio', wav_path,
        '--outfile', output_path,
        '--resize_factor', '2',
        '--nosmooth',
    ]
    print("  [Wav2Lip] Running inference (CPU, may take ~10-15 min)...")
    try:
        proc = subprocess.run(cmd, cwd=WAV2LIP_DIR, capture_output=True,
                              text=True, timeout=1200)
        if proc.stdout:
            print("  [Wav2Lip OUT]", proc.stdout[-800:])
        if proc.returncode != 0:
            print(f"  [Wav2Lip ERR] code={proc.returncode}")
            print(proc.stderr[-400:] if proc.stderr else "")
            return False
        if os.path.exists(output_path) and os.path.getsize(output_path) > 10_000:
            sz = os.path.getsize(output_path) / 1024 / 1024
            print(f"  [Wav2Lip] Done -- {sz:.1f} MB talking head generated")
            return True
        print("  [Wav2Lip] Output file not found or too small")
        return False
    except subprocess.TimeoutExpired:
        print("  [Wav2Lip] Timeout after 20 min")
        return False
    except Exception as e:
        print(f"  [Wav2Lip] Exception: {e}")
        return False


# -- API downloaders --
def download_pexels_video(keywords, out_path):
    if not PEXELS_KEY:
        return False
    try:
        headers = {"Authorization": PEXELS_KEY}
        for query in [keywords, "news television broadcast india"]:
            params = {"query": query, "per_page": 5, "orientation": "portrait"}
            r = requests.get("https://api.pexels.com/videos/search",
                             headers=headers, params=params, timeout=15)
            if r.status_code != 200:
                continue
            videos = r.json().get("videos", [])
            if not videos:
                continue
            files     = videos[0].get("video_files", [])
            portrait  = [f for f in files if f.get("width", 0) < f.get("height", 0)]
            cands     = sorted(portrait or files, key=lambda f: f.get("width", 9999))
            url       = cands[0].get("link", "") if cands else ""
            if not url:
                continue
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
            if os.path.getsize(out_path) > 100_000:
                print(f"  [Pexels video] Got {os.path.getsize(out_path)/1024/1024:.1f} MB")
                return True
    except Exception as e:
        print(f"  [Pexels video] {e}")
    return False


def download_pixabay_video(keywords, out_path):
    if not PIXABAY_KEY:
        return False
    try:
        for query in [keywords, "india news city people"]:
            params = {"key": PIXABAY_KEY, "q": query, "video_type": "film",
                      "per_page": 5, "safesearch": "true"}
            r = requests.get("https://pixabay.com/api/videos/", params=params, timeout=15)
            if r.status_code != 200:
                continue
            hits = r.json().get("hits", [])
            if not hits:
                continue
            vids = hits[0].get("videos", {})
            url  = (vids.get("medium", {}).get("url")
                    or vids.get("small",  {}).get("url")
                    or vids.get("large",  {}).get("url"))
            if not url:
                continue
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
            if os.path.getsize(out_path) > 100_000:
                print(f"  [Pixabay video] Got {os.path.getsize(out_path)/1024/1024:.1f} MB")
                return True
    except Exception as e:
        print(f"  [Pixabay video] {e}")
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
            if r.status_code != 200:
                continue
            photos = r.json().get("photos", [])
            if not photos:
                continue
            url = photos[0]["src"].get("portrait") or photos[0]["src"].get("large", "")
            resp = requests.get(url, timeout=30)
            if resp.status_code != 200:
                continue
            img = Image.open(io.BytesIO(resp.content)).convert("RGB").resize((W, H), Image.LANCZOS)
            img.save(out_path)
            print(f"  [Pexels photo] Saved")
            return True
    except Exception as e:
        print(f"  [Pexels photo] {e}")
    return False


def download_pixabay_photo(keywords, out_path):
    if not PIXABAY_KEY:
        return False
    try:
        for query in [keywords, "india city news"]:
            params = {"key": PIXABAY_KEY, "q": query, "image_type": "photo",
                      "per_page": 5, "safesearch": "true", "orientation": "vertical"}
            r = requests.get("https://pixabay.com/api/", params=params, timeout=15)
            if r.status_code != 200:
                continue
            hits = r.json().get("hits", [])
            if not hits:
                continue
            url = hits[0].get("largeImageURL") or hits[0].get("webformatURL", "")
            resp = requests.get(url, timeout=30)
            if resp.status_code != 200:
                continue
            img = Image.open(io.BytesIO(resp.content)).convert("RGB").resize((W, H), Image.LANCZOS)
            img.save(out_path)
            print(f"  [Pixabay photo] Saved")
            return True
    except Exception as e:
        print(f"  [Pixabay photo] {e}")
    return False


# -- Font loader --
def load_font(size, tamil=False):
    paths = ([
        "/usr/share/fonts/truetype/noto/NotoSansTamil-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansTamil[wdth,wght].ttf",
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
                ImageDraw.Draw(Image.new("RGB", (10,10))).text((0,0), "A", font=font)
                return font
            except Exception:
                continue
    return ImageFont.load_default()


# -- Text helpers --
def tw(draw, text, font):
    try:
        b = draw.textbbox((0,0), text, font=font); return b[2]-b[0]
    except Exception:
        return len(text) * max(getattr(font,"size",12), 8)

def th(draw, text, font):
    try:
        b = draw.textbbox((0,0), text, font=font); return b[3]-b[1]
    except Exception:
        return max(getattr(font,"size",12), 8) + 4

def wrap(draw, text, font, max_w):
    if not text.strip(): return []
    words, lines, cur = text.split(), [], ""
    for w2 in words:
        test = (cur+" "+w2).strip()
        if tw(draw, test, font) <= max_w: cur = test
        else:
            if cur: lines.append(cur)
            cur = w2
    if cur: lines.append(cur)
    return lines or [text]

def shadow(draw, xy, text, font, fill=(255,255,255), sh=(0,0,0), off=2):
    x, y = xy
    for dx in [-off, 0, off]:
        for dy in [-off, 0, off]:
            if dx or dy: draw.text((x+dx, y+dy), text, font=font, fill=sh)
    draw.text((x, y), text, font=font, fill=fill)

def cshadow(draw, text, font, y, fill=(255,255,255)):
    x = max(20, (W - tw(draw, text, font)) // 2)
    shadow(draw, (x, y), text, font, fill=fill)


# -- Gradient fallback --
def gradient_frame(t):
    try:
        p  = int(8 * np.sin(t * 0.7))
        a  = np.zeros((H, W, 3), dtype=np.uint8)
        ys = np.arange(H, dtype=np.float32) / H
        a[:,:,0] = np.clip(10+(ys*20).astype(int)+p, 0,255)[:,None]
        a[:,:,1] = np.clip(10+(ys*15).astype(int),   0,255)[:,None]
        a[:,:,2] = np.clip(50+(ys*80).astype(int)+p*2,0,255)[:,None]
        return a
    except Exception:
        a = np.zeros((H, W, 3), dtype=np.uint8); a[:,:,2]=80; return a


# -- News graphics overlay --
def draw_news_graphics(bg_frame, topic, caption_text,
                        font_ch, font_topic, font_cap, font_ad, font_ad2,
                        is_wav2lip=False):
    try:
        img = Image.fromarray(bg_frame.astype(np.uint8), "RGB")
        alpha = 60 if is_wav2lip else 110
        ov  = Image.new("RGBA", (W, H), (0, 0, 0, alpha))
        img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
        draw = ImageDraw.Draw(img)

        draw.rectangle([0, 0, W, 140], fill=(5, 15, 70))
        draw.rectangle([0, 138, W, 148], fill=(200, 20, 20))
        shadow(draw, (30, 18),  CHANNEL,          font_ch,  fill=(255,255,255))
        shadow(draw, (30, 90),  "BREAKING NEWS",  font_ad2, fill=(255,60,60))

        draw.rectangle([0, 148, W, 290], fill=(0,0,0,180))
        ty = 158
        for line in wrap(draw, topic[:80], font_topic, W-60)[:2]:
            shadow(draw, (30, ty), line, font_topic, fill=(255,215,0)); ty += 60

        if caption_text.strip():
            cap_lines = wrap(draw, caption_text, font_cap, W-80)[:5]
            lh = th(draw, "A", font_cap) + 18
            total_h = len(cap_lines) * lh
            cy  = (H - total_h) // 2 + 80
            pad = 24
            draw.rectangle([30, cy-pad, W-30, cy+total_h+pad], fill=(0,0,0,170))
            for line in cap_lines:
                cshadow(draw, line, font_cap, cy, fill=(255,255,255)); cy += lh

        ft = H - 160
        draw.rectangle([0, ft, W, H],      fill=(175, 8, 8))
        draw.rectangle([0, ft, W, ft+4],   fill=(255,215,0))
        cshadow(draw, AD_LINE1, font_ad,  ft+18,  fill=(255,255,255))
        cshadow(draw, AD_LINE2, font_ad2, ft+88,  fill=(255,230,0))

        return np.array(img)
    except Exception as e:
        print(f"  [graphics] Error: {e}")
        return bg_frame.astype(np.uint8)


# -- Text helpers --
def extract_spoken(script_text):
    lines, spoken, skip = script_text.split("\n"), [], False
    skip_kw = ["HASHTAGS","CAPTION","FORMAT","RULES"]
    for line in lines:
        line = line.strip()
        if not line: continue
        if any(k in line.upper() for k in skip_kw): skip=True; continue
        if line.startswith(("HOOK","STORY","CTA","TRUTH")): skip=False; continue
        if skip or line.startswith(("[","---","#")): continue
        if not line.isupper(): spoken.append(line)
    return " ".join(spoken)

def split_segs(text, n):
    words = text.split()
    if not words: return [""] * n
    chunk = max(1, len(words)//n)
    segs  = []
    for i in range(n):
        s = i*chunk
        e = s+chunk if i < n-1 else len(words)
        segs.append(" ".join(words[s:e]))
    return segs

def topic_keywords(topic):
    words = [w for w in topic.split() if all(ord(c)<128 for c in w) and len(w)>2]
    return " ".join(words[:4]) if words else "news breaking india city"


# -- Main video builder --
def create_news_video(audio_path, spoken_text, topic, output_path,
                      anchor_face=None,
                      bg_video_path=None, bg_photo_path=None):
    from moviepy.editor import VideoClip, AudioFileClip, VideoFileClip, concatenate_videoclips

    audio    = AudioFileClip(audio_path)
    duration = audio.duration
    print(f"  Audio: {duration:.1f}s")

    num_segs = max(1, int(duration / 4))
    segments = split_segs(spoken_text or topic, num_segs)
    seg_dur  = duration / num_segs

    font_ch    = load_font(52)
    font_topic = load_font(44)
    font_cap   = load_font(56, tamil=True)
    font_ad    = load_font(52)
    font_ad2   = load_font(38)

    wl_path    = output_path.replace('.mp4', '_wl.mp4')
    wl_success = run_wav2lip(anchor_face, audio_path, wl_path)
    wl_clip    = None

    if wl_success:
        try:
            raw = VideoFileClip(wl_path)
            print(f"  [Wav2Lip clip] {raw.w}x{raw.h} {raw.duration:.1f}s")
            if raw.duration < duration:
                loops = int(duration / raw.duration) + 2
                raw   = concatenate_videoclips([raw] * loops)
            raw = raw.subclip(0, duration)
            scale_h = H / raw.h
            scale_w = W / raw.w
            scale   = max(scale_h, scale_w)
            new_w   = int(raw.w * scale)
            new_h   = int(raw.h * scale)
            raw = raw.resize((new_w, new_h))
            if new_w > W:
                raw = raw.crop(x_center=new_w/2, width=W)
            if new_h > H:
                raw = raw.crop(y_center=new_h/2, height=H)
            wl_clip = raw
            print(f"  [Wav2Lip clip] Ready: {wl_clip.w}x{wl_clip.h}")
        except Exception as e:
            print(f"  [Wav2Lip clip] Load error: {e}")
            wl_clip = None

    bg_clip  = None
    bg_photo = None
    if wl_clip is None:
        if bg_video_path and os.path.exists(bg_video_path):
            try:
                raw = VideoFileClip(bg_video_path)
                if raw.duration < duration:
                    raw = concatenate_videoclips([raw]*(int(duration/raw.duration)+2))
                raw = raw.subclip(0, duration)
                raw = raw.resize(height=H) if raw.h < H else raw
                raw = raw.resize(width=W)  if raw.w < W else raw
                if raw.w > W: raw = raw.crop(x_center=raw.w/2, width=W)
                if raw.h > H: raw = raw.crop(y_center=raw.h/2, height=H)
                bg_clip = raw
                print(f"  [BG video] {bg_clip.w}x{bg_clip.h}")
            except Exception as e:
                print(f"  [BG video] {e}"); bg_clip = None

        if bg_clip is None and bg_photo_path and os.path.exists(bg_photo_path):
            try:
                bg_photo = np.array(
                    Image.open(bg_photo_path).convert("RGB").resize((W, H), Image.LANCZOS))
                print("  [BG photo] Loaded")
            except Exception as e:
                print(f"  [BG photo] {e}")

        if bg_clip is None and bg_photo is None:
            print("  [BG] Using animated gradient")

    def make_frame(t):
        try:
            if wl_clip is not None:
                frame = wl_clip.get_frame(t)
                if frame.shape[:2] != (H, W):
                    frame = np.array(Image.fromarray(frame).resize((W, H), Image.LANCZOS))
                is_wl = True
            elif bg_clip is not None:
                frame = bg_clip.get_frame(t)
                if frame.shape[:2] != (H, W):
                    frame = np.array(Image.fromarray(frame).resize((W, H), Image.LANCZOS))
                is_wl = False
            elif bg_photo is not None:
                frame = bg_photo.copy(); is_wl = False
            else:
                frame = gradient_frame(t); is_wl = False
        except Exception as e:
            print(f"  make_frame err t={t:.1f}: {e}")
            frame = gradient_frame(t); is_wl = False

        seg_idx = min(int(t / seg_dur), num_segs - 1)
        return draw_news_graphics(frame, topic, segments[seg_idx],
                                  font_ch, font_topic, font_cap,
                                  font_ad, font_ad2, is_wav2lip=is_wl)

    clip  = VideoClip(make_frame, duration=duration)
    final = clip.set_audio(audio)
    print(f"  Writing -> {output_path}")
    final.write_videofile(output_path, fps=FPS, codec="libx264",
                          audio_codec="aac", logger="bar",
                          threads=2, preset="ultrafast")
    audio.close(); final.close()
    if wl_clip: wl_clip.close()
    if bg_clip: bg_clip.close()

    if os.path.exists(output_path):
        sz = os.path.getsize(output_path)/1024/1024
        print(f"  Done: {sz:.1f} MB")
        if wl_success and os.path.exists(wl_path):
            os.remove(wl_path)
        return True
    print("  ERROR: output not found!")
    return False


# -- Entry point --
def main():
    print("Tamil News Video Creator v5 (Wav2Lip + Pexels + Pixabay + Gradient)")
    print(f"Time           : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"PEXELS_API_KEY : {'SET' if PEXELS_KEY  else 'NOT SET'}")
    print(f"PIXABAY_API_KEY: {'SET' if PIXABAY_KEY else 'NOT SET'}")
    print(f"WAV2LIP        : {'INSTALLED' if os.path.exists(WAV2LIP_CHECKPOINT) else 'NOT FOUND'}")

    try:
        r = subprocess.run(['ffmpeg','-version'],capture_output=True,text=True,timeout=10)
        print(f"ffmpeg         : {r.stdout.splitlines()[0] if r.stdout else 'found'}")
    except Exception as e:
        print(f"ffmpeg         : WARNING -- {e}")

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

    print(f"\nScripts: {len(scripts_data)}  Audio: {len(audio_files)}")

    print("\n--- Downloading news anchor face ---")
    anchor_face = get_anchor_face(ASSETS_DIR)

    created_videos = []

    for i, (script_data, audio_data) in enumerate(zip(scripts_data, audio_files), 1):
        topic = script_data.get("topic", f"News {i}")
        print(f"\n{'='*60}")
        print(f"Video {i}/{len(scripts_data)}: {topic[:60]}")
        print(f"{'='*60}")

        audio_path = audio_data.get("audio_file", "")
        if not os.path.exists(audio_path):
            print(f"  SKIP: Audio not found: {audio_path}"); continue

        spoken_text = extract_spoken(script_data.get("script","")) or topic
        keywords    = topic_keywords(topic)
        timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(VIDEO_DIR, f"reel_{i}_{timestamp}.mp4")

        bg_vid_path    = os.path.join(ASSETS_DIR, f"bg_video_{i}.mp4")
        bg_photo_path  = os.path.join(ASSETS_DIR, f"bg_photo_{i}.jpg")
        pix_vid_path   = os.path.join(ASSETS_DIR, f"pbay_video_{i}.mp4")
        pix_photo_path = os.path.join(ASSETS_DIR, f"pbay_photo_{i}.jpg")

        got_video = got_photo = False
        final_vid = final_photo = None

        if not os.path.exists(WAV2LIP_CHECKPOINT):
            print(f"  Keywords: '{keywords}'")
            if download_pexels_video(keywords, bg_vid_path):
                got_video=True; final_vid=bg_vid_path
            if not got_video and download_pixabay_video(keywords, pix_vid_path):
                got_video=True; final_vid=pix_vid_path
            if not got_video and download_pexels_photo(keywords, bg_photo_path):
                got_photo=True; final_photo=bg_photo_path
            if not got_video and not got_photo and download_pixabay_photo(keywords, pix_photo_path):
                got_photo=True; final_photo=pix_photo_path
            if not got_video and not got_photo:
                print("  Using gradient background")

        try:
            success = create_news_video(
                audio_path, spoken_text, topic, output_path,
                anchor_face   = anchor_face,
                bg_video_path = final_vid,
                bg_photo_path = final_photo,
            )
            if success and os.path.exists(output_path):
                sz = os.path.getsize(output_path)/1024/1024
                created_videos.append({
                    "topic":      topic,
                    "video_file": output_path,
                    "size_mb":    round(sz, 1),
                })
                print(f"  DONE: {sz:.1f} MB")
            else:
                print(f"  FAILED: {topic}")
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            import traceback; traceback.print_exc()

    manifest = os.path.join(VIDEO_DIR, "manifest.json")
    with open(manifest, "w", encoding="utf-8") as f:
        json.dump({"videos": created_videos,
                   "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                   "count": len(created_videos)}, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"DONE: {len(created_videos)}/{len(scripts_data)} videos -> {VIDEO_DIR}")
    if not created_videos:
        print("ZERO videos -- check logs"); sys.exit(1)


if __name__ == "__main__":
    main()
