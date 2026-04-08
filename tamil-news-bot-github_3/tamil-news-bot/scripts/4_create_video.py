"""
STEP 4: Tamil News Video Creator (v17)
=======================================
- SadTalker: lip sync + head & body movements
- Wav2Lip fallback
- Audio volume boosted 2x
- Captions in lower third (above footer)
- Dark navy background
- TOP PANEL: Multiple Pexels B-roll clips cutting every 8-10s (true B-roll)
- Anchor occupies lower 72% as always
"""

import json, os, sys, re, subprocess, glob, tempfile, numpy as np, requests, io
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

try:
    from moviepy.editor import (VideoClip, AudioFileClip,
                                 VideoFileClip, concatenate_videoclips)
except ImportError:
    print("ERROR: moviepy not installed.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPTS_DIR     = os.path.dirname(__file__)
SCRIPTS_FILE    = os.path.join(SCRIPTS_DIR, "../output/scripts.json")
AUDIO_DIR       = os.path.join(SCRIPTS_DIR, "../output/audio")
VIDEO_DIR       = os.path.join(SCRIPTS_DIR, "../output/videos")
ASSETS_DIR      = os.path.join(SCRIPTS_DIR, "../assets")
SUPPLIED_ANCHOR = os.path.join(SCRIPTS_DIR, "anchor_face_supplied.png")

W, H   = 1080, 1920
FPS    = 25

AD_LINE1 = "Coimbatore Veedu Builders"
AD_LINE2 = "Contact: 8111024877"
CHANNEL  = "Tamil News Live"

VOLUME_BOOST    = 2.0
BROLL_CUT_EVERY = 8.0   # seconds between B-roll cuts

SADTALKER_DIR      = os.environ.get("SADTALKER_DIR", "/tmp/SadTalker")
WAV2LIP_DIR        = os.environ.get("WAV2LIP_DIR", "/tmp/Wav2Lip")
WAV2LIP_CHECKPOINT = os.path.join(WAV2LIP_DIR, "checkpoints/wav2lip_gan.pth")
PEXELS_API_KEY     = os.environ.get("PEXELS_API_KEY", "")

# Layout
ANCHOR_H      = int(H * 0.72)        # 1382px — anchor bottom section
TOP_PANEL_H   = H - ANCHOR_H         # 538px  — B-roll top section
HEADER_BAR_H  = 130                  # channel name overlay inside top panel
TOPIC_STRIP_H = 120
FOOTER_H      = 160
LOWER_THIRD_H = 240


# ===========================================================================
# Tamil → English keyword map
# ===========================================================================
TAMIL_KEYWORD_MAP = [
    ("இரான்",        "Iran"),
    ("அமெரிக்க",     "America USA"),
    ("ரஷ்ய",         "Russia war"),
    ("சீன",          "China"),
    ("பாகிஸ்தான்",   "Pakistan"),
    ("இஸ்ரேல்",      "Israel"),
    ("உக்ரைன்",      "Ukraine war"),
    ("இந்திய",       "India"),
    ("இலங்கை",       "Sri Lanka"),
    ("வங்காளதேசம்",  "Bangladesh"),
    ("போர்",         "war military"),
    ("அணு",          "nuclear"),
    ("விமான",        "aircraft jet"),
    ("ஏவுகணை",       "missile launch"),
    ("வெடிப்பு",     "explosion blast"),
    ("நிலநடுக்கம்",  "earthquake"),
    ("வெள்ளம்",      "flood disaster"),
    ("தேர்தல்",      "election voting"),
    ("நாடாளுமன்ற",   "parliament"),
    ("பொருளாதார",    "economy finance"),
    ("பங்கு சந்தை",  "stock market"),
    ("கிரிக்கெட்",   "cricket"),
    ("கிரிக்கட்",    "cricket"),
    ("ஜெய்ஸ்வால்",   "cricket India"),
    ("சூர்யவன்ஷி",   "cricket India"),
    ("ஐபிஎல்",       "cricket IPL"),
    ("கால்பந்து",     "football"),
    ("ஒலிம்பிக்",    "olympics"),
    ("மருத்துவ",     "hospital doctor"),
    ("புற்றுநோய்",   "cancer hospital"),
    ("வைரஸ்",        "virus"),
    ("கொரோனா",       "coronavirus"),
    ("காலநிலை",      "climate"),
    ("மழை",          "rain storm"),
    ("வெப்பம்",      "heat summer"),
    ("விண்வெளி",     "space rocket"),
    ("ஆர்டெமிஸ்",    "NASA moon"),
    ("நிலா",         "moon space"),
    ("தொழில்நுட்ப",  "technology"),
    ("செயற்கை",      "artificial intelligence"),
    ("பெண்கள்",      "women"),
    ("கர்ப்பம்",     "pregnancy"),
    ("பிரசவ",        "hospital birth"),
    ("குழந்தை",      "child baby"),
    ("கல்வி",        "education"),
    ("போராட்டம்",    "protest"),
    ("கைது",         "police"),
    ("நீதிமன்ற",     "court justice"),
    ("தண்டனை",       "verdict court"),
    ("டிரம்ப்",      "Trump USA"),
    ("மோடி",         "Modi India"),
    ("பிரதமர்",      "parliament government"),
    ("அதிபர்",       "president"),
    ("ஹோர்மூஸ்",    "strait ship sea"),
    ("போர் நிறுத்த", "ceasefire peace"),
    ("சாதி",         "protest India"),
    ("மதுரை",        "India temple"),
    ("கோவில்",       "temple India"),
]

def topic_to_query(topic: str, script_text: str = "") -> str:
    # Use topic + first 200 chars of script, strip script formatting keywords
    combined = topic + " " + re.sub(r'(HOOK|STORY|CTA|TRUTH|HASHTAG)[^\n]*', '', script_text[:300])
    matched = []
    for tamil_kw, english_kw in TAMIL_KEYWORD_MAP:
        if tamil_kw in combined:
            matched.append(english_kw)
        if len(matched) >= 2:
            break
    if matched:
        q = " ".join(matched[:2])
        print(f"  [BRoll] Tamil match → '{q}'")
        return q
    # Extract English words but skip script structure words
    skip = {"HOOK", "STORY", "CTA", "TRUTH", "sec", "TAGS", "FORMAT"}
    en_words = [w for w in re.findall(r'[A-Za-z]{4,}', combined) if w.upper() not in skip]
    if en_words:
        q = " ".join(en_words[:3])
        print(f"  [BRoll] English words → '{q}'")
        return q
    print(f"  [BRoll] Fallback → 'world news'")
    return "world news"


# ===========================================================================
# Fetch multiple B-roll video clips from Pexels
# Returns list of local temp file paths
# ===========================================================================
def fetch_broll_videos(topic: str, script_text: str, count: int = 5) -> list[str]:
    if not PEXELS_API_KEY:
        print("  [BRoll] No PEXELS_API_KEY — skipping")
        return []

    query = topic_to_query(topic, script_text)
    paths = []

    try:
        resp = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": query, "per_page": count, "orientation": "landscape"},
            timeout=10,
        )
        videos = resp.json().get("videos", []) if resp.status_code == 200 else []

        if not videos:
            fallback = query.split()[0] + " news"
            print(f"  [BRoll] No results, fallback → '{fallback}'")
            resp2 = requests.get(
                "https://api.pexels.com/videos/search",
                headers={"Authorization": PEXELS_API_KEY},
                params={"query": fallback, "per_page": count, "orientation": "landscape"},
                timeout=10,
            )
            videos = resp2.json().get("videos", []) if resp2.status_code == 200 else []

        if not videos:
            print("  [BRoll] No videos found")
            return []

        print(f"  [BRoll] Found {len(videos)} videos for '{query}'")

        for idx, video in enumerate(videos):
            try:
                # Pick smallest resolution >= 480p
                vfiles = sorted(
                    [f for f in video.get("video_files", []) if f.get("width", 0) >= 480],
                    key=lambda f: f.get("width", 9999)
                )
                if not vfiles:
                    continue
                url = vfiles[0]["link"]
                video_resp = requests.get(url, timeout=30, stream=True)
                tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False, dir="/tmp")
                for chunk in video_resp.iter_content(chunk_size=1024 * 256):
                    tmp.write(chunk)
                tmp.close()
                size_mb = os.path.getsize(tmp.name) / 1024 / 1024
                print(f"  [BRoll] #{idx+1} {vfiles[0].get('width')}x{vfiles[0].get('height')} {size_mb:.1f}MB → {tmp.name}")
                paths.append(tmp.name)
            except Exception as e:
                print(f"  [BRoll] #{idx+1} download failed: {e}")

    except Exception as e:
        print(f"  [BRoll] Fetch failed: {e}")

    return paths


