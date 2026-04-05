"""
STEP 4: Tamil News Video Creator (v9 - SadTalker + Wav2Lip + HeadAnimator)
============================================================
Fixes in v9:
  A. Per-video SadTalker timeout (1080s) so video 3 never starves
  B. Synthetic HeadAnimator for natural news-reader motion fallback
  C. RSS article image URLs shown on blue screen zone
  D. topic_keywords uses English description for Tamil titles
  E. fetch_topic_image tries article thumbnail URL first
  F. Category-colored topic background fallback
"""

import json, os, io, sys, time, subprocess, requests, numpy as np, math, random
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
SADTALKER_TIMEOUT    = 1080   # 18 min per video - ensures all 3 videos get processed

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
    for attempt in range(retries):
        try:
            r = requests.get(url, **kwargs)
            if r.status_code == 200:
                return r
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(backoff ** attempt)
    return r


# ===========================================================================
# Font loading with Tamil glyph verification
# ===========================================================================
def _font_renders_tamil(font):
    try:
        img = Image.new("RGB", (100, 100))
        d   = ImageDraw.Draw(img)
        d.text((0, 0), "\u0ba4\u0bae\u0bbf\u0bb4\u0bcd", font=font)
        arr = np.array(img)
        return arr.max() > 30
    except Exception:
        return False

def _try_install_tamil():
    try:
        subprocess.run(
            ["apt-get", "install", "-y", "-q", "fonts-noto-color-emoji",
             "fonts-noto-cjk", "fonts-lohit-taml"],
            capture_output=True, timeout=90
        )
        subprocess.run(["fc-cache", "-f", "-v"], capture_output=True, timeout=30)
    except Exception as e:
        print(f"  [Font install] {e}")

def load_font(size, tamil=False):
    tamil_fonts = [
        "/usr/share/fonts/truetype/noto/NotoSansTamil-Regular.ttf",
        "/usr/share/fonts/truetype/lohit-tamil/Lohit-Tamil.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    fallback_fonts = [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    search = tamil_fonts if tamil else fallback_fonts
    for path in search:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
                if tamil and not _font_renders_tamil(font):
                    continue
                return font
            except Exception:
                continue
    if tamil:
        _try_install_tamil()
        for path in tamil_fonts:
            if os.path.exists(path):
                try:
                    font = ImageFont.truetype(path, size)
                    if _font_renders_tamil(font):
                        return font
                except Exception:
                    continue
    return ImageFont.load_default()


# ===========================================================================
# A. SadTalker - real body+head animated video
# ===========================================================================
def run_sadtalker(face_path, audio_path, out_dir):
    """
    Run SadTalker: real head nods, eye blinks, shoulder sway, facial expressions.
    v9: Per-video timeout = SADTALKER_TIMEOUT (18 min) so all 3 videos complete.
    """
    if not os.path.exists(SADTALKER_SCRIPT):
        print("  [SadTalker] Not found -- using HeadAnimator fallback")
        return None
    if not os.path.exists(SADTALKER_CHECKPOINT):
        print("  [SadTalker] Checkpoints missing -- using HeadAnimator fallback")
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
        "--expression_scale", "1.8",
        "--pose_style",       "0",
        "--preprocess",       "full",
        "--size",             "256",
    ]

    print(f"  [SadTalker] Generating (timeout={SADTALKER_TIMEOUT}s)...")
    try:
        proc = subprocess.run(
            cmd, cwd=SADTALKER_DIR,
            capture_output=True, text=True, timeout=SADTALKER_TIMEOUT
        )
        if proc.stdout:
            print("  [SadTalker OUT]", proc.stdout[-400:])
        if proc.returncode != 0:
            print(f"  [SadTalker ERR] code={proc.returncode}")
            print(proc.stderr[-400:] if proc.stderr else "")
            return None
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
        print(f"  [SadTalker] Timeout after {SADTALKER_TIMEOUT}s -- HeadAnimator will be used")
        return None
    except Exception as e:
        print(f"  [SadTalker] Exception: {e}"); return None


