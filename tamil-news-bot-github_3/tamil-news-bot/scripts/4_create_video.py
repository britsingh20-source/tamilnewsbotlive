"""
STEP 4: Tamil News Video Creator (v9)
======================================
Pipeline: SadTalker (body motion) -> Wav2Lip (lip sync) -> MoviePy (graphics)

Changes over v8:
  A. Article image thumbnail -- fetched from article_image_url in scripts.json,
                                displayed as a small image in the topic bar
                                (right side of topic bar, next to headline)
  B. Dependencies check      -- clear error message if moviepy/PIL missing
  C. All v8 fixes kept       -- lower-third caption, header topic fix,
                                force anchor refresh, manifest merging,
                                Tamil font verification, robust HTTP retry

Install required packages on your machine:
  pip install moviepy gtts Pillow numpy requests
"""

import json, os, io, sys, time, subprocess, requests, numpy as np
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Dependency check -- clear error before silent crash
# ---------------------------------------------------------------------------
try:
    from moviepy.editor import VideoClip, AudioFileClip, VideoFileClip, concatenate_videoclips
except ImportError:
    print("=" * 60)
    print("ERROR: moviepy is not installed!")
    print("Run this command on your machine:")
    print("  pip install moviepy")
    print("=" * 60)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPTS_FILE = os.path.join(os.path.dirname(__file__), "../output/scripts.json")
AUDIO_DIR    = os.path.join(os.path.dirname(__file__), "../output/audio")
VIDEO_DIR    = os.path.join(os.path.dirname(__file__), "../output/videos")
ASSETS_DIR   = os.path.join(os.path.dirname(__file__), "../assets")

SUPPLIED_ANCHOR_PNG = os.path.join(os.path.dirname(__file__), "anchor_face_supplied.png")

W, H = 1080, 1920
FPS  = 25

AD_LINE1 = "Coimbatore Veedu Builders"
AD_LINE2 = "Contact: 8111024877"
CHANNEL  = "Tamil News Live"

PEXELS_KEY  = os.environ.get("PEXELS_API_KEY", "")
PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY", "")

SADTALKER_DIR        = "/tmp/SadTalker"
SADTALKER_SCRIPT     = os.path.join(SADTALKER_DIR, "inference.py")
SADTALKER_CHECKPOINT = os.path.join(SADTALKER_DIR, "checkpoints")

WAV2LIP_DIR        = "/tmp/Wav2Lip"
WAV2LIP_CHECKPOINT = os.path.join(WAV2LIP_DIR, "checkpoints/wav2lip.pth")

CAPTION_TOP_PCT    = 0.72
CAPTION_BOTTOM_PCT = 0.92

# Article thumbnail size in header
THUMB_W = 200
THUMB_H = 130


# ===========================================================================
# Robust HTTP
# ===========================================================================
def _robust_get(url, retries=3, backoff=2, **kwargs):
    last = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, **kwargs)
            if r.status_code < 500:
                return r
            raise requests.HTTPError(f"HTTP {r.status_code}")
        except Exception as e:
            last = e
            time.sleep(backoff ** attempt)
    raise last


# ===========================================================================
# A. Article image fetcher
# ===========================================================================
def fetch_article_thumbnail(image_url: str, cache_path: str):
    """
    Download article image from URL, resize to thumbnail, cache locally.
    Returns PIL Image or None.
    """
    if not image_url:
        return None

    # Use cached version if available
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 1000:
        try:
            return Image.open(cache_path).convert("RGB")
        except Exception:
            pass

    try:
        resp = _robust_get(image_url, timeout=15)
        if resp.status_code == 200:
            img = Image.open(io.BytesIO(resp.content)).convert("RGB")
            img = img.resize((THUMB_W, THUMB_H), Image.LANCZOS)
            img.save(cache_path)
            print(f"  [ArticleImg] Downloaded: {image_url[:60]}")
            return img
    except Exception as e:
        print(f"  [ArticleImg] Failed: {e}")
    return None


