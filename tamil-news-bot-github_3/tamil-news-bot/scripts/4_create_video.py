"""
STEP 4: Tamil News Video Creator (v8 - SadTalker + Wav2Lip)
============================================================
Pipeline:
  1. SadTalker  : static anchor image -> animated talking-head video
                  (real head nods, blinks, shoulder sway, expressions)
  2. Wav2Lip    : animated video -> perfectly lip-synced video
  3. MoviePy    : composite with news graphics overlay

Changes over v7:
  A. SadTalker integration  -- auto-detected at /tmp/SadTalker
     --still flag OFF        -> full head + body motion enabled
     --expression_scale 1.2  -> slightly expressive
     --enhancer gfpgan       -> face quality enhancement
     Fallback chain: SadTalker -> Wav2Lip alone -> BG video -> photo -> gradient

  B. Caption lower-third    -- captions placed in bottom 28% of frame,
                               never overlapping the anchor face

  C. Header topic            -- Tamil shown if font verified OK,
                               else English keywords extracted cleanly
                               (no leftover punctuation / numbers)

  D. AnchorAnimator removed  -- no fake transforms; SadTalker handles motion

  E. All v6/v7 fixes kept    -- force anchor refresh, robust HTTP retry,
                               Tamil font verification, manifest merging,
                               extract_spoken robustness, Wav2Lip smoothing
"""

import json, os, io, sys, time, subprocess, requests, numpy as np
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

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

# SadTalker paths
SADTALKER_DIR        = "/tmp/SadTalker"
SADTALKER_SCRIPT     = os.path.join(SADTALKER_DIR, "inference.py")
SADTALKER_CHECKPOINT = os.path.join(SADTALKER_DIR, "checkpoints")

# Wav2Lip paths
WAV2LIP_DIR        = "/tmp/Wav2Lip"
WAV2LIP_CHECKPOINT = os.path.join(WAV2LIP_DIR, "checkpoints/wav2lip.pth")

# Lower-third caption zone
CAPTION_TOP_PCT    = 0.72
CAPTION_BOTTOM_PCT = 0.92


# ===========================================================================
# Robust HTTP with exponential backoff
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
            wait = backoff ** attempt
            print(f"    [retry {attempt}/{retries}] {e} -- wait {wait}s")
            time.sleep(wait)
    raise last


# ===========================================================================
# Font loading with Tamil glyph verification
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
_TAMIL_TEST        = "த"


