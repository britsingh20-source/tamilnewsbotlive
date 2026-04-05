"""
STEP 4: Tamil News Video Creator (v12)
=======================================
Pipeline: Pollinations.ai BG + Wav2Lip talking anchor

What's new in v12:
  - Pollinations.ai generates FREE AI images relevant to each news topic
    (no API key needed, works on GitHub Actions CPU)
  - FIX: WAV2LIP_CHECKPOINT now correctly points to wav2lip_gan.pth
  - Female anchor (anchor_face_supplied.png) lip-synced to audio
  - Background = AI-generated news-relevant image (full 1080x1920)
  - Header = relevant smaller image thumbnail in top bar
  - Anchor overlay = Wav2Lip talking head placed in lower-centre
  - Tamil captions in middle, footer ad at bottom
"""

import json, os, io, sys, time, subprocess, requests, numpy as np, re, urllib.parse
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

try:
    from moviepy.editor import (VideoClip, AudioFileClip,
                                 VideoFileClip, concatenate_videoclips)
except ImportError:
    print("ERROR: moviepy not installed. Run: pip install moviepy")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPTS_DIR         = os.path.dirname(__file__)
SCRIPTS_FILE        = os.path.join(SCRIPTS_DIR, "../output/scripts.json")
AUDIO_DIR           = os.path.join(SCRIPTS_DIR, "../output/audio")
VIDEO_DIR           = os.path.join(SCRIPTS_DIR, "../output/videos")
ASSETS_DIR          = os.path.join(SCRIPTS_DIR, "../assets")
SUPPLIED_ANCHOR     = os.path.join(SCRIPTS_DIR, "anchor_face_supplied.png")

W, H   = 1080, 1920
FPS    = 25

AD_LINE1 = "Coimbatore Veedu Builders"
AD_LINE2 = "Contact: 8111024877"
CHANNEL  = "Tamil News Live"

PEXELS_KEY  = os.environ.get("PEXELS_API_KEY", "")
PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY", "")

# Wav2Lip — FIX: use wav2lip_gan.pth (matches what workflow downloads)
WAV2LIP_DIR        = os.environ.get("WAV2LIP_DIR", "/tmp/Wav2Lip")
WAV2LIP_CHECKPOINT = os.path.join(WAV2LIP_DIR, "checkpoints/wav2lip_gan.pth")

HEADER_H      = 170
FOOTER_H      = 160
CAPTION_PAD   = 30


# ===========================================================================
# Robust HTTP helper
# ===========================================================================
def _get(url, retries=3, **kwargs):
    for i in range(retries):
        try:
            r = requests.get(url, timeout=kwargs.pop("timeout", 20), **kwargs)
            if r.status_code < 500:
                return r
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(2 ** i)
    return None


# ===========================================================================
# Pollinations.ai — FREE AI image generation (no API key needed)
# ===========================================================================
def pollinations_image(prompt, width=1080, height=1920, seed=42, cache_path=None):
    """
    Generate an AI image from Pollinations.ai (completely free, no signup).
    Returns PIL Image or None on failure.
    """
    if cache_path and os.path.exists(cache_path) and os.path.getsize(cache_path) > 5000:
        try:
            print(f"  [Pollinations] Using cached: {cache_path}")
            return Image.open(cache_path).convert("RGB")
        except Exception:
            pass

    # Enhance prompt for news imagery
    full_prompt = (
        f"{prompt}, Tamil Nadu India, news broadcast, professional photography, "
        f"cinematic lighting, high quality, 4k"
    )
    encoded = urllib.parse.quote(full_prompt)
    url = (f"https://image.pollinations.ai/prompt/{encoded}"
           f"?width={width}&height={height}&seed={seed}&nologo=true&model=flux")

    print(f"  [Pollinations] Generating: {prompt[:60]}...")
    try:
        r = _get(url, retries=3, timeout=60)
        if r and r.status_code == 200 and len(r.content) > 5000:
            img = Image.open(io.BytesIO(r.content)).convert("RGB")
            if cache_path:
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                img.save(cache_path, quality=90)
            print(f"  [Pollinations] Done: {img.size}")
            return img
        else:
            print(f"  [Pollinations] Bad response: {r.status_code if r else 'None'}")
    except Exception as e:
        print(f"  [Pollinations] Error: {e}")
    return None


