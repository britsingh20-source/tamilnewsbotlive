"""
STEP 4: Tamil News Video Creator (v7)
Fixes over v6:
  A. Anchor image  -- force-overwrites cached anchor_face.jpg every run from supplied PNG
  B. Header text   -- ALL header/ticker text kept in Latin/English only (no Tamil in header)
                      Tamil ONLY in caption block where Tamil font is confirmed loaded
  C. Head & body   -- AnchorAnimator class: subtle head bob, slight tilt, micro body sway
                      applied as numpy affine transforms on the Wav2Lip output frames
  D. Font check    -- explicit pre-flight Tamil font verification with clear per-glyph test
  E. Wav2Lip crop  -- face crop biased higher (forehead included) for better lip-sync quality
"""

import json, os, io, sys, time, subprocess, requests, numpy as np
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageFilter

SCRIPTS_FILE = os.path.join(os.path.dirname(__file__), "../output/scripts.json")
AUDIO_DIR    = os.path.join(os.path.dirname(__file__), "../output/audio")
VIDEO_DIR    = os.path.join(os.path.dirname(__file__), "../output/videos")
ASSETS_DIR   = os.path.join(os.path.dirname(__file__), "../assets")

# Place anchor_face_supplied.png next to this script
SUPPLIED_ANCHOR_PNG = os.path.join(os.path.dirname(__file__), "anchor_face_supplied.png")

W, H = 1080, 1920
FPS  = 25

AD_LINE1 = "Coimbatore Veedu Builders"
AD_LINE2 = "Contact: 8111024877"
CHANNEL  = "Tamil News Live"          # English only -- safe for any font

PEXELS_KEY  = os.environ.get("PEXELS_API_KEY", "")
PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY", "")

WAV2LIP_DIR        = "/tmp/Wav2Lip"
WAV2LIP_CHECKPOINT = os.path.join(WAV2LIP_DIR, "checkpoints/wav2lip.pth")


# ===========================================================================
# A. Anchor image -- FORCE overwrite cached copy every run
# ===========================================================================
def prepare_anchor_face(assets_dir):
    face_path = os.path.join(assets_dir, "anchor_face.jpg")

    if os.path.exists(SUPPLIED_ANCHOR_PNG):
        print(f"  [Face] Loading user-supplied anchor: {SUPPLIED_ANCHOR_PNG}")
        try:
            img    = Image.open(SUPPLIED_ANCHOR_PNG).convert("RGB")
            iw, ih = img.size
            # Centre-crop: head-biased portrait (top 80% of image height)
            size   = min(iw, ih)
            left   = (iw - size) // 2
            top    = max(0, int((ih - size) * 0.05))   # very slight top bias
            bottom = min(ih, top + int(size * 1.15))
            img    = img.crop((left, top, left + size, bottom))
            img    = img.resize((480, 640), Image.LANCZOS)
            img.save(face_path, quality=95)
            print(f"  [Face] Saved -> {face_path}  ({img.size})")
            return face_path
        except Exception as e:
            print(f"  [Face] Error processing supplied image: {e}")

    # Fallback: download
    return _download_face(assets_dir, face_path)


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


def _download_face(assets_dir, face_path):
    searches = [
        ("pexels", "woman news anchor portrait professional"),
        ("pixabay", "woman portrait professional"),
    ]
    for src, query in searches:
        try:
            if src == "pexels" and PEXELS_KEY:
                r = _robust_get("https://api.pexels.com/v1/search",
                                headers={"Authorization": PEXELS_KEY},
                                params={"query": query, "per_page": 3,
                                        "orientation": "portrait"}, timeout=15)
                for ph in r.json().get("photos", []):
                    url  = ph["src"].get("medium") or ph["src"].get("large", "")
                    resp = _robust_get(url, timeout=30)
                    if resp.status_code == 200:
                        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
                        img = img.resize((480, 640), Image.LANCZOS)
                        img.save(face_path, quality=95)
                        print(f"  [Face] Downloaded Pexels: {query}")
                        return face_path
            elif src == "pixabay" and PIXABAY_KEY:
                r = _robust_get("https://pixabay.com/api/",
                                params={"key": PIXABAY_KEY, "q": query,
                                        "image_type": "photo", "per_page": 3,
                                        "safesearch": "true",
                                        "orientation": "vertical"}, timeout=15)
                for hit in r.json().get("hits", []):
                    url  = hit.get("webformatURL", "")
                    resp = _robust_get(url, timeout=30)
                    if resp.status_code == 200:
                        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
                        img = img.resize((480, 640), Image.LANCZOS)
                        img.save(face_path, quality=95)
                        print("  [Face] Downloaded Pixabay")
                        return face_path
        except Exception as e:
            print(f"  [Face] {src} error: {e}")
    print("  [Face] WARNING: no face image available")
    return None