# ===========================================================================
# B. Wav2Lip - lip sync
# ===========================================================================
def run_wav2lip(face_input, audio_path, output_path):
    if not os.path.exists(WAV2LIP_CHECKPOINT):
        print("  [Wav2Lip] Checkpoint not found"); return False
    if not face_input or not os.path.exists(face_input):
        print("  [Wav2Lip] No face input"); return False
    cmd = [
        sys.executable,
        os.path.join(WAV2LIP_DIR, "inference.py"),
        "--checkpoint_path", WAV2LIP_CHECKPOINT,
        "--face",            face_input,
        "--audio",           audio_path,
        "--outfile",         output_path,
        "--fps",             str(FPS),
        "--pads",            "0", "10", "0", "0",
        "--resize_factor",   "1",
        "--nosmooth",
    ]
    print("  [Wav2Lip] Running lip sync...")
    try:
        proc = subprocess.run(
            cmd, cwd=WAV2LIP_DIR,
            capture_output=True, text=True, timeout=600
        )
        if proc.returncode != 0:
            print(f"  [Wav2Lip ERR] code={proc.returncode}")
            print(proc.stderr[-400:] if proc.stderr else "")
            return False
        success = os.path.exists(output_path) and os.path.getsize(output_path) > 50000
        if success:
            print(f"  [Wav2Lip] Done: {os.path.getsize(output_path)/1e6:.1f} MB")
        return success
    except subprocess.TimeoutExpired:
        print("  [Wav2Lip] Timeout"); return False
    except Exception as e:
        print(f"  [Wav2Lip] Exception: {e}"); return False


# ===========================================================================
# C. HeadAnimator - synthetic natural news-reader head/body movement
#    Fallback when SadTalker unavailable or timed out
# ===========================================================================
class HeadAnimator:
    """
    Natural head+body movement on static anchor face image.
    News-reader style: slow nods, slight sway, breathing, eye blinks.
    """

    def __init__(self, face_img_path, duration, fps=FPS):
        self.duration = duration
        self.fps      = fps
        self.img      = None
        self.arr      = None

        if face_img_path and os.path.exists(face_img_path):
            try:
                pil  = Image.open(face_img_path).convert("RGB")
                # Scale face to fill lower 55% of frame width
                scale = W / pil.width
                new_h = int(pil.height * scale)
                pil   = pil.resize((W, new_h), Image.LANCZOS)
                self.img = pil
                self.arr = np.array(pil)
                print(f"  [HeadAnimator] Face loaded: {W}x{new_h}")
            except Exception as e:
                print(f"  [HeadAnimator] Load error: {e}")

        rng = random.Random(int(duration * 100))
        self.nod_phase    = rng.uniform(0, math.pi * 2)
        self.sway_phase   = rng.uniform(0, math.pi * 2)
        self.breathe_phase= rng.uniform(0, math.pi * 2)
        self.tilt_phase   = rng.uniform(0, math.pi * 2)

        # Blink times (random, every 3-5 sec)
        self.blinks = []
        t = rng.uniform(1.5, 3.5)
        while t < duration - 0.5:
            self.blinks.append(t)
            t += rng.uniform(2.5, 5.0)

    def get_frame(self, t):
        """Return H x W x 3 numpy array for time t."""
        # Dark studio blue background
        canvas = np.zeros((H, W, 3), dtype=np.uint8)
        for y in range(0, H, 4):
            v = int(8 + 14 * y / H)
            canvas[y:y+4, :] = [v, v + 3, v + 28]

        if self.arr is None:
            return canvas

        img_h, img_w = self.arr.shape[:2]

        # Natural news-reader movements
        nod_y    = int(7  * math.sin(2 * math.pi * 0.33 * t + self.nod_phase))
        sway_x   = int(5  * math.sin(2 * math.pi * 0.17 * t + self.sway_phase))
        breathe  = 1.0 + 0.004 * math.sin(2 * math.pi * 0.23 * t + self.breathe_phase)
        tilt_x   = int(3  * math.sin(2 * math.pi * 0.11 * t + self.tilt_phase))

        blink_y = 0
        for blink_t in self.blinks:
            dt = abs(t - blink_t)
            if dt < 0.12:
                blink_y = int(4 * (1 - dt / 0.12))

        dy = nod_y + blink_y
        dx = sway_x + tilt_x

        # Apply breathing scale
        try:
            scale_h = int(img_h * breathe)
            scale_w = int(img_w * breathe)
            face_arr = np.array(Image.fromarray(self.arr).resize((scale_w, scale_h), Image.BILINEAR))
            dy_c = (scale_h - img_h) // 2
            dx_c = (scale_w - img_w) // 2
            face_arr = face_arr[dy_c:dy_c+img_h, dx_c:dx_c+img_w]
        except Exception:
            face_arr = self.arr

        # Paste face centered horizontally, upper portion of frame
        face_top  = int(H * 0.04) + dy
        face_left = (W - img_w) // 2 + dx

        src_top  = max(0, -face_top)
        src_left = max(0, -face_left)
        dst_top  = max(0, face_top)
        dst_left = max(0, face_left)
        ph = min(img_h - src_top, H - dst_top)
        pw = min(img_w - src_left, W - dst_left)

        if ph > 0 and pw > 0:
            canvas[dst_top:dst_top+ph, dst_left:dst_left+pw] = \
                face_arr[src_top:src_top+ph, src_left:src_left+pw]

        return canvas


