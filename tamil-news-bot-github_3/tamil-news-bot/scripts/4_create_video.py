"""
STEP 4: Tamil News Video Creator (v14)
=======================================
- SadTalker: lip sync + head & body movements
- Wav2Lip fallback
- Audio volume boosted 2x
- Captions in lower third (above footer)
- Dark navy background
"""

import json, os, sys, time, subprocess, glob, numpy as np
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

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

VOLUME_BOOST = 2.0   # multiply audio volume

SADTALKER_DIR      = os.environ.get("SADTALKER_DIR", "/tmp/SadTalker")
WAV2LIP_DIR        = os.environ.get("WAV2LIP_DIR", "/tmp/Wav2Lip")
WAV2LIP_CHECKPOINT = os.path.join(WAV2LIP_DIR, "checkpoints/wav2lip_gan.pth")

HEADER_H       = 170
FOOTER_H       = 160
LOWER_THIRD_H  = 240   # caption bar height above footer


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
# News overlay
# ===========================================================================
def draw_overlay(base_arr, topic, caption_text):
    img  = Image.fromarray(base_arr.astype(np.uint8), "RGB")
    draw = ImageDraw.Draw(img)

    f_channel  = load_font(52)
    f_breaking = load_font(38)
    f_topic    = load_font(44)
    f_cap      = load_font(52, tamil=True)
    f_ad       = load_font(48)
    f_ad2      = load_font(34)

    # ── Header bar ──────────────────────────────────────────
    draw.rectangle([0, 0, W, HEADER_H], fill=(5, 15, 70))
    draw.rectangle([0, HEADER_H - 6, W, HEADER_H], fill=(200, 20, 20))
    shadow_text(draw, (30, 14),  CHANNEL,        f_channel,  fill=(255, 255, 255))
    shadow_text(draw, (30, 100), "BREAKING NEWS", f_breaking, fill=(255, 60, 60))

    # ── Topic strip ─────────────────────────────────────────
    topic_y = HEADER_H + 4
    draw.rectangle([0, topic_y, W, topic_y + 120], fill=(0, 0, 0, 210))
    ty = topic_y + 10
    for line in wrap_text(draw, topic[:90], f_topic, W - 60)[:2]:
        shadow_text(draw, (30, ty), line, f_topic, fill=(255, 215, 0))
        ty += 58

    # ── LOWER THIRD captions (above footer) ─────────────────
    if caption_text and caption_text.strip():
        lt_top = H - FOOTER_H - LOWER_THIRD_H   # y start of lower third

        # Red left accent bar
        draw.rectangle([0, lt_top, 12, H - FOOTER_H], fill=(220, 20, 20))

        # Semi-transparent dark background for lower third
        lt_bg = Image.new("RGBA", (W, LOWER_THIRD_H), (0, 0, 0, 200))
        img_rgba = img.convert("RGBA")
        img_rgba.paste(lt_bg, (0, lt_top), lt_bg)
        img  = img_rgba.convert("RGB")
        draw = ImageDraw.Draw(img)

        # Thin gold top border on lower third
        draw.rectangle([0, lt_top, W, lt_top + 5], fill=(255, 200, 0))

        cap_lines = wrap_text(draw, caption_text, f_cap, W - 80)[:3]
        lh        = txt_h(draw, "A", f_cap) + 14
        total_h   = len(cap_lines) * lh
        cy        = lt_top + (LOWER_THIRD_H - total_h) // 2 + 5

        for line in cap_lines:
            centre_shadow(draw, line, f_cap, cy, fill=(255, 255, 255))
            cy += lh

    # ── Footer ad ────────────────────────────────────────────
    ft = H - FOOTER_H
    draw.rectangle([0, ft, W, H],      fill=(175, 8, 8))
    draw.rectangle([0, ft, W, ft + 5], fill=(255, 215, 0))
    centre_shadow(draw, AD_LINE1, f_ad,  ft + 16, fill=(255, 255, 255))
    centre_shadow(draw, AD_LINE2, f_ad2, ft + 88, fill=(255, 230, 0))

    return np.array(img)


# ===========================================================================
# Composite anchor onto background (lower 70%)
# ===========================================================================
def composite_anchor(bg_arr, anchor_frame):
    bg  = Image.fromarray(bg_arr.astype(np.uint8), "RGB")
    anc = Image.fromarray(anchor_frame.astype(np.uint8), "RGB")
    anc_h = int(H * 0.72)
    anc   = anc.resize((W, anc_h), Image.LANCZOS)
    bg.paste(anc, (0, H - anc_h))
    return np.array(bg)


# ===========================================================================
# SadTalker — lip sync + head & body movement
# ===========================================================================
def sadtalker_available():
    inf = os.path.join(SADTALKER_DIR, "inference.py")
    ok  = os.path.exists(inf)
    print(f"  [SadTalker] {inf} -> {ok}")
    return ok