# ===========================================================================
# Wav2Lip
# ===========================================================================
def wav2lip_available():
    ok = (os.path.exists(WAV2LIP_CHECKPOINT) and
          os.path.exists(os.path.join(WAV2LIP_DIR, "inference.py")))
    if not ok:
        print(f"  [Wav2Lip] NOT available")
        print(f"    checkpoint: {WAV2LIP_CHECKPOINT} -> {os.path.exists(WAV2LIP_CHECKPOINT)}")
        print(f"    inference:  {os.path.join(WAV2LIP_DIR,'inference.py')} -> {os.path.exists(os.path.join(WAV2LIP_DIR,'inference.py'))}")
    return ok


def run_wav2lip(face_path, audio_path, output_path):
    if not wav2lip_available():
        return False
    if not face_path or not os.path.exists(face_path):
        print(f"  [Wav2Lip] Face image missing: {face_path}")
        return False

    # Convert audio to 16kHz WAV (Wav2Lip requirement)
    wav_path = audio_path.rsplit(".", 1)[0] + "_16k.wav"
    conv = subprocess.run(
        ["ffmpeg", "-y", "-i", audio_path, "-ar", "16000", "-ac", "1", wav_path],
        capture_output=True, text=True, timeout=60
    )
    if conv.returncode != 0:
        print(f"  [Wav2Lip] ffmpeg audio convert failed: {conv.stderr[:200]}")
        return False

    cmd = [
        sys.executable, "inference.py",
        "--checkpoint_path", WAV2LIP_CHECKPOINT,
        "--face", face_path,
        "--audio", wav_path,
        "--outfile", output_path,
        "--resize_factor", "1",
        "--nosmooth",
    ]
    print(f"  [Wav2Lip] Running lip sync (CPU ~10-15 min)...")
    try:
        proc = subprocess.run(
            cmd, cwd=WAV2LIP_DIR,
            capture_output=True, text=True, timeout=1800
        )
        if proc.stdout: print("  [Wav2Lip OUT]", proc.stdout[-600:])
        if proc.returncode != 0:
            print(f"  [Wav2Lip ERR] rc={proc.returncode}")
            if proc.stderr: print(proc.stderr[-400:])
            return False
        if os.path.exists(output_path) and os.path.getsize(output_path) > 10_000:
            print(f"  [Wav2Lip] SUCCESS: {os.path.getsize(output_path)/1024/1024:.1f} MB")
            return True
        print("  [Wav2Lip] Output missing or too small")
        return False
    except subprocess.TimeoutExpired:
        print("  [Wav2Lip] TIMEOUT (30 min limit)")
        return False
    except Exception as e:
        print(f"  [Wav2Lip] Exception: {e}")
        return False


# ===========================================================================
# Font loading
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
    f = ImageFont.load_default()
    _font_cache[key] = f
    return f


# ===========================================================================
# Drawing helpers
# ===========================================================================
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
# Gradient fallback background
# ===========================================================================
def gradient_frame(t=0):
    p = int(8 * np.sin(t * 0.5))
    a = np.zeros((H, W, 3), dtype=np.uint8)
    ys = np.arange(H, dtype=np.float32) / H
    a[:, :, 0] = np.clip(15 + (ys * 25).astype(int) + p, 0, 255)[:, None]
    a[:, :, 1] = np.clip(10 + (ys * 12).astype(int),     0, 255)[:, None]
    a[:, :, 2] = np.clip(60 + (ys * 90).astype(int) + p, 0, 255)[:, None]
    return a