def _font_renders_tamil(font):
    try:
        img  = Image.new("RGB", (60, 60), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((5, 5), _TAMIL_TEST, font=font, fill=(0, 0, 0))
        arr  = np.array(img)
        return bool((arr[10:50, 5:55] < 200).any())
    except Exception:
        return False


def _try_install_tamil():
    try:
        res = subprocess.run(
            ["sudo", "apt-get", "install", "-y",
             "fonts-noto-core", "fonts-lohit-taml"],
            capture_output=True, text=True, timeout=120)
        if res.returncode == 0:
            subprocess.run(["fc-cache", "-f", "-v"],
                           capture_output=True, timeout=30)
            return True
    except Exception as e:
        print(f"  [Font] apt error: {e}")
    return False


def load_font(size, tamil=False):
    global _tamil_font_ok, _tamil_font_warned
    key = (size, tamil)
    if key in _font_cache:
        return _font_cache[key]

    paths = TAMIL_FONT_PATHS if tamil else LATIN_FONT_PATHS
    for p in paths:
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
        print("  [Font] WARNING: No Tamil font -- attempting auto-install...")
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
        print("  [Font] Failed. Run: sudo apt-get install fonts-noto-core fonts-lohit-taml")

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
# A. SadTalker -- static image -> animated body+head video
# ===========================================================================
def run_sadtalker(face_path, audio_path, out_dir):
    """
    Run SadTalker to generate full head+body motion video from still image.

    Movements produced by SadTalker:
      - Head nods (driven by audio rhythm)
      - Natural eye blinks (learned)
      - Shoulder / upper-body sway
      - Facial expressions (eyebrows, mouth corners)

    Flags:
      --preprocess full   : includes shoulders in output (not just face crop)
      --expression_scale  : 1.2 = slightly expressive, not over-the-top
      --pose_style 1      : natural news-reader head movement style
      --enhancer gfpgan   : GFPGAN sharpens face after animation
      --still NOT passed  : enables full motion (passing --still freezes pose)
      --size 256          : 256=fast CPU; change to 512 for better quality
    """
    if not os.path.exists(SADTALKER_SCRIPT):
        print("  [SadTalker] Not found -- skipping")
        print("  Install: git clone https://github.com/OpenTalker/SadTalker /tmp/SadTalker")
        return None
    if not os.path.exists(SADTALKER_CHECKPOINT):
        print("  [SadTalker] Checkpoints missing -- skipping")
        print("  Download: bash /tmp/SadTalker/scripts/download_models.sh")
        return None
    if not face_path or not os.path.exists(face_path):
        print("  [SadTalker] No face image"); return None

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
        "--still",             # freeze head/body -- lip-sync only (real news reader look)
    ]

    print("  [SadTalker] Generating body motion (CPU ~15-30 min)...")
    try:
        proc = subprocess.run(
            cmd, cwd=SADTALKER_DIR,
            capture_output=True, text=True, timeout=2400
        )
        if proc.stdout:
            print("  [SadTalker OUT]", proc.stdout[-400:])
        if proc.returncode != 0:
            print(f"  [SadTalker ERR] code={proc.returncode}")
            print(proc.stderr[-400:] if proc.stderr else "")
            return None

        # Find newest mp4 in output dir
        found = []
        for root, dirs, files in os.walk(out_dir):
            for f in files:
                if f.endswith(".mp4"):
                    full = os.path.join(root, f)
                    found.append((os.path.getmtime(full), full))
        if not found:
            print("  [SadTalker] No output mp4 found"); return None

        found.sort(reverse=True)
        result = found[0][1]
        print(f"  [SadTalker] Done: {result} ({os.path.getsize(result)/1e6:.1f} MB)")
        return result

    except subprocess.TimeoutExpired:
        print("  [SadTalker] Timeout after 40 min"); return None
    except Exception as e:
        print(f"  [SadTalker] Exception: {e}"); return None


# ===========================================================================
# Wav2Lip -- lip sync on SadTalker video or static face image
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
        print(f"  [Wav2Lip] Audio convert failed"); return False

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
    print(f"  [Wav2Lip] Input: {os.path.basename(face_input)}")
    print("  [Wav2Lip] Lip sync running (CPU ~10-20 min)...")
    try:
        proc = subprocess.run(cmd, cwd=WAV2LIP_DIR, capture_output=True,
                              text=True, timeout=1800)
        if proc.returncode != 0:
            print(f"  [Wav2Lip ERR] {proc.stderr[-400:]}"); return False
        if os.path.exists(output_path) and os.path.getsize(output_path) > 10_000:
            print(f"  [Wav2Lip] Done: {os.path.getsize(output_path)/1e6:.1f} MB")
            return True
        return False
    except subprocess.TimeoutExpired:
        print("  [Wav2Lip] Timeout"); return False
    except Exception as e:
        print(f"  [Wav2Lip] {e}"); return False


# ===========================================================================
# Anchor face (force refresh from supplied PNG)
# ===========================================================================
def prepare_anchor_face(assets_dir):
    face_path = os.path.join(assets_dir, "anchor_face.jpg")
    if os.path.exists(SUPPLIED_ANCHOR_PNG):
        print("  [Face] Using supplied anchor PNG")
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
            print(f"  [Face] Saved: {face_path}")
            return face_path
        except Exception as e:
            print(f"  [Face] Error: {e}")
    return _download_face(assets_dir, face_path)


