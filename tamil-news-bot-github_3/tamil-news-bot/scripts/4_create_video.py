"""
STEP 4: Auto-Create Video with Captions (FREE)
- Downloads free stock video from Pixabay (no API key needed)
- Combines with Tamil voiceover audio
- Outputs 9:16 vertical video for Reels/Shorts
"""

import json
import os
import requests
from datetime import datetime

SCRIPTS_FILE = os.path.join(os.path.dirname(__file__), "../output/scripts.json")
AUDIO_DIR    = os.path.join(os.path.dirname(__file__), "../output/audio")
VIDEO_DIR    = os.path.join(os.path.dirname(__file__), "../output/videos")
ASSETS_DIR   = os.path.join(os.path.dirname(__file__), "../assets")

# Direct Pixabay MP4 links - no API key needed, always free
PIXABAY_VIDEOS = [
    "https://cdn.pixabay.com/video/2024/03/11/203933_large.mp4",
    "https://cdn.pixabay.com/video/2023/11/14/188848_large.mp4",
    "https://cdn.pixabay.com/video/2022/10/07/134017_large.mp4",
    "https://cdn.pixabay.com/video/2023/05/19/163998_large.mp4",
    "https://cdn.pixabay.com/video/2021/09/01/86178_large.mp4",
    "https://cdn.pixabay.com/video/2020/07/30/46236_large.mp4",
    "https://cdn.pixabay.com/video/2023/08/28/177368_large.mp4",
    "https://cdn.pixabay.com/video/2022/01/11/104324_large.mp4",
]

def download_pixabay_video(output_path, index=0):
    """Download a free Pixabay video - no API key needed"""
    tried = set()
    for attempt in range(len(PIXABAY_VIDEOS)):
        idx = (index + attempt) % len(PIXABAY_VIDEOS)
        if idx in tried:
            continue
        tried.add(idx)
        url = PIXABAY_VIDEOS[idx]
        try:
            print(f"   Downloading Pixabay video {idx+1}...")
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(url, stream=True, timeout=60, headers=headers)
            if r.status_code == 200:
                with open(output_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                size_kb = os.path.getsize(output_path) / 1024
                print(f"   Downloaded {size_kb:.0f} KB")
                if size_kb > 100:
                    return True
            print(f"   Status {r.status_code} - trying next...")
        except Exception as e:
            print(f"   Error: {e} - trying next...")
    print("   All Pixabay links failed - using color background")
    return False

def create_final_video(stock_path, audio_path, output_path):
    """Combine background video + audio using MoviePy"""
    try:
        from moviepy.editor import VideoFileClip, AudioFileClip, ColorClip, concatenate_videoclips

        audio = AudioFileClip(audio_path)
        audio_duration = audio.duration
        print(f"   Audio: {audio_duration:.1f}s")

        stock_ok = os.path.exists(stock_path) and os.path.getsize(stock_path) > 100000
        if stock_ok:
            print(f"   Loading stock video...")
            video = VideoFileClip(stock_path)
            if video.duration < audio_duration:
                loops = int(audio_duration / video.duration) + 2
                video = concatenate_videoclips([video] * loops)
            video = video.subclip(0, audio_duration)
            video = video.resize(height=1920)
            if video.w > 1080:
                video = video.crop(x_center=video.w / 2, width=1080)
            elif video.w < 1080:
                video = video.resize(width=1080)
        else:
            print(f"   Using color background")
            video = ColorClip(size=(1080, 1920), color=[15, 25, 60], duration=audio_duration)

        final = video.set_audio(audio)
        final.write_videofile(
            output_path,
            fps=24,
            codec="libx264",
            audio_codec="aac",
            logger=None,
            threads=2,
            preset="ultrafast"
        )
        audio.close()
        final.close()
        return True

    except Exception as e:
        print(f"   Video error: {e}")
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
        stock_path  = os.path.join(ASSETS_DIR, f"stock_{i}.mp4")
        output_path = os.path.join(VIDEO_DIR,  f"reel_{i}_{timestamp}.mp4")

        got_stock = download_pixabay_video(stock_path, index=i - 1)

        audio_path = audio_data["audio_file"]
        if not os.path.exists(audio_path):
            print(f"   Audio missing: {audio_path}")
            continue

        success = create_final_video(stock_path if got_stock else "", audio_path, output_path)

        if success and os.path.exists(output_path):
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            created_videos.append({
                "topic": script_data["topic"],
                "video_file": output_path,
                "size_mb": round(size_mb, 1),
                "has_stock_footage": got_stock
            })
            bg = "Pixabay stock" if got_stock else "color background"
            print(f"   Done! {size_mb:.1f} MB ({bg})\n")
        else:
            print(f"   Failed\n")

    with open(os.path.join(VIDEO_DIR, "manifest.json"), "w") as f:
        json.dump({"videos": created_videos, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")}, f, indent=2)

    print(f"{len(created_videos)} videos ready!")
    print(f"Folder: {VIDEO_DIR}")

if __name__ == "__main__":
    main()