# ===========================================================================
# Draw news overlay (header + captions + footer)
# ===========================================================================
def draw_overlay(base_arr, topic, caption_text, header_img=None, is_lipsync=False):
    """
    Composite the news graphics on top of base_arr (numpy H×W×3).
    header_img: optional PIL Image for the header thumbnail.
    """
    img  = Image.fromarray(base_arr.astype(np.uint8), "RGB")
    draw = ImageDraw.Draw(img)

    # ---------- Fonts ----------
    f_channel  = load_font(52)
    f_breaking = load_font(36)
    f_topic    = load_font(44)
    f_cap      = load_font(56, tamil=True)
    f_ad       = load_font(50)
    f_ad2      = load_font(36)

    # ---------- Header bar ----------
    draw.rectangle([0, 0, W, HEADER_H], fill=(5, 15, 70, 230))
    draw.rectangle([0, HEADER_H - 6, W, HEADER_H], fill=(200, 20, 20))

    header_text_right = W - 30
    if header_img:
        # Paste header thumbnail on the right side of header
        hi_w, hi_h = header_img.size
        paste_y = (HEADER_H - hi_h) // 2
        try:
            img.paste(header_img, (W - hi_w - 10, paste_y))
            header_text_right = W - hi_w - 20
        except Exception:
            pass

    shadow_text(draw, (30, 14),  CHANNEL,       f_channel,  fill=(255, 255, 255))
    shadow_text(draw, (30, 100), "BREAKING NEWS", f_breaking, fill=(255, 70, 70))

    # ---------- Topic strip ----------
    topic_y = HEADER_H + 4
    draw.rectangle([0, topic_y, W, topic_y + 110], fill=(0, 0, 0, 200))
    ty = topic_y + 8
    for line in wrap_text(draw, topic[:90], f_topic, W - 60)[:2]:
        shadow_text(draw, (30, ty), line, f_topic, fill=(255, 215, 0))
        ty += 56

    # ---------- Tamil captions ----------
    if caption_text and caption_text.strip():
        cap_lines = wrap_text(draw, caption_text, f_cap, W - 80)[:4]
        lh = txt_h(draw, "A", f_cap) + 16
        total_h = len(cap_lines) * lh
        cy = (H - total_h) // 2 + 120  # slightly below centre
        pad = 22
        # Semi-transparent caption box
        box_img = Image.new("RGBA", (W - 40, total_h + pad * 2), (0, 0, 0, 175))
        img_rgba = img.convert("RGBA")
        img_rgba.paste(box_img, (20, cy - pad), box_img)
        img = img_rgba.convert("RGB")
        draw = ImageDraw.Draw(img)
        for line in cap_lines:
            centre_shadow(draw, line, f_cap, cy, fill=(255, 255, 255))
            cy += lh

    # ---------- Footer ad ----------
    ft = H - FOOTER_H
    draw.rectangle([0, ft, W, H],      fill=(175, 8, 8))
    draw.rectangle([0, ft, W, ft + 5], fill=(255, 215, 0))
    centre_shadow(draw, AD_LINE1, f_ad,  ft + 18, fill=(255, 255, 255))
    centre_shadow(draw, AD_LINE2, f_ad2, ft + 90, fill=(255, 230, 0))

    return np.array(img)


# ===========================================================================
# Composite: BG image + Wav2Lip anchor
# ===========================================================================
def composite_anchor_on_bg(bg_frame, wl_frame):
    """
    Place Wav2Lip talking head (wl_frame) on background (bg_frame).
    The anchor fills the lower 65% of the frame.
    """
    bg  = Image.fromarray(bg_frame.astype(np.uint8), "RGB")
    wl  = Image.fromarray(wl_frame.astype(np.uint8), "RGB")

    # Dim the background so anchor stands out
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 80))
    bg = Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")

    # Scale Wav2Lip output to fill anchor zone (lower 65% of frame)
    anchor_h = int(H * 0.70)
    anchor_w = W
    wl = wl.resize((anchor_w, anchor_h), Image.LANCZOS)

    # Paste anchor in lower portion
    anchor_y = H - anchor_h
    bg.paste(wl, (0, anchor_y))

    return np.array(bg)


# ===========================================================================
# Helpers
# ===========================================================================
def extract_spoken(script_text):
    spoken, skip = [], False
    skip_kw = ["HASHTAGS", "CAPTION", "FORMAT", "RULES", "TAGS"]
    for line in script_text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if any(k in line.upper() for k in skip_kw):
            skip = True
            continue
        if line.startswith(("HOOK", "STORY", "CTA", "TRUTH")):
            skip = False
            continue
        if skip or line.startswith(("[", "---", "#")):
            continue
        if not line.isupper():
            spoken.append(line)
    return " ".join(spoken)