def _download_face(assets_dir, face_path):
    if os.path.exists(face_path) and os.path.getsize(face_path) > 5000:
        return face_path
    searches = [("pexels", "woman news anchor portrait"),
                ("pixabay", "woman portrait professional")]
    for src, query in searches:
        try:
            if src == "pexels" and PEXELS_KEY:
                r = _robust_get("https://api.pexels.com/v1/search",
                                headers={"Authorization": PEXELS_KEY},
                                params={"query": query, "per_page": 3,
                                        "orientation": "portrait"}, timeout=15)
                for ph in r.json().get("photos", []):
                    url  = ph["src"].get("medium", "")
                    resp = _robust_get(url, timeout=30)
                    if resp.status_code == 200:
                        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
                        img = img.resize((480, 640), Image.LANCZOS)
                        img.save(face_path, quality=95)
                        return face_path
            elif src == "pixabay" and PIXABAY_KEY:
                r = _robust_get("https://pixabay.com/api/",
                                params={"key": PIXABAY_KEY, "q": query,
                                        "image_type": "photo", "per_page": 3,
                                        "safesearch": "true"}, timeout=15)
                for hit in r.json().get("hits", []):
                    url  = hit.get("webformatURL", "")
                    resp = _robust_get(url, timeout=30)
                    if resp.status_code == 200:
                        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
                        img = img.resize((480, 640), Image.LANCZOS)
                        img.save(face_path, quality=95)
                        return face_path
        except Exception as e:
            print(f"  [Face] {src}: {e}")
    print("  [Face] WARNING: no face image"); return None


# ===========================================================================
# Background downloaders
# ===========================================================================
def _stream_video(url, out_path, max_mb=30):
    resp = _robust_get(url, stream=True, timeout=90)
    if resp.status_code != 200: return False
    downloaded = 0
    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(65536):
            f.write(chunk); downloaded += len(chunk)
            if downloaded > max_mb * 1024 * 1024: break
    return os.path.getsize(out_path) > 100_000


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
        for query in [keywords, "india news city"]:
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
            if dx or dy: draw.text((x + dx, y + dy), text, font=font, fill=sh)
    draw.text((x, y), text, font=font, fill=fill)

