"""
STEP 4: Auto-Create Video with Captions (FREE)
- Downloads free stock video from Pexels API
- Combines with Tamil voiceover audio
- Outputs 9:16 vertical video for Reels/Shorts
"""

import json
import os
import requests
from datetime import datetime

SCRIPTS_FILE = os.path.join(os.path.dirname(__file__), "../output/scripts.json")
AUDIO_DIR = os.path.join(os.path.dirname(__file__), "../output/audio")
VIDEO_DIR = os.path.join(os.path.dirname(__file__), "../output/videos")
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "../assets")

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")

TOPIC_QUERIES = [
    "india city traffic",
    "india market street",
    "india crowd people",
    "nature landscape scenic",
    "city buildings skyline",
]

def download_pexels_video(output_path):
    """Try multiple search queries until one works"""
    if not PEXELS_API_KEY or PEXELS_API_KEY in ("skip", "YOUR_PEXELS_API_KEY_HERE"):
        print("   No Pexels key — using color background")
        return False

    headers = {"Authorization": PEXELS_API_KEY}

    for query in TOPIC_QUERIES:
        try:
            print(f"   Trying Pexels query: '{query}'...")
            resp = requests.get(
                "https://api.pexels.com/videos/search",
                params={"query": query, "per_page": 10, "orientation": "portrait", "size": "medium"},
                headers=headers,
                timeout=20
            )
            print(f"   Pexels status: {resp.status_code}")
            if resp.status_code != 200:
                print(f"   Pexels error response: {resp.text[:200]}")
                continue

            data = resp.json()
            videos = data.get("videos", [])
            print(f"   Found {len(videos)} videos")

            for video in videos:
                video_files = video.get("video_files", [])
                # Sort by width to get smallest workable size (faster download)
                portrait_files = [
                    f for f in video_files
                    if f.get("width", 0) <= 1080 and f.get("height", 0) >= 1000
                ]
                if not portrait_files:
                    # fallback to any file
                    portrait_files = sorted(video_files, key=lambda x: x.get("width", 9999))

                if not portrait_files:
                    continue

                video_url = portrait_files[0]["link"]
                print(f"   Downloading: {video_url[:80]}...")
                r = requests.get(video_url, stream=True, timeout=60)
                if r.status_code == 200:
                    with open(output_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                    size = os.path.getsize(output_path)
                    print(f"   Downloaded {size/1024:.0f} KB")
                    if size > 50000:  # at least 50KB = real video
                        return True
                    else:
                        print("   File too small, trying next...")

        except Exception as e:
            print(f"   Query '{query}' failed: {e}")
            continue

    print("   All Pexels queries failed — using color background")
    return False

def create_color_background_video(output_path, duration):
    """Create animated gradient background video"""
    try:
        from moviepy.editor import ColorClip
        # Dark blue-purple gradient style
        clip = ColorClip(size=(1080, 1920), color=[15, 25, 60], duration=duration)
        clip.write_videofile(output_path, fps=24, logger=None)
        clip.close()
        print(f"   Created color background: {duration:.1f}s")
        return True
    except Exception as e:
        print(f"   Color background error: {e}")
        return False

def create_final_video(stock_path, audio_path, output_path):
    """Combine background video + audio"""
    try:
        from moviepy.editor import VideoFileClip, AudioFileClip, ColorClip, concatenate_videoclips

        # Load audio first to get duration
        audio = AudioFileClip(audio_path)
        audio_duration = audio.duration
        print(f"   Audio: {audio_duration:.1f}s")

        # Load video background
        stock_exists = os.path.exists(stock_path) and os.path.getsize(stock_path) > 50000
        if stock_exists:
            print(f"   Using Pexels stock video")
            video = VideoFileClip(stock_path)

            # Loop video to match audio length
            if video.duration < audio_duration:
                loops = int(audio_duration / video.duration) + 2
                clips = [video] * loops
                video = concatenate_videoclips(clips)

            video = video.subclip(0, audio_duration)

            # Resize to 1080x1920 (9:16)
            target_w, target_h = 1080, 1920
            video = video.resize(height=target_h)
            if video.w != target_w:
                if video.w > target_w:
                    video = video.crop(x_center=video.w/2, width=target_w)
                else:
                    video = video.resize(width=target_w)
        else:
            print(f"   Using color background")
            video = ColorClip(size=(1080, 1920), color=[15, 25, 60], duration=audio_duration)

        # Attach audio
        final = video.set_audio(audio)

        # Write output
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
        print(f"   Final video error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("🎬 Creating Tamil News Videos...")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    print(f"Pexels key set: {'Yes' if PEXELS_API_KEY and PEXELS_API_KEY not in ('skip','') else 'No'}")

    os.makedirs(VIDEO_DIR, exist_ok=True)
    os.makedirs(ASSETS_DIR, exist_ok=True)

    # Load scripts
    try:
        with open(SCRIPTS_FILE, "r", encoding="utf-8") as f:
            scripts_data = json.load(f)["scripts"]
    except FileNotFoundError:
        print("❌ scripts.json not found!")
        return

    # Load audio manifest
    manifest_path = os.path.join(AUDIO_DIR, "manifest.json")
    try:
        with open(manifest_path, "r") as f:
            audio_files = json.load(f)["audio_files"]
    except FileNotFoundError:
        print("❌ Audio manifest not found!")
        return

    print(f"Found {len(scripts_data)} scripts and {len(audio_files)} audio files\n")
    created_videos = []

    for i, (script_data, audio_data) in enumerate(zip(scripts_data, audio_files), 1):
        print(f"🎥 Video {i}/{len(scripts_data)}: {script_data['topic'][:50]}...")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stock_path = os.path.join(ASSETS_DIR, f"stock_{i}.mp4")
        output_path = os.path.join(VIDEO_DIR, f"reel_{i}_{timestamp}.mp4")

        # Try to get Pexels video
        got_stock = download_pexels_video(stock_path)

        # Create final video
        audio_path = audio_data["audio_file"]
        if not os.path.exists(audio_path):
            print(f"   ❌ Audio missing: {audio_path}")
            continue

        success = create_final_video(
            stock_path if got_stock else "",
            audio_path,
            output_path
        )

        if success and os.path.exists(output_path):
            size_mb = os.path.getsize(output_path) / (1024*1024)
            created_videos.append({
                "topic": script_data["topic"],
                "video_file": output_path,
                "size_mb": round(size_mb, 1),
                "has_stock_footage": got_stock
            })
            bg_type = "stock footage" if got_stock else "color background"
            print(f"   ✅ Done! {size_mb:.1f}MB ({bg_type})\n")
        else:
            print(f"   ❌ Failed\n")

    # Save manifest
    v_manifest = os.path.join(VIDEO_DIR, "manifest.json")
    with open(v_manifest, "w") as f:
        json.dump({"videos": created_videos, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")}, f, indent=2)

    print(f"✅ {len(created_videos)} videos ready!")
    print(f"📁 {VIDEO_DIR}")

if __name__ == "__main__":
    main()