def split_captions(text, n):
    words = text.split()
    if not words:
        return [""] * n
    chunk = max(1, len(words) // n)
    segs = []
    for i in range(n):
        s = i * chunk
        e = s + chunk if i < n - 1 else len(words)
        segs.append(" ".join(words[s:e]))
    return segs

def topic_to_prompt(topic):
    # Remove non-ASCII words (Tamil script) for image prompt
    words = [w for w in topic.split() if all(ord(c) < 128 for c in w) and len(w) > 2]
    return " ".join(words[:6]) if words else "Tamil Nadu India news breaking"


# ===========================================================================
# Main video builder
# ===========================================================================
def build_video(audio_path, spoken_text, topic, output_path,
                anchor_face, bg_image=None, header_img=None):
    """
    Build the final video:
      1. Try Wav2Lip lip sync on anchor_face
      2. Composite Wav2Lip output over bg_image (or gradient)
      3. Draw news overlay on each frame
      4. Write to output_path
    """
    audio    = AudioFileClip(audio_path)
    duration = audio.duration
    print(f"  Audio duration: {duration:.1f}s")

    # Caption segments (one every ~4 seconds)
    n_segs   = max(1, int(duration / 4))
    segments = split_captions(spoken_text or topic, n_segs)
    seg_dur  = duration / n_segs

    # Pre-load background image as numpy array
    if bg_image:
        bg_arr = np.array(bg_image.resize((W, H), Image.LANCZOS))
    else:
        bg_arr = gradient_frame(0)

    # Try Wav2Lip
    wl_out = output_path.replace(".mp4", "_wl_raw.mp4")
    wl_ok  = run_wav2lip(anchor_face, audio_path, wl_out)
    wl_clip = None

    if wl_ok:
        try:
            raw = VideoFileClip(wl_out)
            print(f"  [Wav2Lip clip] {raw.w}x{raw.h}, {raw.duration:.1f}s")
            # Loop if shorter than audio
            if raw.duration < duration - 0.5:
                loops = int(duration / raw.duration) + 2
                raw   = concatenate_videoclips([raw] * loops)
            raw     = raw.subclip(0, duration)
            wl_clip = raw
            print(f"  [Wav2Lip clip] Loaded OK")
        except Exception as e:
            print(f"  [Wav2Lip clip] Load error: {e}")
            wl_clip = None

    def make_frame(t):
        try:
            # 1. Get background frame
            if wl_clip is not None:
                wl_frame = wl_clip.get_frame(min(t, wl_clip.duration - 0.01))
                frame    = composite_anchor_on_bg(bg_arr, wl_frame)
            else:
                # No Wav2Lip → just use BG with static anchor overlay
                frame = bg_arr.copy()

            # 2. Determine caption for this timestamp
            seg_idx     = min(int(t / seg_dur), n_segs - 1)
            caption_now = segments[seg_idx]

            # 3. Draw header + captions + footer
            return draw_overlay(frame, topic, caption_now,
                                 header_img=header_img,
                                 is_lipsync=(wl_clip is not None))
        except Exception as e:
            print(f"  make_frame t={t:.1f} err: {e}")
            return draw_overlay(gradient_frame(t), topic, "",
                                 header_img=header_img)

    clip  = VideoClip(make_frame, duration=duration)
    final = clip.set_audio(audio)
    print(f"  Writing video: {output_path}")
    final.write_videofile(
        output_path, fps=FPS, codec="libx264",
        audio_codec="aac", logger="bar",
        threads=2, preset="ultrafast"
    )
    audio.close()
    final.close()
    if wl_clip:
        wl_clip.close()

    # Clean up temp Wav2Lip raw output
    if wl_ok and os.path.exists(wl_out):
        os.remove(wl_out)

    if os.path.exists(output_path):
        sz = os.path.getsize(output_path) / 1024 / 1024
        print(f"  Video ready: {sz:.1f} MB")
        return True
    print("  ERROR: output not found!")
    return False


# ===========================================================================
# Entry point
# ===========================================================================
def main():
    print("=" * 65)
    print("Tamil News Video Creator v12")
    print("Pipeline: Pollinations.ai BG + Wav2Lip Talking Anchor")
    print("=" * 65)
    print(f"Time           : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Anchor face    : {SUPPLIED_ANCHOR} -> exists={os.path.exists(SUPPLIED_ANCHOR)}")
    print(f"Wav2Lip ckpt   : {WAV2LIP_CHECKPOINT} -> exists={os.path.exists(WAV2LIP_CHECKPOINT)}")
    print(f"PEXELS         : {'SET' if PEXELS_KEY  else 'not set'}")
    print(f"PIXABAY        : {'SET' if PIXABAY_KEY else 'not set'}")

    os.makedirs(VIDEO_DIR,  exist_ok=True)
    os.makedirs(ASSETS_DIR, exist_ok=True)

    # ---------- Load scripts.json ----------
    try:
        with open(SCRIPTS_FILE, "r", encoding="utf-8") as f:
            scripts_data = json.load(f)["scripts"]
    except FileNotFoundError:
        print(f"ERROR: scripts.json not found at {SCRIPTS_FILE}")
        sys.exit(1)

    # ---------- Load audio manifest ----------
    try:
        with open(os.path.join(AUDIO_DIR, "manifest.json"), "r") as f:
            audio_files = json.load(f)["audio_files"]
    except FileNotFoundError:
        print("ERROR: audio/manifest.json not found")
        sys.exit(1)

    print(f"\nScripts: {len(scripts_data)} | Audio: {len(audio_files)}")

    # ---------- Anchor face ----------
    anchor_face = SUPPLIED_ANCHOR if os.path.exists(SUPPLIED_ANCHOR) else None
    if anchor_face:
        print(f"Using supplied anchor: {anchor_face}")
    else:
        print("WARNING: anchor_face_supplied.png not found — lip sync will be skipped!")

    created = []

    for i, (script_data, audio_data) in enumerate(zip(scripts_data, audio_files), 1):
        topic = script_data.get("topic", f"News {i}")
        print(f"\n{'='*65}")
        print(f"Video {i}/{len(scripts_data)}: {topic[:60]}")
        print(f"{'='*65}")

        audio_path = audio_data.get("audio_file", "")
        if not os.path.exists(audio_path):
            print(f"  SKIP: audio not found: {audio_path}")
            continue

        spoken  = extract_spoken(script_data.get("script", "")) or topic
        prompt  = topic_to_prompt(topic)
        seed    = i * 42  # different seed per video so images differ

        # ---------- Generate background image with Pollinations.ai ----------
        bg_cache = os.path.join(ASSETS_DIR, f"bg_pollinations_{i}.jpg")
        bg_image = pollinations_image(
            f"Tamil news broadcast background {prompt}",
            width=W, height=H, seed=seed, cache_path=bg_cache
        )
        if bg_image is None:
            print("  [BG] Pollinations failed — using gradient")

        # ---------- Generate header thumbnail ----------
        hdr_cache = os.path.join(ASSETS_DIR, f"hdr_pollinations_{i}.jpg")
        hdr_image = pollinations_image(
            f"News photo {prompt} Tamil Nadu India",
            width=400, height=150, seed=seed + 1, cache_path=hdr_cache
        )

        # ---------- Build video ----------
        ts          = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(VIDEO_DIR, f"reel_{i}_{ts}.mp4")

        try:
            ok = build_video(
                audio_path, spoken, topic, output_path,
                anchor_face = anchor_face,
                bg_image    = bg_image,
                header_img  = hdr_image,
            )
            if ok:
                sz = os.path.getsize(output_path) / 1024 / 1024
                created.append({
                    "topic":      topic,
                    "video_file": output_path,
                    "size_mb":    round(sz, 1),
                    "lipsync":    wav2lip_available() and anchor_face is not None,
                })
                print(f"  DONE: {sz:.1f} MB")
            else:
                print(f"  FAILED: {topic}")
        except Exception as e:
            import traceback
            print(f"  EXCEPTION: {e}")
            traceback.print_exc()

    # ---------- Write manifest ----------
    manifest_path = os.path.join(VIDEO_DIR, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "videos":     created,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "count":      len(created),
        }, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*65}")
    print(f"DONE: {len(created)}/{len(scripts_data)} videos written to {VIDEO_DIR}")
    if not created:
        print("ZERO videos — check logs above for errors")
        sys.exit(1)


if __name__ == "__main__":
    main()