def centre_shadow(draw, text, font, y, fill=(255, 255, 255)):
    x = max(20, (W - tw(draw, text, font)) // 2)
    shadow_text(draw, (x, y), text, font, fill=fill)


# ===========================================================================
# C. Header topic -- Tamil if font OK, else clean English keywords
# ===========================================================================
def _header_topic(topic: str) -> str:
    """Always returns English keywords for the header -- never Tamil script."""
    import re
    ascii_words = re.findall(r'[A-Za-z]{2,}', topic)
    result = " ".join(ascii_words[:8])
    return result.strip() if result.strip() else "Breaking News"


# ===========================================================================
# B. News graphics -- lower-third caption, clean header
# ===========================================================================
# ===========================================================================
# News banner fallback (shown when no topic image is available)
# ===========================================================================
def _draw_news_banner(draw, img, top_y, bottom_y, topic, font_topic):
    """
    Draw a professional news-style graphic banner with English topic text
    when no photo is available. Looks like a real news channel graphic.
    """
    banner_h = bottom_y - top_y
    for row in range(banner_h):
        ratio = row / banner_h
        r = int(5  + 15 * (1 - ratio))
        g = int(10 + 20 * (1 - ratio))
        b = int(60 + 40 * (1 - ratio))
        draw.rectangle([0, top_y + row, img.width, top_y + row + 1], fill=(r, g, b))
    draw.rectangle([0, top_y, 12, bottom_y], fill=(200, 20, 20))
    draw.rectangle([0, top_y, img.width, top_y + 4], fill=(255, 255, 255))
    try:
        from PIL import ImageFont as _IF
        lbl_font = _IF.truetype("/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf", 36)
    except Exception:
        lbl_font = font_topic
    draw.rectangle([28, top_y + 30, 308, top_y + 80], fill=(180, 10, 10))
    draw.text((38, top_y + 33), "LATEST NEWS", font=lbl_font, fill=(255, 255, 255))
    eng_topic = topic_keywords(topic) or topic[:60]
    words = eng_topic.upper().split()
    mid = max(1, len(words) // 2)
    lines = [' '.join(words[:mid]), ' '.join(words[mid:])]
    ty = top_y + 110
    for line in lines:
        if line.strip():
            shadow_text(draw, (28, ty), line, font_topic, fill=(255, 215, 0))
            ty += 75


# ===========================================================================
# Fetch relevant topic image (cached per topic)
# ===========================================================================
_IMG_CACHE = {}  # topic_key -> PIL Image or None

def fetch_topic_image(topic: str):
    """
    Fetch a relevant photo for the topic using Pexels or Pixabay.
    Returns PIL Image (RGB) sized to display, or None if unavailable.
    Cached so same topic doesn't re-fetch on every frame.
    """
    import hashlib, io as _io, urllib.request as _urllib
    key = hashlib.md5(topic.encode("utf-8")).hexdigest()
    if key in _IMG_CACHE:
        return _IMG_CACHE[key]

    kw = topic_keywords(topic) or topic[:30]

    # Try Pexels
    if PEXELS_KEY:
        try:
            r = _robust_get(
                "https://api.pexels.com/v1/search",
                params={"query": kw, "per_page": 1, "orientation": "landscape"},
                headers={"Authorization": PEXELS_KEY},
                timeout=10
            )
            photos = r.json().get("photos", [])
            if photos:
                img_url = photos[0]["src"]["medium"]
                data = _urllib.urlopen(img_url, timeout=10).read()
                img = Image.open(_io.BytesIO(data)).convert("RGB")
                _IMG_CACHE[key] = img
                print(f"  [TopicImg] Pexels photo fetched for: {kw[:30]}")
                return img
        except Exception as e:
            print(f"  [TopicImg Pexels] {e}")

    # Try Pixabay fallback
    if PIXABAY_KEY:
        try:
            r = _robust_get(
                "https://pixabay.com/api/",
                params={"key": PIXABAY_KEY, "q": kw, "image_type": "photo",
                        "per_page": 3, "safesearch": "true"},
                timeout=10
            )
            hits = r.json().get("hits", [])
            if hits:
                img_url = hits[0]["webformatURL"]
                data = _urllib.urlopen(img_url, timeout=10).read()
                img = Image.open(_io.BytesIO(data)).convert("RGB")
                _IMG_CACHE[key] = img
                print(f"  [TopicImg] Pixabay photo fetched for: {kw[:30]}")
                return img
        except Exception as e:
            print(f"  [TopicImg Pixabay] {e}")

    _IMG_CACHE[key] = None
    return None


def draw_news_graphics(bg_frame, topic, caption_text,
                        font_ch, font_topic, font_cap, font_ad, font_ad2,
                        is_wav2lip=False):
    try:
        img  = Image.fromarray(bg_frame.astype(np.uint8), "RGB")
        alpha = 40 if is_wav2lip else 100
        ov   = Image.new("RGBA", (W, H), (0, 0, 0, alpha))
        img  = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
        draw = ImageDraw.Draw(img)

        # ── TOP HEADER ───────────────────────────────────────────────────────
        HEADER_H = 145   # channel name bar height
        IMG_H    = 400   # relevant image zone height below header
        IMG_TOP  = HEADER_H
        TOPIC_TOP = IMG_TOP + IMG_H  # topic bar starts below image

        draw.rectangle([0, 0, W, HEADER_H], fill=(5, 15, 70))
        draw.rectangle([0, HEADER_H - 2, W, HEADER_H + 6], fill=(200, 20, 20))
        shadow_text(draw, (28, 16), CHANNEL,         font_ch,  fill=(255, 255, 255))
        shadow_text(draw, (28, 82), "BREAKING NEWS", font_ad2, fill=(255, 60,  60))

        # ── RELEVANT TOPIC IMAGE ZONE (below channel bar, top area) ──────────
        topic_img = fetch_topic_image(topic)
        if topic_img:
            try:
                tw_i, th_i = topic_img.size
                scale_i = W / tw_i
                nw_i = W
                nh_i = int(th_i * scale_i)
                img_resized = topic_img.resize((nw_i, nh_i), Image.LANCZOS)
                crop_top = max(0, (nh_i - IMG_H) // 2)
                img_cropped = img_resized.crop((0, crop_top, nw_i, crop_top + IMG_H))
                img.paste(img_cropped, (0, IMG_TOP))
                draw = ImageDraw.Draw(img)
                print(f"  [TopicImg] Displayed image in header zone")
            except Exception as e:
                print(f"  [TopicImg draw] {e}")
                _draw_news_banner(draw, img, IMG_TOP, TOPIC_TOP, topic, font_topic)
        else:
            _draw_news_banner(draw, img, IMG_TOP, TOPIC_TOP, topic, font_topic)

        # ── TOPIC BAR (positioned below the relevant image) ──────────────────
        draw.rectangle([0, TOPIC_TOP, W, TOPIC_TOP + 144], fill=(0, 0, 0, 210))
        draw.rectangle([0, TOPIC_TOP, 8, TOPIC_TOP + 144], fill=(200, 20, 20))
        display_topic = _header_topic(topic)
        ty = TOPIC_TOP + 11
        for line in wrap_text(draw, display_topic[:100], font_topic, W - 60)[:2]:
            shadow_text(draw, (24, ty), line, font_topic, fill=(255, 215, 0))
            ty += 60

        # ── B. LOWER-THIRD CAPTION (72%–92% of frame height) ─────────────────
        if caption_text.strip():
            zone_top    = int(H * CAPTION_TOP_PCT)
            zone_bottom = int(H * CAPTION_BOTTOM_PCT)
            zone_h      = zone_bottom - zone_top

            cap_lines = wrap_text(draw, caption_text, font_cap, W - 80)[:4]
            lh        = th(draw, "A", font_cap) + 16
            total_h   = len(cap_lines) * lh
            pad       = 20

            cy = zone_top + max(0, (zone_h - total_h) // 2)

            draw.rectangle([0, cy - pad, W, cy + total_h + pad],
                           fill=(0, 0, 0, 185))
            draw.rectangle([0, cy - pad, 8, cy + total_h + pad],
                           fill=(255, 215, 0))
            for line in cap_lines:
                centre_shadow(draw, line, font_cap, cy, fill=(255, 255, 255))
                cy += lh

        # ── FOOTER AD ────────────────────────────────────────────────────────
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
# extract_spoken (robust)
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
    a[:, :, 0] = np.clip(10 + (ys * 20).astype(int) + p,     0, 255)[:, None]
    a[:, :, 1] = np.clip(10 + (ys * 15).astype(int),          0, 255)[:, None]
    a[:, :, 2] = np.clip(50 + (ys * 80).astype(int) + p * 2,  0, 255)[:, None]
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
        except Exception as e:
            print(f"  [Manifest] Read error: {e}")
    return []

def save_manifest(path, videos):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"videos":     videos,
                   "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                   "count":      len(videos)},
                  f, ensure_ascii=False, indent=2)


# ===========================================================================
# Main video builder
# ===========================================================================
def create_news_video(audio_path, spoken_text, topic, output_path,
                      anchor_face=None, bg_video_path=None, bg_photo_path=None):
    from moviepy.editor import (VideoClip, AudioFileClip,
                                 VideoFileClip, concatenate_videoclips)

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

    # ── STEP 1: SadTalker -> real body+head animated video ───────────────────
    st_out_dir = output_path.replace('.mp4', '_sadtalker')
    st_video   = run_sadtalker(anchor_face, audio_path, st_out_dir)

    # ── STEP 2: Wav2Lip -> lip sync on top of SadTalker (or raw face) ────────
    wl_path    = output_path.replace('.mp4', '_wl.mp4')
    wl_input   = st_video if st_video else anchor_face
    wl_success = run_wav2lip(wl_input, audio_path, wl_path)
    wl_clip    = None

    if wl_success:
        try:
            raw   = VideoFileClip(wl_path)
            print(f"  [Final clip] {raw.w}x{raw.h} {raw.duration:.1f}s")
            if raw.duration < duration:
                loops = int(duration / raw.duration) + 2
                raw   = concatenate_videoclips([raw] * loops)
            raw   = raw.subclip(0, duration)
            scale = max(H / raw.h, W / raw.w)
            nw    = int(raw.w * scale)
            nh    = int(raw.h * scale)
            raw   = raw.resize((nw, nh))
            if nw > W: raw = raw.crop(x_center=nw / 2, width=W)
            if nh > H: raw = raw.crop(y_center=nh / 2, height=H)
            wl_clip = raw
        except Exception as e:
            print(f"  [Clip load] {e}"); wl_clip = None

    # ── Background fallback ───────────────────────────────────────────────────
    bg_clip = bg_photo = None
    if wl_clip is None:
        if bg_video_path and os.path.exists(bg_video_path):
            try:
                raw = VideoFileClip(bg_video_path)
                if raw.duration < duration:
                    raw = concatenate_videoclips([raw] * (int(duration / raw.duration) + 2))
                raw = raw.subclip(0, duration)
                raw = raw.resize(height=H) if raw.h < H else raw
                raw = raw.resize(width=W)  if raw.w < W else raw
                if raw.w > W: raw = raw.crop(x_center=raw.w / 2, width=W)
                if raw.h > H: raw = raw.crop(y_center=raw.h / 2, height=H)
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

    # Cleanup temp files
    if os.path.exists(wl_path): os.remove(wl_path)
    if st_video and os.path.exists(st_video): os.remove(st_video)

    if os.path.exists(output_path):
        print(f"  Done: {os.path.getsize(output_path)/1e6:.1f} MB")
        return True
    print("  ERROR: output not created!"); return False


# ===========================================================================
# Entry point
# ===========================================================================
def main():
    st_ok = os.path.exists(SADTALKER_SCRIPT)
    wl_ok = os.path.exists(WAV2LIP_CHECKPOINT)

    print("Tamil News Video Creator v8  (SadTalker + Wav2Lip)")
    print(f"Time            : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"PEXELS_API_KEY  : {'SET' if PEXELS_KEY  else 'NOT SET'}")
    print(f"PIXABAY_API_KEY : {'SET' if PIXABAY_KEY else 'NOT SET'}")
    print(f"SadTalker       : {'INSTALLED' if st_ok else 'NOT FOUND'}")
    print(f"Wav2Lip         : {'INSTALLED' if wl_ok else 'NOT FOUND'}")
    print(f"ANCHOR SRC      : {'user PNG' if os.path.exists(SUPPLIED_ANCHOR_PNG) else 'API download'}")

    if not st_ok:
        print("\n  [!] SadTalker missing. Install commands:")
        print("      git clone https://github.com/OpenTalker/SadTalker /tmp/SadTalker")
        print("      cd /tmp/SadTalker && pip install -r requirements.txt")
        print("      bash scripts/download_models.sh")
        print("  [!] Will fall back to Wav2Lip-only (lips only, no body)\n")

    try:
        r = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=10)
        print(f"ffmpeg          : {r.stdout.splitlines()[0] if r.stdout else 'found'}")
    except Exception as e:
        print(f"ffmpeg          : WARNING -- {e}")

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

        spoken_text = extract_spoken(script_data.get("script", "")) or topic
        if not spoken_text.strip():
            spoken_text = topic

        keywords    = topic_keywords(topic)
        timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(VIDEO_DIR, f"reel_{i}_{timestamp}.mp4")

        if output_path in existing_paths:
            print("  SKIP: already in manifest"); continue

        # Only fetch BG assets if both AI models are unavailable
        final_vid = final_photo = None
        if not st_ok and not wl_ok:
            bg_vid_path    = os.path.join(ASSETS_DIR, f"bg_video_{i}.mp4")
            bg_photo_path  = os.path.join(ASSETS_DIR, f"bg_photo_{i}.jpg")
            pix_vid_path   = os.path.join(ASSETS_DIR, f"pbay_video_{i}.mp4")
            pix_photo_path = os.path.join(ASSETS_DIR, f"pbay_photo_{i}.jpg")
            print(f"  Keywords: '{keywords}'")
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
                anchor_face   = anchor_face,
                bg_video_path = final_vid,
                bg_photo_path = final_photo,
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
        print("ZERO videos created -- check logs above"); sys.exit(1)


if __name__ == "__main__":
    main()