# ===========================================================================
# Anchor face preparation
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
        for q in [keywords, "tamil news", "india news"]:
            r = _robust_get("https://api.pexels.com/videos/search",
                            headers={"Authorization": PEXELS_KEY},
                            params={"query": q, "per_page": 3,
                                    "orientation": "portrait"}, timeout=15)
            for vid in r.json().get("videos", []):
                for vf in vid.get("video_files", []):
                    if vf.get("quality") in ("sd", "hd") and vf.get("width", 0) <= 1080:
                        if _stream_video(vf["link"], out_path):
                            return True
    except Exception as e: print(f"  [Pexels video] {e}")
    return False

def download_pixabay_video(keywords, out_path):
    if not PIXABAY_KEY: return False
    try:
        for q in [keywords, "news india", "city india"]:
            r = _robust_get("https://pixabay.com/api/videos/",
                            params={"key": PIXABAY_KEY, "q": q,
                                    "video_type": "film", "per_page": 3}, timeout=15)
            for hit in r.json().get("hits", []):
                url = hit.get("videos", {}).get("medium", {}).get("url", "")
                if url and _stream_video(url, out_path):
                    return True
    except Exception as e: print(f"  [Pixabay video] {e}")
    return False

def download_pexels_photo(keywords, out_path):
    if not PEXELS_KEY: return False
    try:
        for q in [keywords, "india news", "breaking news"]:
            r = _robust_get("https://api.pexels.com/v1/search",
                            headers={"Authorization": PEXELS_KEY},
                            params={"query": q, "per_page": 3,
                                    "orientation": "landscape"}, timeout=15)
            for ph in r.json().get("photos", []):
                url  = ph["src"].get("large", "")
                resp = _robust_get(url, timeout=30)
                if resp.status_code == 200:
                    with open(out_path, "wb") as f: f.write(resp.content)
                    return True
    except Exception as e: print(f"  [Pexels photo] {e}")
    return False

def download_pixabay_photo(keywords, out_path):
    if not PIXABAY_KEY: return False
    try:
        for q in [keywords, "news", "india"]:
            r = _robust_get("https://pixabay.com/api/",
                            params={"key": PIXABAY_KEY, "q": q,
                                    "image_type": "photo", "per_page": 3,
                                    "safesearch": "true"}, timeout=15)
            for hit in r.json().get("hits", []):
                url  = hit.get("webformatURL", "")
                resp = _robust_get(url, timeout=30)
                if resp.status_code == 200:
                    with open(out_path, "wb") as f: f.write(resp.content)
                    return True
    except Exception as e: print(f"  [Pixabay photo] {e}")
    return False


# ===========================================================================
# Text drawing helpers
# ===========================================================================
def tw(draw, text, font):
    try: return draw.textlength(text, font=font)
    except: bbox = draw.textbbox((0,0), text, font=font); return bbox[2]-bbox[0]

def th(draw, text, font):
    try: bbox = draw.textbbox((0,0), text, font=font); return bbox[3]-bbox[1]
    except: return font.size