# ===========================================================================
# Build a single B-roll segment: resize+crop one clip to (W x TOP_PANEL_H)
# Returns numpy array of shape (TOP_PANEL_H, W, 3) or None
# ===========================================================================
def resize_crop_frame(frame: np.ndarray) -> np.ndarray:
    """Resize and center-crop a single frame to (TOP_PANEL_H, W)."""
    img = Image.fromarray(frame.astype(np.uint8), "RGB")
    src_w, src_h = img.size
    target_w, target_h = W, TOP_PANEL_H
    scale = max(target_w / src_w, target_h / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)
    img = img.resize((new_w, new_h), Image.BILINEAR)
    left = (new_w - target_w) // 2
    top  = (new_h - target_h) // 2
    img  = img.crop((left, top, left + target_w, top + target_h))
    return np.array(img)


def prepare_broll_clips(video_paths: list[str], total_duration: float) -> list[dict]:
    """
    Load all broll clips, trim each to BROLL_CUT_EVERY seconds,
    arrange them to cover total_duration with cuts.
    Returns list of dicts: {clip, start_t, end_t}
    """
    segments = []
    t = 0.0

    clip_objects = []
    for p in video_paths:
        try:
            c = VideoFileClip(p, audio=False)
            clip_objects.append(c)
        except Exception as e:
            print(f"  [BRoll] Load failed {p}: {e}")

    if not clip_objects:
        return []

    clip_idx = 0
    clip_offset = 0.0  # how far into current clip we are

    while t < total_duration:
        seg_end = min(t + BROLL_CUT_EVERY, total_duration)
        seg_dur = seg_end - t

        clip = clip_objects[clip_idx % len(clip_objects)]

        # How much is left in this clip from current offset
        clip_remaining = clip.duration - clip_offset
        if clip_remaining < seg_dur:
            # Not enough left — advance to next clip
            clip_idx += 1
            clip_offset = 0.0
            clip = clip_objects[clip_idx % len(clip_objects)]

        seg_clip = clip.subclip(clip_offset, clip_offset + seg_dur)
        segments.append({
            "clip":    seg_clip,
            "start_t": t,
            "end_t":   seg_end,
        })

        clip_offset += seg_dur
        # If we've used most of this clip, move to next
        if clip_offset >= clip.duration - 0.5:
            clip_idx += 1
            clip_offset = 0.0

        t = seg_end

    print(f"  [BRoll] {len(segments)} segments from {len(clip_objects)} clips, covering {total_duration:.1f}s")
    return segments, clip_objects