def run_sadtalker(face_path, audio_path, output_dir):
    if not sadtalker_available():
        return None
    if not face_path or not os.path.exists(face_path):
        print(f"  [SadTalker] Face missing: {face_path}")
        return None

    wav_path = audio_path.rsplit(".", 1)[0] + "_16k_st.wav"
    conv = subprocess.run(
        ["ffmpeg", "-y", "-i", audio_path, "-ar", "16000", "-ac", "1", wav_path],
        capture_output=True, text=True, timeout=60
    )
    if conv.returncode != 0:
        print(f"  [SadTalker] ffmpeg failed: {conv.stderr[:200]}")
        return None

    os.makedirs(output_dir, exist_ok=True)

    cmd = [
        sys.executable, "inference.py",
        "--driven_audio", wav_path,
        "--source_image", face_path,
        "--result_dir",   output_dir,
        "--cpu",
        "--preprocess",   "full",    # full body movement
        "--size",         "256",
        # NO --still → enables natural head & body movement
    ]
    print(f"  [SadTalker] Running lip sync + head/body movement (CPU)...")
    try:
        proc = subprocess.run(
            cmd, cwd=SADTALKER_DIR,
            capture_output=True, text=True, timeout=3600
        )
        if proc.stdout: print("  [ST OUT]", proc.stdout[-800:])
        if proc.returncode != 0:
            print(f"  [SadTalker] rc={proc.returncode}")
            if proc.stderr: print("  [ST ERR]", proc.stderr[-600:])
            return None
        mp4s = sorted(glob.glob(os.path.join(output_dir, "**/*.mp4"), recursive=True))
        if mp4s:
            sz = os.path.getsize(mp4s[-1]) / 1024 / 1024
            print(f"  [SadTalker] SUCCESS: {mp4s[-1]} ({sz:.1f} MB)")
            return mp4s[-1]
        print("  [SadTalker] No output mp4 found")
        return None
    except subprocess.TimeoutExpired:
        print("  [SadTalker] TIMEOUT (60 min)")
        return None
    except Exception as e:
        print(f"  [SadTalker] Exception: {e}")
        return None


# ===========================================================================
# Wav2Lip fallback — lip sync only
# ===========================================================================
def wav2lip_available():
    ok = (os.path.exists(WAV2LIP_CHECKPOINT) and
          os.path.exists(os.path.join(WAV2LIP_DIR, "inference.py")))
    print(f"  [Wav2Lip] ckpt={os.path.exists(WAV2LIP_CHECKPOINT)} inference={os.path.exists(os.path.join(WAV2LIP_DIR,'inference.py'))}")
    return ok

def run_wav2lip(face_path, audio_path, output_path):
    if not wav2lip_available():
        return False
    if not face_path or not os.path.exists(face_path):
        return False
    wav_path = audio_path.rsplit(".", 1)[0] + "_16k_wl.wav"
    conv = subprocess.run(
        ["ffmpeg", "-y", "-i", audio_path, "-ar", "16000", "-ac", "1", wav_path],
        capture_output=True, text=True, timeout=60
    )
    if conv.returncode != 0:
        print(f"  [Wav2Lip] ffmpeg failed: {conv.stderr[:200]}")
        return False
    cmd = [
        sys.executable, "inference.py",
        "--checkpoint_path", WAV2LIP_CHECKPOINT,
        "--face",    face_path,
        "--audio",   wav_path,
        "--outfile", output_path,
        "--resize_factor", "1",
        "--nosmooth",
    ]
    print(f"  [Wav2Lip] Running lip sync (CPU)...")
    try:
        proc = subprocess.run(
            cmd, cwd=WAV2LIP_DIR,
            capture_output=True, text=True, timeout=1800
        )
        if proc.stdout: print("  [WL OUT]", proc.stdout[-600:])
        if proc.returncode != 0:
            print(f"  [Wav2Lip] rc={proc.returncode}")
            if proc.stderr: print("  [WL ERR]", proc.stderr[-400:])
            return False
        if os.path.exists(output_path) and os.path.getsize(output_path) > 10_000:
            print(f"  [Wav2Lip] SUCCESS: {os.path.getsize(output_path)/1024/1024:.1f} MB")
            return True
        return False
    except subprocess.TimeoutExpired:
        print("  [Wav2Lip] TIMEOUT")
        return False
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
        if any(k in line.upper() for k in skip_kw):
            skip = True; continue
        if line.startswith(("HOOK", "STORY", "CTA", "TRUTH")):
            skip = False; continue
        if skip or line.startswith(("[", "---", "#")): continue
        if not line.isupper():
            spoken.append(line)
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
def build_video(audio_path, spoken_text, topic, output_path, anchor_face):
    # ── Load & boost audio ──────────────────────────────────
    audio    = AudioFileClip(audio_path).volumex(VOLUME_BOOST)
    duration = audio.duration
    print(f"  Duration: {duration:.1f}s  |  Volume: {VOLUME_BOOST}x")

    n_segs   = max(1, int(duration / 4))
    segments = split_captions(spoken_text or topic, n_segs)
    seg_dur  = duration / n_segs

    bg_arr = make_bg()

    # ── Try SadTalker first ──────────────────────────────────
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
            print(f"  [SadTalker] Clip: {anchor_clip.w}x{anchor_clip.h}")
        except Exception as e:
            print(f"  [SadTalker] Clip load error: {e}")
            anchor_clip = None

    # ── Fallback: Wav2Lip ────────────────────────────────────
    if anchor_clip is None:
        print("  SadTalker failed → trying Wav2Lip...")
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
                print(f"  [Wav2Lip] Clip load error: {e}")
                anchor_clip = None

    # ── Fallback: static image ───────────────────────────────
    static_arr = None
    if anchor_clip is None and anchor_face and os.path.exists(anchor_face):
        print("  Both failed → static image")
        static_arr = np.array(Image.open(anchor_face).convert("RGB"))

    print(f"  Method: {method}")

    def make_frame(t):
        try:
            if anchor_clip is not None:
                anc_frame = anchor_clip.get_frame(min(t, anchor_clip.duration - 0.01))
                frame     = composite_anchor(bg_arr, anc_frame)
            elif static_arr is not None:
                frame = composite_anchor(bg_arr, static_arr)
            else:
                frame = bg_arr.copy()

            seg_idx = min(int(t / seg_dur), n_segs - 1)
            return draw_overlay(frame, topic, segments[seg_idx])
        except Exception as e:
            print(f"  make_frame err t={t:.1f}: {e}")
            return draw_overlay(bg_arr.copy(), topic, "")

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

    # Cleanup temp files
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
    print("  ERROR: output not found!")
    return False


