"""
STEP 4: Auto-Create Video with Animated Background (FREE)
- Generates beautiful animated gradient background using NumPy
- No downloads needed - works 100% on GitHub Actions
- Combines with Tamil voiceover audio
- Outputs 9:16 vertical video for Reels/Shorts
"""

import json
import os
import numpy as np
from datetime import datetime

SCRIPTS_FILE = os.path.join(os.path.dirname(__file__), "../output/scripts.json")
AUDIO_DIR    = os.path.join(os.path.dirname(__file__), "../output/audio")
VIDEO_DIR    = os.path.join(os.path.dirname(__file__), "../output/videos")

# Beautiful color themes for news channel backgrounds
COLOR_THEMES = [
    {"name": "red_gold",    "top": [180, 20, 20],   "bottom": [120, 80, 0]},
    {"name": "blue_purple", "top": [10, 30, 120],   "bottom": [80, 10, 100]},
    {"name": "green_teal",  "top": [10, 100, 60],   "bottom": [0, 60, 80]},
    {"name": "orange_red",  "top": [180, 80, 10],   "bottom": [140, 20, 20]},
    {"name": "purple_blue", "top": [80, 10, 140],   "bottom": [10, 40, 160]},
]

def make_gradient_frame(width, height, top_color, bottom_color, t, total_frames):
    """Create a single animated gradient frame"""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    shift = int(np.sin(t / total_frames * 2 * np.pi) * 30)
    for y in range(height):
        ratio = (y + shift) / height
        ratio = max(0.0, min(1.0, ratio))
        r = int(top_color[0] * (1 - ratio) + bottom_color[0] * ratio)
        g = int(top_color[1] * (1 - ratio) + bottom_color[1] * ratio)
        b = int(top_color[2] * (1 - ratio) + bottom_color[2] * ratio)
        frame[y, :] = [r, g, b]
    shimmer = int(np.sin(t / total_frames * 4 * np.pi + 1.5) * 15)
    shimmer_band_start = int((0.3 + 0.1 * np.sin(t / total_frames * np.pi)) * height)
    shimmer_band_end = shimmer_band_start + 80
    if 0 <= shimmer_band_start < height:
        end = min(shimmer_band_end, height)
        frame[shimmer_band_start:end, :] = np.clip(
            frame[shimmer_band_start:end, :].astype(int) + shimmer, 0, 255
        ).astype(np.uint8)
    return frame

def create_animated_video(audio_path, output_path, theme_index=0):
    """Create animated gradient background video with audio"""
    try:
        from moviepy.editor import AudioFileClip, VideoClip
        audio = AudioFileClip(audio_path)
        duration = audio.duration
        print(f"   Audio duration: {duration:.1f}s")
        theme = COLOR_THEMES[theme_index % len(COLOR_THEMES)]
        width, height = 1080, 1920
        fps = 24
        total_frames = int(duration * fps)
        print(f"   Generating animated {theme['name']} background ({total_frames} frames)...")
        top_color    = theme["top"]
        bottom_color = theme["bottom"]
        def make_frame(t):
            frame_num = int(t * fps)
            return make_gradient_frame(width, height, top_color, bottom_color, frame_num, total_frames)
        video = VideoClip(make_frame, duration=duration)
        final = video.set_audio(audio)
        final.write_videofile(
            output_path,
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            logger=None,
            threads=2,
            preset="ultrafast"
        )
        audio.close()
        final.close()
        print(f"   Done!")
        return True
    except Exception as e:
        print(f"   Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("Creating Tamil News Videos with Animated Backgrounds...")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    os.makedirs(VIDEO_DIR, exist_ok=True)
    try:
        with open(SCRIPTS_FILE, "r", encoding="utf-8") as f:
            scripts_data = json.load(f)["scripts"]
    except FileNotFoundError:
        print("scripts.json not found!")
        return
    try:
        with open(os.path.join(AUDIO_DIR, "manifest.json"), "r") as f:
            audio_files = json.load(f)["audio_files"]
    except FileNotFoundError:
        print("Audio manifest not found!")
        return
    print(f"Found {len(scripts_data)} scripts and {len(audio_files)} audio files\n")
    created_videos = []
    for i, (script_data, audio_data) in enumerate(zip(scripts_data, audio_files), 1):
        topic = script_data['topic'][:50]
        print(f"Video {i}/{len(scripts_data)}: {topic}...")
        timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(VIDEO_DIR, f"reel_{i}_{timestamp}.mp4")
        audio_path  = audio_data["audio_file"]
        if not os.path.exists(audio_path):
            print(f"   Audio missing: {audio_path}")
            continue
        success = create_animated_video(audio_path, output_path, theme_index=i - 1)
        if success and os.path.exists(output_path):
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            theme_name = COLOR_THEMES[(i-1) % len(COLOR_THEMES)]["name"]
            created_videos.append({
                "topic": script_data["topic"],
                "video_file": output_path,
                "size_mb": round(size_mb, 1),
                "theme": theme_name
            })
            print(f"   {size_mb:.1f} MB ({theme_name} theme)\n")
        else:
            print(f"   Failed\n")
    with open(os.path.join(VIDEO_DIR, "manifest.json"), "w") as f:
        json.dump({"videos": created_videos, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")}, f, indent=2)
    print(f"{len(created_videos)} videos ready!")
    print(f"Folder: {VIDEO_DIR}")

if __name__ == "__main__":
    main()