def get_broll_frame(segments: list[dict], t: float) -> np.ndarray | None:
    """Get the B-roll frame for time t."""
    for seg in segments:
        if seg["start_t"] <= t < seg["end_t"]:
            local_t = t - seg["start_t"]
            try:
                frame = seg["clip"].get_frame(min(local_t, seg["clip"].duration - 0.01))
                return resize_crop_frame(frame)
            except Exception:
                return None
    return None


# ===========================================================================
# Dark background
# ===========================================================================
def make_bg():
    a = np.zeros((H, W, 3), dtype=np.uint8)
    a[:, :, 0] = 8
    a[:, :, 1] = 12
    a[:, :, 2] = 45
    cy = H // 2
    for y in range(0, H, 4):
        boost = int(15 * (1 - abs(y - cy) / cy))
        a[y, :, 2] = np.clip(45 + boost, 0, 80)
    return a


# ===========================================================================
# Font helpers
# ===========================================================================
_font_cache = {}

def load_font(size, tamil=False):
    key = (size, tamil)
    if key in _font_cache:
        return _font_cache[key]
    paths = (
        ["/usr/share/fonts/truetype/noto/NotoSansTamil-Regular.ttf",
         "/usr/share/fonts/truetype/lohit-tamil/Lohit-Tamil.ttf",
         "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
        if tamil else
        ["/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
         "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    )
    for p in paths:
        if os.path.exists(p):
            try:
                f = ImageFont.truetype(p, size)
                _font_cache[key] = f
                return f
            except Exception:
                continue
    return ImageFont.load_default()

def txt_w(draw, text, font):
    try:
        b = draw.textbbox((0, 0), text, font=font)
        return b[2] - b[0]
    except Exception:
        return len(text) * max(getattr(font, "size", 12), 8)

def txt_h(draw, text, font):
    try:
        b = draw.textbbox((0, 0), text, font=font)
        return b[3] - b[1]
    except Exception:
        return max(getattr(font, "size", 12), 8) + 4

def shadow_text(draw, xy, text, font, fill=(255,255,255), shadow=(0,0,0), off=2):
    x, y = xy
    for dx in [-off, 0, off]:
        for dy in [-off, 0, off]:
            if dx or dy:
                draw.text((x+dx, y+dy), text, font=font, fill=shadow)
    draw.text((x, y), text, font=font, fill=fill)

def centre_shadow(draw, text, font, y, fill=(255,255,255)):
    x = max(20, (W - txt_w(draw, text, font)) // 2)
    shadow_text(draw, (x, y), text, font, fill=fill)

def wrap_text(draw, text, font, max_w):
    if not text.strip():
        return []
    words, lines, cur = text.split(), [], ""
    for word in words:
        test = (cur + " " + word).strip()
        if txt_w(draw, test, font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [text]


# ===========================================================================
# Draw overlay
# ===========================================================================
def draw_overlay(base_arr, topic, caption_text, broll_frame=None):
    img  = Image.fromarray(base_arr.astype(np.uint8), "RGB")
    draw = ImageDraw.Draw(img)

    f_channel  = load_font(50)
    f_breaking = load_font(36)
    f_topic    = load_font(42)
    f_cap      = load_font(52, tamil=True)
    f_ad       = load_font(48)
    f_ad2      = load_font(34)

    # ── Top panel: B-roll frame ──────────────────────────────
    if broll_frame is not None:
        broll_img = Image.fromarray(broll_frame.astype(np.uint8), "RGB")
        broll_img = ImageEnhance.Brightness(broll_img).enhance(0.70)
        img.paste(broll_img, (0, 0))
    else:
        draw.rectangle([0, 0, W, TOP_PANEL_H], fill=(5, 15, 70))

    # ── Channel name bar overlay ─────────────────────────────
    bar_ov = Image.new("RGBA", (W, HEADER_BAR_H), (5, 15, 70, 210))
    img_rgba = img.convert("RGBA")
    img_rgba.paste(bar_ov, (0, 0), bar_ov)
    img  = img_rgba.convert("RGB")
    draw = ImageDraw.Draw(img)

    shadow_text(draw, (24, 16),  CHANNEL,        f_channel,  fill=(255, 255, 255))
    shadow_text(draw, (24, 82),  "BREAKING NEWS", f_breaking, fill=(255, 60, 60))

    # Red border bottom of top panel
    draw.rectangle([0, TOP_PANEL_H - 6, W, TOP_PANEL_H], fill=(200, 20, 20))

    # ── Topic strip ──────────────────────────────────────────
    topic_y = TOP_PANEL_H
    draw.rectangle([0, topic_y, W, topic_y + TOPIC_STRIP_H], fill=(0, 0, 0, 220))
    draw.rectangle([0, topic_y, 8, topic_y + TOPIC_STRIP_H], fill=(255, 200, 0))
    ty = topic_y + 10
    for line in wrap_text(draw, topic[:90], f_topic, W - 40)[:2]:
        shadow_text(draw, (24, ty), line, f_topic, fill=(255, 215, 0))
        ty += 56

    # ── Lower third captions ─────────────────────────────────
    if caption_text and caption_text.strip():
        lt_top = H - FOOTER_H - LOWER_THIRD_H
        draw.rectangle([0, lt_top, 12, H - FOOTER_H], fill=(220, 20, 20))
        lt_bg = Image.new("RGBA", (W, LOWER_THIRD_H), (0, 0, 0, 200))
        img_rgba = img.convert("RGBA")
        img_rgba.paste(lt_bg, (0, lt_top), lt_bg)
        img  = img_rgba.convert("RGB")
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, lt_top, W, lt_top + 5], fill=(255, 200, 0))
        cap_lines = wrap_text(draw, caption_text, f_cap, W - 80)[:3]
        lh = txt_h(draw, "A", f_cap) + 14
        cy = lt_top + (LOWER_THIRD_H - len(cap_lines) * lh) // 2 + 5
        for line in cap_lines:
            centre_shadow(draw, line, f_cap, cy, fill=(255, 255, 255))
            cy += lh

    # ── Footer ───────────────────────────────────────────────
    ft = H - FOOTER_H
    draw.rectangle([0, ft, W, H],      fill=(175, 8, 8))
    draw.rectangle([0, ft, W, ft + 5], fill=(255, 215, 0))
    centre_shadow(draw, AD_LINE1, f_ad,  ft + 16, fill=(255, 255, 255))
    centre_shadow(draw, AD_LINE2, f_ad2, ft + 88, fill=(255, 230, 0))

    return np.array(img)


# ===========================================================================
# Composite anchor (lower 72%)
# ===========================================================================
def composite_anchor(bg_arr, anchor_frame):
    bg  = Image.fromarray(bg_arr.astype(np.uint8), "RGB")
    anc = Image.fromarray(anchor_frame.astype(np.uint8), "RGB")
    anc = anc.resize((W, ANCHOR_H), Image.LANCZOS)
    bg.paste(anc, (0, H - ANCHOR_H))
    return np.array(bg)


# ===========================================================================
# SadTalker
# ===========================================================================
def sadtalker_available():
    inf = os.path.join(SADTALKER_DIR, "inference.py")
    ok  = os.path.exists(inf)
    print(f"  [SadTalker] {inf} -> {ok}")
    return ok

def run_sadtalker(face_path, audio_path, output_dir):
    if not sadtalker_available(): return None
    if not face_path or not os.path.exists(face_path): return None
    wav_path = audio_path.rsplit(".", 1)[0] + "_16k_st.wav"
    conv = subprocess.run(["ffmpeg", "-y", "-i", audio_path, "-ar", "16000", "-ac", "1", wav_path],
                          capture_output=True, text=True, timeout=60)
    if conv.returncode != 0: return None
    os.makedirs(output_dir, exist_ok=True)
    cmd = [sys.executable, "inference.py",
           "--driven_audio", wav_path, "--source_image", face_path,
           "--result_dir", output_dir, "--cpu", "--preprocess", "full", "--size", "256"]
    print("  [SadTalker] Running...")
    try:
        proc = subprocess.run(cmd, cwd=SADTALKER_DIR, capture_output=True, text=True, timeout=3600)
        if proc.stdout: print("  [ST OUT]", proc.stdout[-800:])
        if proc.returncode != 0:
            if proc.stderr: print("  [ST ERR]", proc.stderr[-600:])
            return None
        mp4s = sorted(glob.glob(os.path.join(output_dir, "**/*.mp4"), recursive=True))
        return mp4s[-1] if mp4s else None
    except Exception as e:
        print(f"  [SadTalker] Exception: {e}")
        return None


# ===========================================================================
# Wav2Lip
# ===========================================================================
def wav2lip_available():
    ok = (os.path.exists(WAV2LIP_CHECKPOINT) and
          os.path.exists(os.path.join(WAV2LIP_DIR, "inference.py")))
    print(f"  [Wav2Lip] ckpt={os.path.exists(WAV2LIP_CHECKPOINT)}")
    return ok

def run_wav2lip(face_path, audio_path, output_path):
    if not wav2lip_available(): return False
    if not face_path or not os.path.exists(face_path): return False
    wav_path = audio_path.rsplit(".", 1)[0] + "_16k_wl.wav"
    conv = subprocess.run(["ffmpeg", "-y", "-i", audio_path, "-ar", "16000", "-ac", "1", wav_path],
                          capture_output=True, text=True, timeout=60)
    if conv.returncode != 0: return False
    cmd = [sys.executable, "inference.py",
           "--checkpoint_path", WAV2LIP_CHECKPOINT,
           "--face", face_path, "--audio", wav_path,
           "--outfile", output_path, "--resize_factor", "1", "--nosmooth"]
    print("  [Wav2Lip] Running...")
    try:
        proc = subprocess.run(cmd, cwd=WAV2LIP_DIR, capture_output=True, text=True, timeout=1800)
        if proc.stdout: print("  [WL OUT]", proc.stdout[-600:])
        if proc.returncode != 0:
            if proc.stderr: print("  [WL ERR]", proc.stderr[-400:])
            return False
        return os.path.exists(output_path) and os.path.getsize(output_path) > 10_000
    except Exception as e:
        print(f"  [Wav2Lip] Exception: {e}")
        return False


# ===========================================================================
# Helpers
# ===========================================================================
def extract_spoken(script_text):
    spoken, skip = [], False
    skip_kw = ["HASHTAGS", "CAPTION", "FORMAT", "RULES", "TAGS"]
    for line in script_text.split("\n"):
        line = line.strip()
        if not line: continue
        if any(k in line.upper() for k in skip_kw): skip = True; continue
        if line.startswith(("HOOK", "STORY", "CTA", "TRUTH")): skip = False; continue
        if skip or line.startswith(("[", "---", "#")): continue
        if not line.isupper(): spoken.append(line)
    return " ".join(spoken)

def split_captions(text, n):
    words = text.split()
    if not words: return [""] * n
    chunk = max(1, len(words) // n)
    segs  = []
    for i in range(n):
        s = i * chunk
        e = s + chunk if i < n - 1 else len(words)
        segs.append(" ".join(words[s:e]))
    return segs


# ===========================================================================
# Build one video
# ===========================================================================
def build_video(audio_path, spoken_text, topic, output_path, anchor_face,
                broll_segments=None):
    audio    = AudioFileClip(audio_path).volumex(VOLUME_BOOST)
    duration = audio.duration
    print(f"  Duration: {duration:.1f}s  |  Volume: {VOLUME_BOOST}x")

    n_segs   = max(1, int(duration / 4))
    segments = split_captions(spoken_text or topic, n_segs)
    seg_dur  = duration / n_segs
    bg_arr   = make_bg()

    # SadTalker
    st_dir      = f"/tmp/st_{os.path.splitext(os.path.basename(output_path))[0]}"
    st_mp4      = run_sadtalker(anchor_face, audio_path, st_dir)
    anchor_clip = None
    method      = "static"

    if st_mp4:
        try:
            anchor_clip = VideoFileClip(st_mp4)
            if anchor_clip.duration < duration - 0.5:
                loops = int(duration / anchor_clip.duration) + 2
                anchor_clip = concatenate_videoclips([anchor_clip] * loops)
            anchor_clip = anchor_clip.subclip(0, duration)
            method = "sadtalker"
        except Exception as e:
            print(f"  [SadTalker] Clip error: {e}")
            anchor_clip = None

    # Wav2Lip
    if anchor_clip is None:
        print("  SadTalker failed → Wav2Lip...")
        wl_out = output_path.replace(".mp4", "_wl_raw.mp4")
        if run_wav2lip(anchor_face, audio_path, wl_out):
            try:
                raw = VideoFileClip(wl_out)
                if raw.duration < duration - 0.5:
                    loops = int(duration / raw.duration) + 2
                    raw   = concatenate_videoclips([raw] * loops)
                anchor_clip = raw.subclip(0, duration)
                method = "wav2lip"
                print(f"  [Wav2Lip] Clip: {anchor_clip.w}x{anchor_clip.h}")
            except Exception as e:
                print(f"  [Wav2Lip] Clip error: {e}")
                anchor_clip = None

    # Static fallback
    static_arr = None
    if anchor_clip is None and anchor_face and os.path.exists(anchor_face):
        print("  Both failed → static")
        static_arr = np.array(Image.open(anchor_face).convert("RGB"))

    broll_count = len(broll_segments) if broll_segments else 0
    print(f"  Method: {method} | BRoll segments: {broll_count}")

    def make_frame(t):
        try:
            frame = bg_arr.copy()

            # Anchor
            if anchor_clip is not None:
                anc_f = anchor_clip.get_frame(min(t, anchor_clip.duration - 0.01))
                frame = composite_anchor(frame, anc_f)
            elif static_arr is not None:
                frame = composite_anchor(frame, static_arr)

            # B-roll frame for this timestamp
            broll_f = get_broll_frame(broll_segments, t) if broll_segments else None

            seg_idx = min(int(t / seg_dur), n_segs - 1)
            return draw_overlay(frame, topic, segments[seg_idx], broll_f)
        except Exception as e:
            print(f"  make_frame err t={t:.1f}: {e}")
            return draw_overlay(bg_arr.copy(), topic, "", None)

    clip  = VideoClip(make_frame, duration=duration)
    final = clip.set_audio(audio)
    print(f"  Writing: {output_path}")
    final.write_videofile(
        output_path, fps=FPS, codec="libx264",
        audio_codec="aac", logger="bar",
        threads=2, preset="ultrafast"
    )
    audio.close()
    final.close()
    if anchor_clip: anchor_clip.close()

    for tmp in [
        output_path.replace(".mp4", "_wl_raw.mp4"),
        audio_path.rsplit(".", 1)[0] + "_16k_st.wav",
        audio_path.rsplit(".", 1)[0] + "_16k_wl.wav",
    ]:
        if os.path.exists(tmp):
            try: os.remove(tmp)
            except: pass

    if os.path.exists(output_path):
        sz = os.path.getsize(output_path) / 1024 / 1024
        print(f"  Done: {sz:.1f} MB  [{method}]")
        return True
    return False


# ===========================================================================
# Entry point
# ===========================================================================
def main():
    print("=" * 65)
    print("Tamil News Video Creator v17")
    print("Wav2Lip | Multi-clip B-roll cuts every 8s | Smart Tamil query")
    print("=" * 65)
    print(f"Time         : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Anchor       : {SUPPLIED_ANCHOR} -> {os.path.exists(SUPPLIED_ANCHOR)}")
    print(f"SadTalker    : {SADTALKER_DIR} -> {os.path.exists(os.path.join(SADTALKER_DIR,'inference.py'))}")
    print(f"Wav2Lip ckpt : {WAV2LIP_CHECKPOINT} -> {os.path.exists(WAV2LIP_CHECKPOINT)}")
    print(f"Volume boost : {VOLUME_BOOST}x")
    print(f"Pexels key   : {'SET' if PEXELS_API_KEY else 'NOT SET'}")
    print(f"B-roll cut   : every {BROLL_CUT_EVERY}s  |  top panel {W}x{TOP_PANEL_H}px")

    os.makedirs(VIDEO_DIR,  exist_ok=True)
    os.makedirs(ASSETS_DIR, exist_ok=True)

    try:
        with open(SCRIPTS_FILE, "r", encoding="utf-8") as f:
            scripts_data = json.load(f)["scripts"]
    except FileNotFoundError:
        print(f"ERROR: {SCRIPTS_FILE} not found"); sys.exit(1)

    try:
        with open(os.path.join(AUDIO_DIR, "manifest.json"), "r") as f:
            audio_files = json.load(f)["audio_files"]
    except FileNotFoundError:
        print("ERROR: audio/manifest.json not found"); sys.exit(1)

    print(f"\nScripts: {len(scripts_data)} | Audio: {len(audio_files)}")

    anchor_face = SUPPLIED_ANCHOR if os.path.exists(SUPPLIED_ANCHOR) else None
    if not anchor_face:
        print("WARNING: anchor_face_supplied.png not found!")

    created = []

    for i, (script_data, audio_data) in enumerate(zip(scripts_data, audio_files), 1):
        topic       = script_data.get("topic", f"News {i}")
        script_text = script_data.get("script", "")
        print(f"\n{'='*65}")
        print(f"Video {i}/{len(scripts_data)}: {topic[:60]}")
        print(f"{'='*65}")

        audio_path = audio_data.get("audio_file", "")
        if not os.path.exists(audio_path):
            print(f"  SKIP: audio missing: {audio_path}"); continue

        # Get audio duration
        try:
            tmp_a    = AudioFileClip(audio_path)
            duration = tmp_a.duration
            tmp_a.close()
        except Exception:
            duration = 60.0

        # How many clips we need: 1 per BROLL_CUT_EVERY seconds + 1 buffer
        clips_needed = max(3, int(duration / BROLL_CUT_EVERY) + 2)

        # Download multiple B-roll clips
        broll_paths = fetch_broll_videos(topic, script_text, count=clips_needed)

        broll_segments = None
        broll_clip_objects = []
        if broll_paths:
            result = prepare_broll_clips(broll_paths, duration)
            if result:
                broll_segments, broll_clip_objects = result

        spoken      = extract_spoken(script_text) or topic
        ts          = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(VIDEO_DIR, f"reel_{i}_{ts}.mp4")

        try:
            ok = build_video(audio_path, spoken, topic, output_path,
                             anchor_face, broll_segments)
            if ok:
                sz = os.path.getsize(output_path) / 1024 / 1024
                created.append({
                    "topic":      topic,
                    "video_file": output_path,
                    "size_mb":    round(sz, 1),
                    "method":     "sadtalker/wav2lip",
                })
            else:
                print(f"  FAILED: {topic}")
        except Exception as e:
            import traceback
            print(f"  EXCEPTION: {e}")
            traceback.print_exc()
        finally:
            # Close all broll clip objects
            for c in broll_clip_objects:
                try: c.close()
                except: pass
            # Delete temp files
            for p in broll_paths:
                if os.path.exists(p):
                    try: os.remove(p)
                    except: pass

    with open(os.path.join(VIDEO_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({
            "videos":     created,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "count":      len(created),
        }, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*65}")
    print(f"DONE: {len(created)}/{len(scripts_data)} videos → {VIDEO_DIR}")
    if not created:
        print("ZERO videos — check logs above"); sys.exit(1)


if __name__ == "__main__":
    main()