# ===========================================================================
# Entry point
# ===========================================================================
def main():
    print("=" * 65)
    print("Tamil News Video Creator v14")
    print("SadTalker lip sync + head/body movement | Volume 2x | Lower third")
    print("=" * 65)
    print(f"Time         : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Anchor       : {SUPPLIED_ANCHOR} -> {os.path.exists(SUPPLIED_ANCHOR)}")
    print(f"SadTalker    : {SADTALKER_DIR} -> {os.path.exists(os.path.join(SADTALKER_DIR,'inference.py'))}")
    print(f"Wav2Lip ckpt : {WAV2LIP_CHECKPOINT} -> {os.path.exists(WAV2LIP_CHECKPOINT)}")
    print(f"Volume boost : {VOLUME_BOOST}x")

    os.makedirs(VIDEO_DIR,  exist_ok=True)
    os.makedirs(ASSETS_DIR, exist_ok=True)

    try:
        with open(SCRIPTS_FILE, "r", encoding="utf-8") as f:
            scripts_data = json.load(f)["scripts"]
    except FileNotFoundError:
        print(f"ERROR: {SCRIPTS_FILE} not found")
        sys.exit(1)

    try:
        with open(os.path.join(AUDIO_DIR, "manifest.json"), "r") as f:
            audio_files = json.load(f)["audio_files"]
    except FileNotFoundError:
        print("ERROR: audio/manifest.json not found")
        sys.exit(1)

    print(f"\nScripts: {len(scripts_data)} | Audio: {len(audio_files)}")

    anchor_face = SUPPLIED_ANCHOR if os.path.exists(SUPPLIED_ANCHOR) else None
    if not anchor_face:
        print("WARNING: anchor_face_supplied.png not found!")

    created = []

    for i, (script_data, audio_data) in enumerate(zip(scripts_data, audio_files), 1):
        topic = script_data.get("topic", f"News {i}")
        print(f"\n{'='*65}")
        print(f"Video {i}/{len(scripts_data)}: {topic[:60]}")
        print(f"{'='*65}")

        audio_path = audio_data.get("audio_file", "")
        if not os.path.exists(audio_path):
            print(f"  SKIP: audio missing: {audio_path}")
            continue

        spoken      = extract_spoken(script_data.get("script", "")) or topic
        ts          = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(VIDEO_DIR, f"reel_{i}_{ts}.mp4")

        try:
            ok = build_video(audio_path, spoken, topic, output_path, anchor_face)
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

    with open(os.path.join(VIDEO_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({
            "videos":     created,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "count":      len(created),
        }, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*65}")
    print(f"DONE: {len(created)}/{len(scripts_data)} videos → {VIDEO_DIR}")
    if not created:
        print("ZERO videos — check logs above")
        sys.exit(1)


if __name__ == "__main__":
    main()