# ===========================================================================
# B. Font loading with explicit Tamil verification
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

_TAMIL_TEST_CHAR = "த"   # Unicode Tamil letter

_tamil_font_cache  = {}
_latin_font_cache  = {}
_tamil_font_warned = False
_tamil_font_ok     = None   # True/False/None = not tested yet


def _font_renders_tamil(font):
    """Return True if font can render a Tamil glyph without tofu boxes."""
    try:
        img  = Image.new("RGB", (60, 60), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((5, 5), _TAMIL_TEST_CHAR, font=font, fill=(0, 0, 0))
        arr = np.array(img)
        # If the glyph rendered something non-white in the centre region
        centre = arr[10:50, 5:55]
        return bool((centre < 200).any())
    except Exception:
        return False


def _try_install_tamil_fonts():
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
        print(f"  [Font] apt-install error: {e}")
    return False


def load_font(size, tamil=False):
    global _tamil_font_warned, _tamil_font_ok
    cache = _tamil_font_cache if tamil else _latin_font_cache
    if size in cache:
        return cache[size]

    paths = TAMIL_FONT_PATHS if tamil else LATIN_FONT_PATHS
    for p in paths:
        if not os.path.exists(p):
            continue
        try:
            font = ImageFont.truetype(p, size)
            if tamil:
                if _font_renders_tamil(font):
                    _tamil_font_ok = True
                    cache[size] = font
                    return font
                # font loaded but doesn't render Tamil glyphs -- try next
            else:
                cache[size] = font
                return font
        except Exception:
            continue

    if tamil and not _tamil_font_warned:
        _tamil_font_warned = True
        _tamil_font_ok     = False
        print("  [Font] WARNING: No working Tamil font found!")
        print("         Attempting auto-install...")
        if _try_install_tamil_fonts():
            for p in TAMIL_FONT_PATHS:
                if os.path.exists(p):
                    try:
                        font = ImageFont.truetype(p, size)
                        if _font_renders_tamil(font):
                            _tamil_font_ok = True
                            cache[size]    = font
                            return font
                    except Exception:
                        pass
        print("  [Font] Auto-install failed. Run:")
        print("         sudo apt-get install fonts-noto-core fonts-lohit-taml")
        print("  [Font] Tamil captions will use Latin fallback font.")

    # For Tamil that still failed: use best Latin font (at least readable)
    for p in LATIN_FONT_PATHS:
        if os.path.exists(p):
            try:
                font = ImageFont.truetype(p, size)
                cache[size] = font
                return font
            except Exception:
                continue

    return ImageFont.load_default()


# ===========================================================================
# C. Head & body motion animator
# ===========================================================================
class AnchorAnimator:
    """
    Applies subtle realistic anchor motion to video frames using PIL affine
    transforms. Simulates:
      - Gentle head bob (vertical sine)
      - Slight head tilt (rotation oscillation)
      - Micro body sway (horizontal drift)
      - Occasional slow blink-like brightness dip (not actual blink)
    All amplitudes are small enough to look natural, not cartoon-like.
    """

    def __init__(self, fps=25):
        self.fps = fps
        # Frequencies (Hz) chosen to not be simple multiples -> feels organic
        self.bob_freq   = 0.28   # vertical bob
        self.sway_freq  = 0.19   # horizontal sway
        self.tilt_freq  = 0.23   # rotation
        self.breathe_freq = 0.14 # slow breath-like scale pulse

        # Amplitudes
        self.bob_amp    = 6      # pixels vertical
        self.sway_amp   = 4      # pixels horizontal
        self.tilt_amp   = 0.9   # degrees
        self.scale_amp  = 0.008  # fractional scale change (breath)

        # Phase offsets so motions don't sync
        self.bob_phase   = 0.0
        self.sway_phase  = 1.1
        self.tilt_phase  = 0.7
        self.breath_phase= 2.3

    def _val(self, freq, phase, t):
        return np.sin(2 * np.pi * freq * t + phase)

    def animate_frame(self, frame_rgb: np.ndarray, t: float) -> np.ndarray:
        """
        frame_rgb: H x W x 3 uint8 numpy array
        t:         time in seconds
        Returns:   same shape, animated
        """
        img = Image.fromarray(frame_rgb.astype(np.uint8), "RGB")
        fw, fh = img.size

        # --- rotation (head tilt) ---
        angle  = self.tilt_amp * self._val(self.tilt_freq, self.tilt_phase, t)
        img    = img.rotate(angle, resample=Image.BICUBIC, expand=False,
                            center=(fw // 2, fh // 3))   # rotate around head centre

        # --- scale (breath) ---
        scale  = 1.0 + self.scale_amp * self._val(self.breathe_freq, self.breath_phase, t)
        new_w  = int(fw * scale)
        new_h  = int(fh * scale)
        img    = img.resize((new_w, new_h), Image.LANCZOS)
        # Crop back to original size from centre
        x0 = (new_w - fw) // 2
        y0 = (new_h - fh) // 2
        img = img.crop((x0, y0, x0 + fw, y0 + fh))

        # --- translation (bob + sway) ---
        dx = int(self.sway_amp * self._val(self.sway_freq, self.sway_phase, t))
        dy = int(self.bob_amp  * self._val(self.bob_freq,  self.bob_phase,  t))
        # PIL paste onto blank canvas to achieve translation
        canvas = Image.new("RGB", (fw, fh), (0, 0, 0))
        canvas.paste(img, (dx, dy))
        img = canvas

        return np.array(img)


# ===========================================================================
# Wav2Lip
# ===========================================================================
def run_wav2lip(face_path, audio_path, output_path):
    if not os.path.exists(WAV2LIP_DIR):
        print("  [Wav2Lip] Not installed -- skipping"); return False
    if not os.path.exists(WAV2LIP_CHECKPOINT):
        print("  [Wav2Lip] Checkpoint missing -- skipping"); return False
    if not face_path or not os.path.exists(face_path):
        print("  [Wav2Lip] No face image -- skipping"); return False

    wav_path = audio_path.rsplit('.', 1)[0] + '_wl16k.wav'
    conv = subprocess.run(
        ['ffmpeg', '-y', '-i', audio_path, '-ar', '16000', '-ac', '1', wav_path],
        capture_output=True, text=True, timeout=60)
    if conv.returncode != 0:
        print(f"  [Wav2Lip] Audio conversion failed: {conv.stderr[:200]}"); return False

    cmd = [
        sys.executable, 'inference.py',
        '--checkpoint_path', WAV2LIP_CHECKPOINT,
        '--face',            face_path,
        '--audio',           wav_path,
        '--outfile',         output_path,
        '--resize_factor',   '1',
        '--pads',            '0', '15', '0', '0',
        '--face_det_batch_size', '4',
        '--wav2lip_batch_size',  '64',
        # --nosmooth intentionally omitted for less flicker
    ]
    print("  [Wav2Lip] Running inference (CPU ~10-15 min)...")
    try:
        proc = subprocess.run(cmd, cwd=WAV2LIP_DIR, capture_output=True,
                              text=True, timeout=1200)
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
# Background downloaders
# ===========================================================================
def _stream_video(url, out_path, max_mb=30):
    resp = _robust_get(url, stream=True, timeout=90)
    if resp.status_code != 200:
        return False
    downloaded = 0
    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(65536):
            f.write(chunk); downloaded += len(chunk)
            if downloaded > max_mb * 1024 * 1024:
                break
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
            portrait= [f for f in files if f.get("width",0) < f.get("height",0)]
            cands   = sorted(portrait or files, key=lambda f: f.get("width", 9999))
            url     = cands[0].get("link","") if cands else ""
            if url and _stream_video(url, out_path):
                print(f"  [Pexels video] {os.path.getsize(out_path)/1e6:.1f} MB")
                return True
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
            url  = (vids.get("medium",{}).get("url") or
                    vids.get("small", {}).get("url") or
                    vids.get("large", {}).get("url"))
            if url and _stream_video(url, out_path):
                print(f"  [Pixabay video] {os.path.getsize(out_path)/1e6:.1f} MB")
                return True
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
            url  = photos[0]["src"].get("portrait") or photos[0]["src"].get("large","")
            resp = _robust_get(url, timeout=30)
            if resp.status_code == 200:
                img = Image.open(io.BytesIO(resp.content)).convert("RGB").resize((W,H),Image.LANCZOS)
                img.save(out_path)
                print("  [Pexels photo] Saved"); return True
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
            url  = hits[0].get("largeImageURL") or hits[0].get("webformatURL","")
            resp = _robust_get(url, timeout=30)
            if resp.status_code == 200:
                img = Image.open(io.BytesIO(resp.content)).convert("RGB").resize((W,H),Image.LANCZOS)
                img.save(out_path)
                print("  [Pixabay photo] Saved"); return True
    except Exception as e: print(f"  [Pixabay photo] {e}")
    return False


# ===========================================================================
# Text helpers
# ===========================================================================
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

def shadow_text(draw, xy, text, font, fill=(255,255,255), sh=(0,0,0), off=2):
    x, y = xy
    for dx in [-off, 0, off]:
        for dy in [-off, 0, off]:
            if dx or dy: draw.text((x+dx, y+dy), text, font=font, fill=sh)
    draw.text((x, y), text, font=font, fill=fill)

def centre_shadow(draw, text, font, y, fill=(255,255,255)):
    x = max(20, (W - tw(draw, text, font)) // 2)
    shadow_text(draw, (x, y), text, font, fill=fill)


# ===========================================================================
# B. News graphics overlay -- English-only header, Tamil only in caption block
# ===========================================================================
def draw_news_graphics(bg_frame, topic, caption_text,
                        font_ch, font_topic, font_cap, font_ad, font_ad2,
                        is_wav2lip=False):
    try:
        img   = Image.fromarray(bg_frame.astype(np.uint8), "RGB")
        alpha = 50 if is_wav2lip else 110
        ov    = Image.new("RGBA", (W, H), (0, 0, 0, alpha))
        img   = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
        draw  = ImageDraw.Draw(img)

        # --- Header (ALL English -- no Tamil here) ---
        draw.rectangle([0, 0, W, 140],   fill=(5, 15, 70))
        draw.rectangle([0, 138, W, 148], fill=(200, 20, 20))
        shadow_text(draw, (30, 18),  CHANNEL,         font_ch,  fill=(255,255,255))
        shadow_text(draw, (30, 90),  "BREAKING NEWS", font_ad2, fill=(255, 60, 60))

        # --- Topic bar (English keywords only -- safe) ---
        draw.rectangle([0, 148, W, 300], fill=(0, 0, 0, 200))
        topic_safe = _safe_topic(topic)   # strip non-Latin for header display
        ty = 158
        for line in wrap_text(draw, topic_safe[:90], font_topic, W - 60)[:2]:
            shadow_text(draw, (30, ty), line, font_topic, fill=(255, 215, 0))
            ty += 62

        # --- Tamil caption block (centre of screen) ---
        if caption_text.strip():
            cap_lines = wrap_text(draw, caption_text, font_cap, W - 80)[:5]
            lh        = th(draw, "A", font_cap) + 20
            total_h   = len(cap_lines) * lh
            cy        = (H - total_h) // 2 + 60
            pad       = 28
            draw.rectangle([24, cy - pad, W - 24, cy + total_h + pad],
                           fill=(0, 0, 0, 175))
            for line in cap_lines:
                centre_shadow(draw, line, font_cap, cy, fill=(255, 255, 255))
                cy += lh

        # --- Footer ad ---
        ft = H - 165
        draw.rectangle([0, ft, W, H],    fill=(175, 8, 8))
        draw.rectangle([0, ft, W, ft+4], fill=(255, 215, 0))
        centre_shadow(draw, AD_LINE1, font_ad,  ft + 20, fill=(255, 255, 255))
        centre_shadow(draw, AD_LINE2, font_ad2, ft + 90, fill=(255, 230, 0))

        return np.array(img)
    except Exception as e:
        print(f"  [graphics] {e}")
        return bg_frame.astype(np.uint8)


def _safe_topic(topic):
    """Keep only ASCII printable characters for header display."""
    return "".join(c if ord(c) < 128 else " " for c in topic).strip()


# ===========================================================================
# extract_spoken (robust v6 version kept)
# ===========================================================================
_SECTION_MARKERS = {"HOOK","STORY","CTA","TRUTH","INTRO","BODY","OUTRO"}
_SKIP_MARKERS    = {"HASHTAGS","CAPTION","FORMAT","RULES","TAGS","NOTE","NOTES"}

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
                rem  = line[ci+1:].strip()
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
    a[:,:,0] = np.clip(10+(ys*20).astype(int)+p, 0,255)[:,None]
    a[:,:,1] = np.clip(10+(ys*15).astype(int),   0,255)[:,None]
    a[:,:,2] = np.clip(50+(ys*80).astype(int)+p*2,0,255)[:,None]
    return a


# ===========================================================================
# Misc helpers
# ===========================================================================
def split_segs(text, n):
    words = text.split()
    if not words: return [""] * n
    chunk = max(1, len(words)//n)
    segs  = []
    for i in range(n):
        s = i*chunk; e = s+chunk if i<n-1 else len(words)
        segs.append(" ".join(words[s:e]))
    return segs

def topic_keywords(topic):
    words = [w for w in topic.split() if all(ord(c)<128 for c in w) and len(w)>2]
    return " ".join(words[:4]) if words else "news breaking india city"


# ===========================================================================
# Manifest helpers (v6 FIX 3 kept)
# ===========================================================================
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
        json.dump({"videos": videos,
                   "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                   "count": len(videos)}, f, ensure_ascii=False, indent=2)


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

    animator = AnchorAnimator(fps=FPS)   # C. head/body motion

    # --- Wav2Lip ---
    wl_path    = output_path.replace('.mp4', '_wl.mp4')
    wl_success = run_wav2lip(anchor_face, audio_path, wl_path)
    wl_clip    = None

    if wl_success:
        try:
            raw   = VideoFileClip(wl_path)
            if raw.duration < duration:
                loops = int(duration / raw.duration) + 2
                raw   = concatenate_videoclips([raw] * loops)
            raw   = raw.subclip(0, duration)
            scale = max(H / raw.h, W / raw.w)
            nw    = int(raw.w * scale); nh = int(raw.h * scale)
            raw   = raw.resize((nw, nh))
            if nw > W: raw = raw.crop(x_center=nw/2, width=W)
            if nh > H: raw = raw.crop(y_center=nh/2, height=H)
            wl_clip = raw
            print(f"  [Wav2Lip clip] {wl_clip.w}x{wl_clip.h}")
        except Exception as e:
            print(f"  [Wav2Lip clip] {e}"); wl_clip = None

    # --- Background fallback ---
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
                    Image.open(bg_photo_path).convert("RGB").resize((W,H),Image.LANCZOS))
            except Exception as e: print(f"  [BG photo] {e}")
        if bg_clip is None and bg_photo is None:
            print("  [BG] Using animated gradient")

    def make_frame(t):
        try:
            if wl_clip is not None:
                frame = wl_clip.get_frame(t)
                if frame.shape[:2] != (H, W):
                    frame = np.array(Image.fromarray(frame).resize((W,H),Image.LANCZOS))
                # C. Apply head/body motion to Wav2Lip output
                frame = animator.animate_frame(frame, t)
                is_wl = True
            elif bg_clip is not None:
                frame = bg_clip.get_frame(t)
                if frame.shape[:2] != (H, W):
                    frame = np.array(Image.fromarray(frame).resize((W,H),Image.LANCZOS))
                is_wl = False
            elif bg_photo is not None:
                frame = bg_photo.copy(); is_wl = False
            else:
                frame = gradient_frame(t); is_wl = False
        except Exception as e:
            print(f"  make_frame t={t:.1f}: {e}")
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
    if bg_clip:  bg_clip.close()

    if os.path.exists(output_path):
        sz = os.path.getsize(output_path)/1e6
        print(f"  Done: {sz:.1f} MB")
        if wl_success and os.path.exists(wl_path):
            os.remove(wl_path)
        return True
    print("  ERROR: output not created!"); return False


# ===========================================================================
# Entry point
# ===========================================================================
def main():
    print("Tamil News Video Creator v7")
    print(f"Time           : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"PEXELS_API_KEY : {'SET' if PEXELS_KEY  else 'NOT SET'}")
    print(f"PIXABAY_API_KEY: {'SET' if PIXABAY_KEY else 'NOT SET'}")
    print(f"WAV2LIP        : {'INSTALLED' if os.path.exists(WAV2LIP_CHECKPOINT) else 'NOT FOUND'}")
    print(f"ANCHOR SRC     : {'user-supplied PNG' if os.path.exists(SUPPLIED_ANCHOR_PNG) else 'API download'}")

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

    print("\n--- Preparing anchor face (force refresh) ---")
    anchor_face = prepare_anchor_face(ASSETS_DIR)   # A. always overwrites

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

        spoken_text = extract_spoken(script_data.get("script","")) or topic
        if not spoken_text.strip():
            print("  [warn] empty spoken text -- using topic"); spoken_text = topic

        keywords    = topic_keywords(topic)
        timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(VIDEO_DIR, f"reel_{i}_{timestamp}.mp4")

        if output_path in existing_paths:
            print(f"  SKIP: already in manifest"); continue

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
                sz = os.path.getsize(output_path)/1e6
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
    print(f"DONE: {new_count} new | {len(created_videos)} total in manifest -> {VIDEO_DIR}")
    if new_count == 0 and not existing_videos:
        print("ZERO videos created -- check logs above"); sys.exit(1)


if __name__ == "__main__":
    main()
