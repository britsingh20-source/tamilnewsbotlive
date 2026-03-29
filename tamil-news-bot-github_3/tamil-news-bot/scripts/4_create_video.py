"""
STEP 4: Auto-Create Video with Animated News Background (FREE)
- Creates professional animated dark background - no external dependencies
- Combines with Tamil voiceover audio
- Outputs 9:16 vertical video for Reels/Shorts
"""

import json
import os
import requests
import numpy as np
from datetime import datetime

SCRIPTS_FILE = os.path.join(os.path.dirname(__file__), "../output/scripts.json")
AUDIO_DIR    = os.path.join(os.path.dirname(__file__), "../output/audio")
VIDEO_DIR    = os.path.join(os.path.dirname(__file__), "../output/videos")
ASSETS_DIR   = os.path.join(os.path.dirname(__file__), "../assets")

FREE_VIDEO_URLS = [
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerEscapes.mp4",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/SubaruOutbackOnStreetAndDirt.mp4",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
]

def download_free_video(output_path, index=0):
    for i, url in enumerate(FREE_VIDEO_URLS):
        try:
            print(f"   Trying video source {i+1}/{len(FREE_VIDEO_URLS)}...")
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(url, stream=True, timeout=30, headers=headers)
            if r.status_code == 200:
                with open(output_path, "wb") as f:
                    downloaded = 0
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if downloaded > 5 * 1024 * 1024:
                            break
                size_kb = os.path.getsize(output_path) / 1024
                if size_kb > 100:
                    print(f"   Downloaded {size_kb:.0f} KB from source {i+1}")
                    return True
        except Exception as e:
            print(f"   Source {i+1} failed: {e}")
            continue
    print("   All video sources failed - using generated background")
    return False

def create_animated_background(output_path, duration):
    try:
        from moviepy.editor import VideoClip
        W, H = 1080, 1920
        FPS = 24

        def make_frame(t):
            frame = np.zeros((H, W, 3), dtype=np.uint8)
            for y in range(H):
                intensity = int(15 * np.sin(y / H * np.pi + t * 0.3))
                wave = int(20 * np.sin(t * 0.5))
                frame[y, :, 0] = max(0, min(255, 10 + intensity))
                frame[y, :, 1] = max(0, min(255, 20 + intensity + wave))
                frame[y, :, 2] = max(0, min(255, 60 + intensity * 2))
            frame[50:120, :] = [20, 80, 180]
            frame[H-120:H-50, :] = [180, 20, 20]
            return frame

        clip = VideoClip(make_frame, duration=duration)
        clip.write_videofile(output_path, fps=FPS, logger=None, threads=2)
        clip.close()
        print(f"   Created animated background: {duration:.1f}s")
        return True
    except Exception as e:
        print(f"   Animated background error: {e}")
        return False

def create_final_video(bg_path, audio_path, output_path):
    try:
        from moviepy.editor import VideoFileClip, AudioFileClip, ColorClip, concatenate_videoclips

        audio = AudioFileClip(audio_path)
        duration = audio.duration
        print(f"   Audio duration: {duration:.1f}s")

        bg_ok = os.path.exists(bg_path) and os.path.getsize(bg_path) > 50000
        if bg_ok:
            video = VideoFileClip(bg_path)
            if video.duration < duration:
                loops = int(duration / video.duration) + 2
                video = concatenate_videoclips([video] * loops)
            video = video.subclip(0, duration)
            video = video.resize(height=1920)
            if video.w > 1080:
                video = video.crop(x_center=video.w/2, width=1080)
            elif video.w < 1080:
                video = video.resize(width=1080)
        else:
            video = ColorClip(size=(1080, 1920), color=[10, 20, 60], duration=duration)

        final = video.set_audio(audio)
        final.write_videofile(
            output_path, fps=24, codec="libx264",
            audio_codec="aac", logger=None, threads=2, preset="ultrafast"
        )
        audio.close()
        final.close()
        size_mb = os.path.getsize(output_path) / (1024*1024)
        print(f"   Video created: {size_mb:.1f} MB")
        return True
    except Exception as e:
        print(f"   Final video error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("Creating Tamil News Videos...")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    os.makedirs(VIDEO_DIR, exist_ok=True)
    os.makedirs(ASSETS_DIR, exist_ok=True)

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
        print(f"Video {i}/{len(scripts_data)}: {script_data['topic'][:50]}...")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        bg_path     = os.path.join(ASSETS_DIR, f"bg_{i}.mp4")
        output_path = os.path.join(VIDEO_DIR,  f"reel_{i}_{timestamp}.mp4")

        got_bg = download_free_video(bg_path, index=i-1)
        if not got_bg:
            print("   Generating animated news background...")
            got_bg = create_animated_background(bg_path, duration=60)
        if not got_bg:
            from moviepy.editor import ColorClip
            clip = ColorClip(size=(1080,1920), color=[10,20,60], duration=60)
            clip.write_videofile(bg_path, fps=24, logger=None)
            clip.close()

        audio_path_file = audio_data["audio_file"]
        if not os.path.exists(audio_path_file):
            print(f"   Audio missing: {audio_path_file}")
            continue

        success = create_final_video(bg_path, audio_path_file, output_path)

        if success and os.path.exists(output_path):
            size_mb = os.path.getsize(output_path) / (1024*1024)
            created_videos.append({
                "topic": script_data["topic"],
                "video_file": output_path,
                "size_mb": round(size_mb, 1),
            })
            print(f"   Done! {size_mb:.1f} MB\n")
        else:
            print(f"   Failed\n")

    with open(os.path.join(VIDEO_DIR, "manifest.json"), "w") as f:
        json.dump({"videos": created_videos,
                   "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")}, f, indent=2)

    print(f"{len(created_videos)} videos ready!")
    print(f"Folder: {VIDEO_DIR}")

if __name__ == "__main__":
    main()
