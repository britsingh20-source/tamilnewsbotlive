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

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "YOUR_PEXELS_API_KEY_HERE")

TOPIC_TO_QUERY = {
    "default": "india news crowd street",
    "lockdown": "india street empty",
    "petrol": "petrol pump fuel india",
    "politics": "indian parliament building",
    "technology": "technology digital india",
    "sports": "cricket india stadium",
    "weather": "india rain monsoon",
    "accident": "india traffic road",
    "economy": "india market business",
}

def get_search_query(topic_title):
    topic_lower = topic_title.lower()
    for keyword, query in TOPIC_TO_QUERY.items():
        if keyword in topic_lower:
            return query
    return TOPIC_TO_QUERY["default"]

def download_stock_video(query, output_path):
    """Download a free stock video from Pexels"""
    if PEXELS_API_KEY in ("YOUR_PEXELS_API_KEY_HERE", "skip", ""):
        print("   ⚠️  No Pexels API key. Using placeholder video.")
        return create_placeholder_video(output_path)
    try:
        headers = {"Authorization": PEXELS_API_KEY}
        resp = requests.get(
            f"https://api.pexels.com/videos/search?query={query}&per_page=5&orientation=portrait",
            headers=headers, timeout=15
        )
        data = resp.json()
        videos = data.get("videos", [])
        if not videos:
            return create_placeholder_video(output_path)
        video = videos[0]
        video_files = [f for f in video.get("video_files", []) if f.get("quality") in ["hd", "sd"]]
        video_files.sort(key=lambda x: x.get("width", 0))
        if not video_files:
            return create_placeholder_video(output_path)
        video_url = video_files[0]["link"]
        print(f"   Downloading stock video from Pexels...")
        r = requests.get(video_url, stream=True, timeout=60)
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"   Pexels error: {e}")
        return create_placeholder_video(output_path)

def create_placeholder_video(output_path):
    """Create a simple colored placeholder video using MoviePy"""
    try:
        from moviepy.editor import ColorClip
        clip = ColorClip(size=(1080, 1920), color=[20, 20, 40], duration=30)
        clip.write_videofile(output_path, fps=24, logger=None)
        clip.close()
        return True
    except Exception as e:
        print(f"   Placeholder video error: {e}")
        return False

def create_video_with_audio(video_path, audio_path, output_path):
    """Combine video + audio using MoviePy (no ImageMagick needed)"""
    try:
        from moviepy.editor import VideoFileClip, AudioFileClip, ColorClip, concatenate_videoclips

        audio = AudioFileClip(audio_path)
        audio_duration = audio.duration
        print(f"   Audio duration: {audio_duration:.1f}s")

        # Load or create video
        if os.path.exists(video_path) and os.path.getsize(video_path) > 1000:
            video = VideoFileClip(video_path)
            # Loop if needed
            if video.duration < audio_duration:
                loops = int(audio_duration / video.duration) + 1
                video = concatenate_videoclips([video] * loops)
            video = video.subclip(0, audio_duration)
            # Resize to 9:16
            video = video.resize(height=1920)
            if video.w > 1080:
                video = video.crop(x_center=video.w / 2, width=1080)
        else:
            # Fallback: solid color background
            video = ColorClip(size=(1080, 1920), color=[20, 20, 40], duration=audio_duration)

        # Set audio
        final = video.set_audio(audio)

        final.write_videofile(
            output_path,
            fps=24,
            codec="libx264",
            audio_codec="aac",
            logger=None,
            threads=2
        )
        audio.close()
        final.close()
        return True

    except Exception as e:
        print(f"   Video creation error: {e}")
        return False

def main():
    print("🎬 Creating Tamil News Videos...")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    os.makedirs(VIDEO_DIR, exist_ok=True)
    os.makedirs(ASSETS_DIR, exist_ok=True)

    # Load scripts
    try:
        with open(SCRIPTS_FILE, "r", encoding="utf-8") as f:
            scripts_data = json.load(f)["scripts"]
    except FileNotFoundError:
        print("❌ scripts.json not found. Run 2_generate_script.py first!")
        return

    # Load audio manifest
    manifest_path = os.path.join(AUDIO_DIR, "manifest.json")
    try:
        with open(manifest_path, "r") as f:
            audio_files = json.load(f)["audio_files"]
    except FileNotFoundError:
        print("❌ Audio manifest not found. Run 3_generate_voice.py first!")
        return

    print(f"Found {len(scripts_data)} scripts and {len(audio_files)} audio files")
    created_videos = []

    for i, (script_data, audio_data) in enumerate(zip(scripts_data, audio_files), 1):
        print(f"\n🎥 Creating video {i}/{len(scripts_data)}: {script_data['topic'][:40]}...")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Download stock video
        stock_path = os.path.join(ASSETS_DIR, f"stock_{i}.mp4")
        query = get_search_query(script_data["topic"])
        print(f"   Fetching stock footage: '{query}'...")
        download_stock_video(query, stock_path)

        # Create final video
        audio_path = audio_data["audio_file"]
        if not os.path.exists(audio_path):
            print(f"   ❌ Audio file not found: {audio_path}")
            continue

        output_path = os.path.join(VIDEO_DIR, f"reel_{i}_{timestamp}.mp4")
        print(f"   Combining video + audio...")
        success = create_video_with_audio(stock_path, audio_path, output_path)

        if success and os.path.exists(output_path):
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            created_videos.append({
                "topic": script_data["topic"],
                "video_file": output_path,
                "size_mb": round(size_mb, 1),
                "ready_to_post": True
            })
            print(f"   ✅ Video created: reel_{i}_{timestamp}.mp4 ({size_mb:.1f} MB)")
        else:
            print(f"   ❌ Video creation failed")

    # Save manifest
    v_manifest = os.path.join(VIDEO_DIR, "manifest.json")
    with open(v_manifest, "w") as f:
        json.dump({"videos": created_videos, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")}, f, indent=2)

    print(f"\n✅ {len(created_videos)} videos ready!")
    print(f"📁 Video folder: {VIDEO_DIR}")

if __name__ == "__main__":
    main()