# ===========================================================================
# Font loading with Tamil verification
# ===========================================================================
TAMIL_FONT_PATHS = [
    "/usr/share/fonts/truetype/noto/NotoSansTamil-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansTamil[wdth,wght].ttf",
    "/usr/share/fonts/opentype/noto/NotoSansTamil-Regular.otf",
    "/usr/share/fonts/truetype/lohit-tamil/Lohit-Tamil.ttf",
]
LATIN_FONT_PATHS = [
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]

_font_cache        = {}
_tamil_font_ok     = None
_tamil_font_warned = False

def _font_renders_tamil(font):
    try:
        img  = Image.new("RGB", (60, 60), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((5, 5), "த", font=font, fill=(0, 0, 0))
        return bool((np.array(img)[10:50, 5:55] < 200).any())
    except Exception:
        return False

def _try_install_tamil():
    try:
        res = subprocess.run(
            ["sudo", "apt-get", "install", "-y", "fonts-noto-core", "fonts-lohit-taml"],
            capture_output=True, text=True, timeout=120)
        if res.returncode == 0:
            subprocess.run(["fc-cache", "-f", "-v"], capture_output=True, timeout=30)
            return True
    except Exception:
        pass
    return False

def load_font(size, tamil=False):
    global _tamil_font_ok, _tamil_font_warned
    key = (size, tamil)
    if key in _font_cache:
        return _font_cache[key]

    for p in (TAMIL_FONT_PATHS if tamil else LATIN_FONT_PATHS):
        if not os.path.exists(p):
            continue
        try:
            font = ImageFont.truetype(p, size)
            if tamil:
                if _font_renders_tamil(font):
                    _tamil_font_ok   = True
                    _font_cache[key] = font
                    return font
            else:
                _font_cache[key] = font
                return font
        except Exception:
            continue

    if tamil and not _tamil_font_warned:
        _tamil_font_warned = True
        _tamil_font_ok     = False
        print("  [Font] No Tamil font -- attempting auto-install...")
        if _try_install_tamil():
            for p in TAMIL_FONT_PATHS:
                if os.path.exists(p):
                    try:
                        font = ImageFont.truetype(p, size)
                        if _font_renders_tamil(font):
                            _tamil_font_ok   = True
                            _font_cache[key] = font
                            return font
                    except Exception:
                        pass
        print("  [Font] Run: sudo apt-get install fonts-noto-core fonts-lohit-taml")

    for p in LATIN_FONT_PATHS:
        if os.path.exists(p):
            try:
                font = ImageFont.truetype(p, size)
                _font_cache[key] = font
                return font
            except Exception:
                continue
    return ImageFont.load_default()


# ===========================================================================
# SadTalker
# ===========================================================================
def run_sadtalker(face_path, audio_path, out_dir):
    if not os.path.exists(SADTALKER_SCRIPT):
        print("  [SadTalker] Not installed -- skipping")
        return None
    if not os.path.exists(SADTALKER_CHECKPOINT):
        print("  [SadTalker] Checkpoints missing -- skipping")
        return None
    if not face_path or not os.path.exists(face_path):
        return None

    os.makedirs(out_dir, exist_ok=True)
    cmd = [
        sys.executable, SADTALKER_SCRIPT,
        "--driven_audio",     audio_path,
        "--source_image",     face_path,
        "--result_dir",       out_dir,
        "--enhancer",         "gfpgan",
        "--expression_scale", "1.2",
        "--pose_style",       "1",
        "--preprocess",       "full",
        "--size",             "256",
    ]
    print("  [SadTalker] Generating body motion (~15-30 min)...")
    try:
        proc = subprocess.run(cmd, cwd=SADTALKER_DIR, capture_output=True,
                              text=True, timeout=2400)
        if proc.returncode != 0:
            print(f"  [SadTalker ERR] {proc.stderr[-300:]}")
            return None
        found = []
        for root, dirs, files in os.walk(out_dir):
            for f in files:
                if f.endswith(".mp4"):
                    full = os.path.join(root, f)
                    found.append((os.path.getmtime(full), full))
        if not found:
            return None
        found.sort(reverse=True)
        print(f"  [SadTalker] Done: {found[0][1]}")
        return found[0][1]
    except subprocess.TimeoutExpired:
        print("  [SadTalker] Timeout")
        return None
    except Exception as e:
        print(f"  [SadTalker] {e}")
        return None


# ===========================================================================
# Wav2Lip
# ===========================================================================
def run_wav2lip(face_input, audio_path, output_path):
    if not os.path.exists(WAV2LIP_DIR):
        print("  [Wav2Lip] Not installed"); return False
    if not os.path.exists(WAV2LIP_CHECKPOINT):
        print("  [Wav2Lip] Checkpoint missing"); return False
    if not face_input or not os.path.exists(face_input):
        print("  [Wav2Lip] No face input"); return False

    wav_path = audio_path.rsplit('.', 1)[0] + '_wl16k.wav'
    conv = subprocess.run(
        ['ffmpeg', '-y', '-i', audio_path, '-ar', '16000', '-ac', '1', wav_path],
        capture_output=True, text=True, timeout=60)
    if conv.returncode != 0:
        print("  [Wav2Lip] Audio convert failed"); return False

    cmd = [
        sys.executable, 'inference.py',
        '--checkpoint_path',     WAV2LIP_CHECKPOINT,
        '--face',                face_input,
        '--audio',               wav_path,
        '--outfile',             output_path,
        '--resize_factor',       '1',
        '--pads',                '0', '15', '0', '0',
        '--face_det_batch_size', '4',
        '--wav2lip_batch_size',  '64',
    ]
    print(f"  [Wav2Lip] Running lip sync...")
    try:
        proc = subprocess.run(cmd, cwd=WAV2LIP_DIR, capture_output=True,
                              text=True, timeout=1800)
        if proc.returncode != 0:
            print(f"  [Wav2Lip ERR] {proc.stderr[-300:]}"); return False
        if os.path.exists(output_path) and os.path.getsize(output_path) > 10_000:
            print(f"  [Wav2Lip] Done: {os.path.getsize(output_path)/1e6:.1f} MB")
            return True
        return False
    except subprocess.TimeoutExpired:
        print("  [Wav2Lip] Timeout"); return False
    except Exception as e:
        print(f"  [Wav2Lip] {e}"); return False


# ===========================================================================
# Anchor face
# ===========================================================================
def prepare_anchor_face(assets_dir):
    face_path = os.path.join(assets_dir, "anchor_face.jpg")
    if os.path.exists(SUPPLIED_ANCHOR_PNG):
        try:
            img    = Image.open(SUPPLIED_ANCHOR_PNG).convert("RGB")
            iw, ih = img.size
            size   = min(iw, ih)
            left   = (iw - size) // 2
            top    = max(0, int((ih - size) * 0.05))
            bottom = min(ih, top + int(size * 1.15))
            img    = img.crop((left, top, left + size, bottom))
            img    = img.resize((480, 640), Image.LANCZOS)
            img.save(face_path, quality=95)
            print(f"  [Face] Saved from supplied PNG")
            return face_path
        except Exception as e:
            print(f"  [Face] Error: {e}")
    if os.path.exists(face_path) and os.path.getsize(face_path) > 5000:
        return face_path
    print("  [Face] WARNING: no anchor face image")
    return None


# ===========================================================================
# Background downloaders
# ===========================================================================
def _stream_video(url, out_path, max_mb=30):
    try:
        resp = _robust_get(url, stream=True, timeout=90)
        if resp.status_code != 200: return False
        downloaded = 0
        with open(out_path, "wb") as f:
            for chunk in resp.iter_content(65536):
                f.write(chunk); downloaded += len(chunk)
                if downloaded > max_mb * 1024 * 1024: break
        return os.path.getsize(out_path) > 100_000
    except Exception:
        return False

def download_pexels_video(keywords, out_path):
    if not PEXELS_KEY: return False
    try:
        for query in [keywords, "india news broadcast"]:
            r = _robust_get("https://api.pexels.com/videos/search",
                            headers={"Authorization": PEXELS_KEY},
                            params={"query": query, "per_page": 5,
                                    "orientation": "portrait"}, timeout=15)
            videos = r.json().get("videos", [])
            if not videos: continue
            files   = videos[0].get("video_files", [])
            portrait= [f for f in files if f.get("width", 0) < f.get("height", 0)]
            cands   = sorted(portrait or files, key=lambda f: f.get("width", 9999))
            url     = cands[0].get("link", "") if cands else ""
            if url and _stream_video(url, out_path): return True
    except Exception as e: print(f"  [Pexels video] {e}")
    return False

def download_pixabay_video(keywords, out_path):
    if not PIXABAY_KEY: return False
    try:
        for query in [keywords, "india news city"]:
            r = _robust_get("https://pixabay.com/api/videos/",
                            params={"key": PIXABAY_KEY, "q": query,
                                    "video_type": "film", "per_page": 5,
                                    "safesearch": "true"}, timeout=15)
            hits = r.json().get("hits", [])
            if not hits: continue
            vids = hits[0].get("videos", {})
            url  = (vids.get("medium", {}).get("url") or
                    vids.get("small",  {}).get("url") or
                    vids.get("large",  {}).get("url"))
            if url and _stream_video(url, out_path): return True
    except Exception as e: print(f"  [Pixabay video] {e}")
    return False

def download_pexels_photo(keywords, out_path):
    if not PEXELS_KEY: return False
    try:
        for query in [keywords, "india news"]:
            r = _robust_get("https://api.pexels.com/v1/search",
                            headers={"Authorization": PEXELS_KEY},
                            params={"query": query, "per_page": 3,
                                    "orientation": "portrait"}, timeout=15)
            photos = r.json().get("photos", [])
            if not photos: continue
            url  = photos[0]["src"].get("portrait") or photos[0]["src"].get("large", "")
            resp = _robust_get(url, timeout=30)
            if resp.status_code == 200:
                img = Image.open(io.BytesIO(resp.content)).convert("RGB").resize((W, H), Image.LANCZOS)
                img.save(out_path); return True
    except Exception as e: print(f"  [Pexels photo] {e}")
    return False

def download_pixabay_photo(keywords, out_path):
    if not PIXABAY_KEY: return False
    try:
        for query in [keywords, "india city news"]:
            r = _robust_get("https://pixabay.com/api/",
                            params={"key": PIXABAY_KEY, "q": query,
                                    "image_type": "photo", "per_page": 5,
                                    "safesearch": "true",
                                    "orientation": "vertical"}, timeout=15)
            hits = r.json().get("hits", [])
            if not hits: continue
            url  = hits[0].get("largeImageURL") or hits[0].get("webformatURL", "")
            resp = _robust_get(url, timeout=30)
            if resp.status_code == 200:
                img = Image.open(io.BytesIO(resp.content)).convert("RGB").resize((W, H), Image.LANCZOS)
                img.save(out_path); return True
    except Exception as e: print(f"  [Pixabay photo] {e}")
    return False


# ===========================================================================
# Text helpers
# ===========================================================================
def tw(draw, text, font):
    try:
        b = draw.textbbox((0, 0), text, font=font); return b[2] - b[0]
    except Exception:
        return len(text) * max(getattr(font, "size", 12), 8)

def th(draw, text, font):
    try:
        b = draw.textbbox((0, 0), text, font=font); return b[3] - b[1]
    except Exception:
        return max(getattr(font, "size", 12), 8) + 4

def wrap_text(draw, text, font, max_w):
    if not text.strip(): return []
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if tw(draw, test, font) <= max_w: cur = test
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines or [text]

def shadow_text(draw, xy, text, font, fill=(255, 255, 255), sh=(0, 0, 0), off=2):
    x, y = xy
    for dx in [-off, 0, off]:
        for dy in [-off, 0, off]:
            if dx or dy: draw.text((x+dx, y+dy), text, font=font, fill=sh)
    draw.text((x, y), text, font=font, fill=fill)

def centre_shadow(draw, text, font, y, fill=(255, 255, 255)):
    x = max(20, (W - tw(draw, text, font)) // 2)
    shadow_text(draw, (x, y), text, font, fill=fill)


# ===========================================================================
# Header topic -- clean Tamil or English fallback
# ===========================================================================
def _header_topic(topic: str) -> str:
    if _tamil_font_ok:
        return topic.strip(" '\"-.,:;")
    import re
    ascii_words = re.findall(r'[A-Za-z]{3,}', topic)
    noise = {"the","and","for","with","from","this","that","are","was",
             "were","has","have","will","been"}
    meaningful = [w for w in ascii_words if w.lower() not in noise]
    result = " ".join(meaningful[:7])
    return result.strip() if len(result.strip()) >= 3 else "Tamil Breaking News"


# ===========================================================================
# A. News graphics overlay -- article thumbnail in topic bar
# ===========================================================================
def draw_news_graphics(bg_frame, topic, caption_text,
                        font_ch, font_topic, font_cap, font_ad, font_ad2,
                        article_thumb=None,
                        is_wav2lip=False):
    try:
        img  = Image.fromarray(bg_frame.astype(np.uint8), "RGB")
        alpha = 40 if is_wav2lip else 100
        ov   = Image.new("RGBA", (W, H), (0, 0, 0, alpha))
        img  = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
        draw = ImageDraw.Draw(img)

        # ── TOP HEADER ───────────────────────────────────────────────────────
        draw.rectangle([0, 0, W, 145],   fill=(5, 15, 70))
        draw.rectangle([0, 143, W, 151], fill=(200, 20, 20))
        shadow_text(draw, (28, 16), CHANNEL,         font_ch,  fill=(255, 255, 255))
        shadow_text(draw, (28, 82), "BREAKING NEWS", font_ad2, fill=(255, 60,  60))

        # ── TOPIC BAR with article thumbnail ─────────────────────────────────
        topic_bar_h = 155  # height of topic bar
        draw.rectangle([0, 151, W, 151 + topic_bar_h], fill=(0, 0, 0, 210))
        draw.rectangle([0, 151, 8, 151 + topic_bar_h], fill=(200, 20, 20))

        # A. Paste article thumbnail on RIGHT side of topic bar
        text_right_limit = W - 20  # default: text goes full width
        if article_thumb is not None:
            try:
                thumb = article_thumb.resize((THUMB_W, THUMB_H), Image.LANCZOS)
                tx    = W - THUMB_W - 10
                ty    = 155  # vertically centred in topic bar
                # Red border around thumbnail
                border_rect = [tx - 3, ty - 3, tx + THUMB_W + 3, ty + THUMB_H + 3]
                draw.rectangle(border_rect, fill=(200, 20, 20))
                img.paste(thumb, (tx, ty))
                text_right_limit = tx - 16  # text stays left of thumbnail
                # Re-draw after paste
                draw = ImageDraw.Draw(img)
            except Exception as e:
                print(f"  [Thumb paste] {e}")

        # Topic text (left of thumbnail)
        display_topic = _header_topic(topic)
        ty = 164
        for line in wrap_text(draw, display_topic[:100], font_topic,
                               text_right_limit - 24)[:2]:
            shadow_text(draw, (24, ty), line, font_topic, fill=(255, 215, 0))
            ty += 60

        # ── LOWER-THIRD CAPTION (72%–92% of frame) ───────────────────────────
        if caption_text.strip():
            zone_top  = int(H * CAPTION_TOP_PCT)
            zone_bot  = int(H * CAPTION_BOTTOM_PCT)
            zone_h    = zone_bot - zone_top
            cap_lines = wrap_text(draw, caption_text, font_cap, W - 80)[:4]
            lh        = th(draw, "A", font_cap) + 16
            total_h   = len(cap_lines) * lh
            pad       = 20
            cy        = zone_top + max(0, (zone_h - total_h) // 2)
            draw.rectangle([0, cy - pad, W, cy + total_h + pad], fill=(0, 0, 0, 185))
            draw.rectangle([0, cy - pad, 8, cy + total_h + pad], fill=(255, 215, 0))
            for line in cap_lines:
                centre_shadow(draw, line, font_cap, cy, fill=(255, 255, 255))
                cy += lh

        # ── FOOTER ───────────────────────────────────────────────────────────
        ft = H - 165
        draw.rectangle([0, ft, W, H],    fill=(175, 8, 8))
        draw.rectangle([0, ft, W, ft+4], fill=(255, 215, 0))
        centre_shadow(draw, AD_LINE1, font_ad,  ft + 20, fill=(255, 255, 255))
        centre_shadow(draw, AD_LINE2, font_ad2, ft + 90, fill=(255, 230,   0))

        return np.array(img)
    except Exception as e:
        print(f"  [graphics] {e}")
        return bg_frame.astype(np.uint8)


# ===========================================================================
# extract_spoken
# ===========================================================================
_SECTION_MARKERS = {"HOOK", "STORY", "CTA", "TRUTH", "INTRO", "BODY", "OUTRO"}
_SKIP_MARKERS    = {"HASHTAGS", "CAPTION", "FORMAT", "RULES", "TAGS", "NOTE", "NOTES"}

def extract_spoken(script_text: str) -> str:
    spoken = []
    skip   = False
    for raw_line in script_text.split("\n"):
        line = raw_line.strip()
        if not line: continue
        if set(line).issubset(set("-=_*# \t")): continue
        if line.startswith("#"): continue
        if line.startswith("[") and line.endswith("]"): continue
        upper = line.upper()
        if any(kw in upper for kw in _SKIP_MARKERS): skip = True; continue
        bare  = line.rstrip(":").strip().upper()
        if bare in _SECTION_MARKERS: skip = False; continue
        ci = line.find(":")
        if ci > 0:
            prefix = line[:ci].strip().upper()
            if prefix in _SECTION_MARKERS:
                skip = False
                rem  = line[ci + 1:].strip()
                if rem: spoken.append(rem)
                continue
        if skip: continue
        if line.isupper() and len(line.split()) <= 4: continue
        spoken.append(line)
    return " ".join(spoken).strip()


# ===========================================================================
# Gradient fallback
# ===========================================================================
def gradient_frame(t):
    p  = int(8 * np.sin(t * 0.7))
    a  = np.zeros((H, W, 3), dtype=np.uint8)
    ys = np.arange(H, dtype=np.float32) / H
    a[:, :, 0] = np.clip(10 + (ys*20).astype(int) + p,     0, 255)[:, None]
    a[:, :, 1] = np.clip(10 + (ys*15).astype(int),          0, 255)[:, None]
    a[:, :, 2] = np.clip(50 + (ys*80).astype(int) + p * 2,  0, 255)[:, None]
    return a


# ===========================================================================
# Helpers
# ===========================================================================
def split_segs(text, n):
    words = text.split()
    if not words: return [""] * n
    chunk = max(1, len(words) // n)
    segs  = []
    for i in range(n):
        s = i * chunk
        e = s + chunk if i < n - 1 else len(words)
        segs.append(" ".join(words[s:e]))
    return segs

def topic_keywords(topic):
    words = [w for w in topic.split() if all(ord(c) < 128 for c in w) and len(w) > 2]
    return " ".join(words[:4]) if words else "news breaking india city"

def load_existing_manifest(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f).get("videos", [])
        except Exception:
            pass
    return []

def save_manifest(path, videos):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"videos": videos,
                   "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                   "count": len(videos)},
                  f, ensure_ascii=False, indent=2)


# ===========================================================================
# Main video builder
# ===========================================================================
def create_news_video(audio_path, spoken_text, topic, output_path,
                      anchor_face=None, bg_video_path=None, bg_photo_path=None,
                      article_image_url=""):

    audio    = AudioFileClip(audio_path)
    duration = audio.duration
    print(f"  Audio: {duration:.1f}s")

    if duration < 3.0:
        print(f"  ERROR: Audio too short ({duration:.1f}s) -- skipping")
        audio.close()
        return False

    num_segs = max(1, int(duration / 4))
    segments = split_segs(spoken_text or topic, num_segs)
    seg_dur  = duration / num_segs

    font_ch    = load_font(52)
    font_topic = load_font(44)
    font_cap   = load_font(56, tamil=True)
    font_ad    = load_font(52)
    font_ad2   = load_font(38)

    # A. Fetch article thumbnail
    thumb_cache = output_path.replace('.mp4', '_thumb.jpg')
    article_thumb = fetch_article_thumbnail(article_image_url, thumb_cache)

    # SadTalker -> Wav2Lip pipeline
    st_out_dir = output_path.replace('.mp4', '_sadtalker')
    st_video   = run_sadtalker(anchor_face, audio_path, st_out_dir)
    wl_path    = output_path.replace('.mp4', '_wl.mp4')
    wl_input   = st_video if st_video else anchor_face
    wl_success = run_wav2lip(wl_input, audio_path, wl_path)
    wl_clip    = None

    if wl_success:
        try:
            raw   = VideoFileClip(wl_path)
            if raw.duration < duration:
                loops = int(duration / raw.duration) + 2
                raw   = concatenate_videoclips([raw] * loops)
            raw   = raw.subclip(0, duration)
            scale = max(H / raw.h, W / raw.w)
            nw, nh = int(raw.w * scale), int(raw.h * scale)
            raw   = raw.resize((nw, nh))
            if nw > W: raw = raw.crop(x_center=nw/2, width=W)
            if nh > H: raw = raw.crop(y_center=nh/2, height=H)
            wl_clip = raw
        except Exception as e:
            print(f"  [Wav2Lip clip] {e}")

    bg_clip = bg_photo = None
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
            except Exception as e: print(f"  [BG video] {e}")
        if bg_clip is None and bg_photo_path and os.path.exists(bg_photo_path):
            try:
                bg_photo = np.array(
                    Image.open(bg_photo_path).convert("RGB").resize((W, H), Image.LANCZOS))
            except Exception as e: print(f"  [BG photo] {e}")
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
            print(f"  make_frame t={t:.1f}: {e}")
            frame = gradient_frame(t); is_wl = False

        seg_idx = min(int(t / seg_dur), num_segs - 1)
        return draw_news_graphics(
            frame, topic, segments[seg_idx],
            font_ch, font_topic, font_cap, font_ad, font_ad2,
            article_thumb=article_thumb,
            is_wav2lip=is_wl
        )

    clip  = VideoClip(make_frame, duration=duration)
    final = clip.set_audio(audio)
    print(f"  Writing -> {output_path}")
    final.write_videofile(output_path, fps=FPS, codec="libx264",
                          audio_codec="aac", logger="bar",
                          threads=2, preset="ultrafast")
    audio.close(); final.close()
    if wl_clip: wl_clip.close()
    if bg_clip: bg_clip.close()
    if os.path.exists(wl_path): os.remove(wl_path)
    if st_video and os.path.exists(st_video): os.remove(st_video)

    if os.path.exists(output_path):
        print(f"  Done: {os.path.getsize(output_path)/1e6:.1f} MB")
        return True
    print("  ERROR: output not created!")
    return False


# ===========================================================================
# Entry point
# ===========================================================================
def main():
    st_ok = os.path.exists(SADTALKER_SCRIPT)
    wl_ok = os.path.exists(WAV2LIP_CHECKPOINT)

    print("Tamil News Video Creator v9")
    print(f"Time            : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"SadTalker       : {'INSTALLED' if st_ok else 'NOT FOUND'}")
    print(f"Wav2Lip         : {'INSTALLED' if wl_ok else 'NOT FOUND'}")
    print(f"ANCHOR SRC      : {'user PNG' if os.path.exists(SUPPLIED_ANCHOR_PNG) else 'missing!'}")

    if not st_ok:
        print("\n  SadTalker not found. Install for body motion:")
        print("  git clone https://github.com/OpenTalker/SadTalker /tmp/SadTalker")
        print("  cd /tmp/SadTalker && pip install -r requirements.txt")
        print("  bash scripts/download_models.sh\n")

    os.makedirs(VIDEO_DIR,  exist_ok=True)
    os.makedirs(ASSETS_DIR, exist_ok=True)

    try:
        with open(SCRIPTS_FILE, "r", encoding="utf-8") as f:
            scripts_data = json.load(f)["scripts"]
    except FileNotFoundError:
        print("ERROR: scripts.json not found -- run 2_generate_script.py first!")
        sys.exit(1)

    try:
        with open(os.path.join(AUDIO_DIR, "manifest.json"), "r") as f:
            audio_files = json.load(f)["audio_files"]
    except FileNotFoundError:
        print("ERROR: audio manifest not found -- run 3_generate_voice.py first!")
        sys.exit(1)

    if not scripts_data:
        print("ERROR: scripts.json is empty -- run 2_generate_script.py first!")
        sys.exit(1)
    if not audio_files:
        print("ERROR: no audio files found -- run 3_generate_voice.py first!")
        sys.exit(1)

    print(f"\nScripts: {len(scripts_data)}  Audio: {len(audio_files)}")
    print("\n--- Preparing anchor face ---")
    anchor_face = prepare_anchor_face(ASSETS_DIR)

    manifest_path   = os.path.join(VIDEO_DIR, "manifest.json")
    existing_videos = load_existing_manifest(manifest_path)
    existing_paths  = {v["video_file"] for v in existing_videos}
    created_videos  = list(existing_videos)

    for i, (script_data, audio_data) in enumerate(zip(scripts_data, audio_files), 1):
        topic = script_data.get("topic", f"News {i}")
        print(f"\n{'='*60}")
        print(f"Video {i}/{len(scripts_data)}: {topic[:60]}")
        print(f"{'='*60}")

        audio_path = audio_data.get("audio_file", "")
        if not os.path.exists(audio_path):
            print(f"  SKIP: audio not found: {audio_path}"); continue

        spoken_text       = extract_spoken(script_data.get("script", "")) or topic
        article_image_url = script_data.get("article_image_url", "")
        keywords          = topic_keywords(topic)
        timestamp         = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path       = os.path.join(VIDEO_DIR, f"reel_{i}_{timestamp}.mp4")

        if output_path in existing_paths:
            print("  SKIP: already in manifest"); continue

        # Background assets (only when AI models unavailable)
        final_vid = final_photo = None
        if not st_ok and not wl_ok:
            bg_vid_path    = os.path.join(ASSETS_DIR, f"bg_video_{i}.mp4")
            bg_photo_path  = os.path.join(ASSETS_DIR, f"bg_photo_{i}.jpg")
            pix_vid_path   = os.path.join(ASSETS_DIR, f"pbay_video_{i}.mp4")
            pix_photo_path = os.path.join(ASSETS_DIR, f"pbay_photo_{i}.jpg")
            if download_pexels_video(keywords, bg_vid_path):
                final_vid = bg_vid_path
            elif download_pixabay_video(keywords, pix_vid_path):
                final_vid = pix_vid_path
            elif download_pexels_photo(keywords, bg_photo_path):
                final_photo = bg_photo_path
            elif download_pixabay_photo(keywords, pix_photo_path):
                final_photo = pix_photo_path
            else:
                print("  Using gradient background")

        try:
            success = create_news_video(
                audio_path, spoken_text, topic, output_path,
                anchor_face       = anchor_face,
                bg_video_path     = final_vid,
                bg_photo_path     = final_photo,
                article_image_url = article_image_url,
            )
            if success and os.path.exists(output_path):
                sz = os.path.getsize(output_path) / 1e6
                created_videos.append({
                    "topic":      topic,
                    "video_file": output_path,
                    "size_mb":    round(sz, 1),
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                })
                save_manifest(manifest_path, created_videos)
                print(f"  DONE: {sz:.1f} MB")
            else:
                print(f"  FAILED: {topic}")
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            import traceback; traceback.print_exc()

    print(f"\n{'='*60}")
    new_count = len(created_videos) - len(existing_videos)
    print(f"DONE: {new_count} new | {len(created_videos)} total -> {VIDEO_DIR}")
    if new_count == 0 and not existing_videos:
        print("ZERO videos -- check logs above")
        sys.exit(1)


if __name__ == "__main__":
    main()