def wrap_text(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if tw(draw, test, font) <= max_w:
            cur = test
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines or [text]

def shadow_text(draw, xy, text, font, fill=(255,255,255), sh=(0,0,0), off=2):
    draw.text((xy[0]+off, xy[1]+off), text, font=font, fill=sh)
    draw.text(xy, text, font=font, fill=fill)

def centre_shadow(draw, text, font, y, fill=(255,255,255)):
    w = tw(draw, text, font)
    x = (W - w) // 2
    shadow_text(draw, (x, y), text, font, fill=fill)

def _header_topic(topic: str) -> str:
    # Extract clean English keywords for header display
    words = topic.split()
    ascii_words = [w.strip(".,!?-:;()[]") for w in words
                   if all(ord(c) < 128 for c in w) and len(w) > 2]
    if len(ascii_words) >= 2:
        return " ".join(ascii_words[:8])
    # Fallback: return first 60 chars
    return topic[:60]

def _draw_news_banner(draw, img, top_y, bottom_y, topic, font_topic):
    # Dark blue banner when no topic image available
    draw.rectangle([0, top_y, W, bottom_y], fill=(5, 15, 70))
    draw.rectangle([0, top_y, W, top_y + 6], fill=(200, 20, 20))
    draw.rectangle([0, bottom_y - 6, W, bottom_y], fill=(200, 20, 20))
    display = _header_topic(topic)
    ty = top_y + 20
    for line in wrap_text(draw, display[:100], font_topic, W - 60)[:3]:
        shadow_text(draw, (24, ty), line, font_topic, fill=(255, 255, 255))
        ty += 55


# ===========================================================================
# Image cache for topic images
# ===========================================================================
_IMG_CACHE = {}  # topic_key -> PIL Image or None


def topic_keywords(topic, description=""):
    """
    Extract English search keywords from topic.
    v9 fix: if topic is Tamil script (non-ASCII), use English description instead.
    """
    # Try to get ASCII words from topic title
    words = [w.strip(".,!?-:;()[]") for w in topic.split()
             if all(ord(c) < 128 for c in w) and len(w) > 3]
    if len(words) >= 2:
        return " ".join(words[:5])
    # Fallback to English description (from RSS feed)
    if description:
        desc_words = [w.strip(".,!?-:;()[]") for w in description.split()
                      if all(ord(c) < 128 for c in w) and len(w) > 3]
        if desc_words:
            return " ".join(desc_words[:5])
    return "india news breaking today"


def fetch_topic_image(topic: str, article_image_url: str = "", description: str = ""):
    """
    Fetch a relevant photo for the topic.
    Priority order:
      1. article_image_url (from RSS feed enclosure/media) - FREE, always relevant
      2. Pexels API (needs PEXELS_KEY)
      3. Pixabay API (needs PIXABAY_KEY)
      4. Category-colored PIL image (always works, no API needed)
    Returns PIL Image (RGB) or None.
    Cached so same topic doesn't re-fetch on every frame.
    """
    import hashlib, io as _io, urllib.request as _urllib

    key = hashlib.md5(topic.encode("utf-8")).hexdigest()
    if key in _IMG_CACHE:
        return _IMG_CACHE[key]

    kw = topic_keywords(topic, description) or topic[:30]

    # Priority 1: article thumbnail from RSS
    if article_image_url:
        try:
            data = _urllib.urlopen(article_image_url, timeout=10).read()
            img  = Image.open(_io.BytesIO(data)).convert("RGB")
            _IMG_CACHE[key] = img
            print(f"  [TopicImg] RSS article image fetched")
            return img
        except Exception as e:
            print(f"  [TopicImg RSS] {e}")

    # Priority 2: Pexels
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
                print(f"  [TopicImg] Pexels photo for: {kw[:30]}")
                return img
        except Exception as e:
            print(f"  [TopicImg Pexels] {e}")

    # Priority 3: Pixabay
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
                img_url = hits[0].get("webformatURL", "")
                data = _urllib.urlopen(img_url, timeout=10).read()
                img = Image.open(_io.BytesIO(data)).convert("RGB")
                _IMG_CACHE[key] = img
                print(f"  [TopicImg] Pixabay photo for: {kw[:30]}")
                return img
        except Exception as e:
            print(f"  [TopicImg Pixabay] {e}")

    # Priority 4: Category-colored background (always works)
    topic_lower = (topic + " " + description).lower()
    if any(w in topic_lower for w in ["sport", "cricket", "football", "ipl", "match", "win"]):
        color = (0, 80, 30)      # dark green - sports
    elif any(w in topic_lower for w in ["weather", "rain", "flood", "cyclone", "storm"]):
        color = (0, 40, 90)      # deep blue - weather
    elif any(w in topic_lower for w in ["petrol", "price", "economy", "rupee", "bank", "finance"]):
        color = (60, 30, 0)      # dark orange-brown - economy
    elif any(w in topic_lower for w in ["politic", "election", "government", "minister", "party"]):
        color = (60, 0, 0)       # dark red - politics
    elif any(w in topic_lower for w in ["health", "hospital", "doctor", "covid", "disease"]):
        color = (0, 60, 60)      # dark teal - health
    elif any(w in topic_lower for w in ["film", "actor", "actress", "cinema", "movie", "kollywood"]):
        color = (50, 0, 60)      # dark purple - entertainment
    else:
        color = (5, 15, 70)      # navy - general news

    img = Image.new("RGB", (W, 400), color)
    d   = ImageDraw.Draw(img)
    # Draw subtle grid pattern to add texture
    for x in range(0, W, 60):
        d.line([(x, 0), (x, 400)], fill=tuple(min(255, c+8) for c in color), width=1)
    for y in range(0, 400, 60):
        d.line([(0, y), (W, y)], fill=tuple(min(255, c+8) for c in color), width=1)
    _IMG_CACHE[key] = img
    print(f"  [TopicImg] Using category color background: {color}")
    return img


# ===========================================================================
# News graphics compositor
# ===========================================================================
def draw_news_graphics(bg_frame, topic, caption_text,
                        font_ch, font_topic, font_cap, font_ad, font_ad2,
                        is_wav2lip=False, article_image_url="", description=""):
    try:
        img  = Image.fromarray(bg_frame.astype(np.uint8), "RGB")
        alpha = 40 if is_wav2lip else 100
        ov   = Image.new("RGBA", (W, H), (0, 0, 0, alpha))
        img  = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
        draw = ImageDraw.Draw(img)

        # Layout constants
        HEADER_H  = 145   # channel name bar height
        IMG_H     = 400   # relevant image zone height below header
        IMG_TOP   = HEADER_H
        TOPIC_TOP = IMG_TOP + IMG_H

        # --- TOP HEADER ---
        draw.rectangle([0, 0, W, HEADER_H], fill=(5, 15, 70))
        draw.rectangle([0, HEADER_H - 2, W, HEADER_H + 6], fill=(200, 20, 20))
        shadow_text(draw, (28, 16),  CHANNEL,         font_ch,  fill=(255, 255, 255))
        shadow_text(draw, (28, 82),  "BREAKING NEWS", font_ad2, fill=(255, 60,  60))

        # --- RELEVANT TOPIC IMAGE ZONE ---
        topic_img = fetch_topic_image(topic, article_image_url, description)
        if topic_img:
            try:
                tw_i, th_i = topic_img.size
                scale_i    = W / tw_i
                nw_i = W
                nh_i = int(th_i * scale_i)
                img_resized = topic_img.resize((nw_i, nh_i), Image.LANCZOS)
                crop_top    = max(0, (nh_i - IMG_H) // 2)
                img_cropped = img_resized.crop((0, crop_top, nw_i, crop_top + IMG_H))
                img.paste(img_cropped, (0, IMG_TOP))
                draw = ImageDraw.Draw(img)
                print(f"  [TopicImg] Displayed in header zone")
            except Exception as e:
                print(f"  [TopicImg draw] {e}")
                _draw_news_banner(draw, img, IMG_TOP, TOPIC_TOP, topic, font_topic)
        else:
            _draw_news_banner(draw, img, IMG_TOP, TOPIC_TOP, topic, font_topic)

        # --- TOPIC BAR ---
        draw.rectangle([0, TOPIC_TOP, W, TOPIC_TOP + 144], fill=(0, 0, 0, 210))
        draw.rectangle([0, TOPIC_TOP, 8, TOPIC_TOP + 144], fill=(200, 20, 20))
        display_topic = _header_topic(topic)
        ty = TOPIC_TOP + 11
        for line in wrap_text(draw, display_topic[:100], font_topic, W - 60)[:2]:
            shadow_text(draw, (24, ty), line, font_topic, fill=(255, 215, 0))
            ty += 60

        # --- LOWER-THIRD CAPTION ---
        if caption_text.strip():
            zone_top    = int(H * CAPTION_TOP_PCT)
            zone_bottom = int(H * CAPTION_BOTTOM_PCT)
            zone_h      = zone_bottom - zone_top
            cap_lines   = wrap_text(draw, caption_text, font_cap, W - 80)[:4]
            lh          = th(draw, "A", font_cap) + 16
            total_h     = len(cap_lines) * lh
            pad         = 20
            cy          = zone_top + max(0, (zone_h - total_h) // 2)
            draw.rectangle([0, cy - pad, W, cy + total_h + pad], fill=(0, 0, 0, 185))
            draw.rectangle([0, cy - pad, 8, cy + total_h + pad], fill=(255, 215, 0))
            for line in cap_lines:
                centre_shadow(draw, line, font_cap, cy, fill=(255, 255, 255))
                cy += lh

        # --- FOOTER ---
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
    for raw_line in script_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        upper = line.upper()
        if any(upper.startswith(m) for m in _SKIP_MARKERS):
            skip = True; continue
        if any(upper.startswith(m) for m in _SECTION_MARKERS):
            skip = False; continue
        if skip:
            continue
        if line.startswith("[") and line.endswith("]"):
            continue
        if line.startswith("#"):
            continue
        if line.startswith("---"):
            continue
        spoken.append(line)
    result = " ".join(spoken).strip()
    if not result:
        # Fallback: return all non-empty, non-marker lines
        result = " ".join(
            l.strip() for l in script_text.splitlines()
            if l.strip() and not l.strip().startswith("#")
               and not l.strip().startswith("[")
        )
    return result


# ===========================================================================
# Utilities
# ===========================================================================
def gradient_frame(t):
    frame = np.zeros((H, W, 3), dtype=np.uint8)
    shift = int(20 * math.sin(2 * math.pi * t / 8))
    for y in range(H):
        r = int(max(0, min(255, 5  + shift + 10 * y / H)))
        g = int(max(0, min(255, 15 + shift +  8 * y / H)))
        b = int(max(0, min(255, 70 + shift + 20 * y / H)))
        frame[y, :] = [r, g, b]
    return frame

def split_segs(text, n):
    if n <= 1:
        return [text]
    words = text.split()
    if not words:
        return [text] * n
    chunk = max(1, len(words) // n)
    segs  = []
    for i in range(n):
        start = i * chunk
        end   = start + chunk if i < n - 1 else len(words)
        segs.append(" ".join(words[start:end]))
    return segs

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
                      anchor_face=None, bg_video_path=None, bg_photo_path=None,
                      article_image_url="", description=""):
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

    # STEP 1: SadTalker -> real body+head animated video
    st_out_dir = output_path.replace('.mp4', '_sadtalker')
    st_video   = run_sadtalker(anchor_face, audio_path, st_out_dir)

    # STEP 2: Wav2Lip -> lip sync on top of SadTalker (or raw face)
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

    # STEP 3: HeadAnimator fallback (synthetic natural movement)
    head_animator = None
    if wl_clip is None:
        print("  [HeadAnimator] Using synthetic head/body movement")
        head_animator = HeadAnimator(anchor_face, duration)

    # Background fallback (only used if no AI face at all)
    bg_clip = bg_photo = None
    if wl_clip is None and head_animator is None:
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

    def make_frame(t):
        try:
            if wl_clip is not None:
                frame = wl_clip.get_frame(t)
                if frame.shape[:2] != (H, W):
                    frame = np.array(Image.fromarray(frame).resize((W, H), Image.LANCZOS))
                is_wl = True
            elif head_animator is not None:
                frame = head_animator.get_frame(t)
                is_wl = False
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
            is_wav2lip=is_wl,
            article_image_url=article_image_url,
            description=description
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

    print("Tamil News Video Creator v9  (SadTalker + Wav2Lip + HeadAnimator)")
    print(f"Time            : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"PEXELS_API_KEY  : {'SET' if PEXELS_KEY  else 'NOT SET'}")
    print(f"PIXABAY_API_KEY : {'SET' if PIXABAY_KEY else 'NOT SET'}")
    print(f"SadTalker       : {'INSTALLED' if st_ok else 'NOT FOUND'}")
    print(f"Wav2Lip         : {'INSTALLED' if wl_ok else 'NOT FOUND'}")
    print(f"HeadAnimator    : ALWAYS AVAILABLE (synthetic fallback)")
    print(f"SADTALKER_TIMEOUT: {SADTALKER_TIMEOUT}s per video")
    print(f"ANCHOR SRC      : {'user PNG' if os.path.exists(SUPPLIED_ANCHOR_PNG) else 'API download'}")

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
        topic       = script_data.get("topic", f"News {i}")
        description = script_data.get("description", "")
        img_url     = script_data.get("article_image_url", "")

        print(f"\n{'='*60}")
        print(f"Video {i}/{len(scripts_data)}: {topic[:60]}")
        print(f"{'='*60}")

        audio_path = audio_data.get("audio_file", "")
        if not os.path.exists(audio_path):
            print(f"  SKIP: audio not found: {audio_path}"); continue

        spoken_text = extract_spoken(script_data.get("script", "")) or topic
        if not spoken_text.strip():
            spoken_text = topic

        keywords    = topic_keywords(topic, description)
        timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(VIDEO_DIR, f"reel_{i}_{timestamp}.mp4")

        if output_path in existing_paths:
            print("  SKIP: already in manifest"); continue

        # BG assets only when both AI models unavailable
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
                anchor_face        = anchor_face,
                bg_video_path      = final_vid,
                bg_photo_path      = final_photo,
                article_image_url  = img_url,
                description        = description,
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
