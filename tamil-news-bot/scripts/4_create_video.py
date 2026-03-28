"""
STEP 4: Auto-Create Video with Captions (FREE)
- Downloads free stock video from Pexels API (free key)
- Combines with Tamil voiceover audio
- Adds Tamil text captions overlay
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

# Get FREE Pexels API key at: https://www.pexels.com/api/
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
    """Map topic to Pexels search query"""
    topic_lower = topic_title.lower()
    for keyword, query in TOPIC_TO_QUERY.items():
        if keyword in topic_lower:
            return query
    return TOPIC_TO_QUERY["default"]

def download_stock_video(query, output_path):
    """Download a free stock video from Pexels"""
    if PEXELS_API_KEY == "YOUR_PEXELS_API_KEY_HERE":
        print("   ⚠️  No Pexels API key. Using placeholder video.")
        return create_placeholder_video(output_path)

    try:
        headers = {"Authorization": PEXELS_API_KEY}
        resp = requests.get(
            f"https://api.pexels.com/videos/search?query={query}&per_page=5&orientation=portrait",
            headers=headers, timeout=10
        )
        data = resp.json()
        videos = data.get("videos", [])
        if not videos:
            return create_placeholder_video(output_path)

        # Get best portrait video file
        video = videos[0]
        video_files = [f for f in video.get("video_files", []) if f.get("quality") in ["hd", "sd"]]
        video_files.sort(key=lambda x: x.get("width", 0))
        if not video_files:
            return create_placeholder_video(output_path)

        video_url = video_files[0]["link"]
        print(f"   Downloading stock video from Pexels...")
        r = requests.get(video_url, stream=True, timeout=30)
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
        clip = ColorClip(size=(1080, 1920), color=[20, 20, 40], duration=60)
        clip.write_videofile(output_path, fps=24, logger=None)
        return True
    except Exception as e:
        print(f"   Placeholder video error: {e}")
        return False

def add_captions_and_audio(video_path, audio_path, hook_text, topic, output_path):
    """Combine video + audio + text captions using MoviePy"""
    try:
        from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip, concatenate_videoclips

        # Load video and audio
        video = VideoFileClip(video_path)
        audio = AudioFileClip(audio_path)

        # Match video duration to audio
        audio_duration = audio.duration
        if video.duration < audio_duration:
            loops = int(audio_duration / video.duration) + 1
            video = concatenate_videoclips([video] * loops)
        video = video.subclip(0, audio_duration)

        # Resize to 9:16 (1080x1920)
        video = video.resize(height=1920)
        if video.w > 1080:
            video = video.crop(x_center=video.w/2, width=1080)

        # Set audio
        video = video.set_audio(audio)

        # Add hook text overlay (top of screen)
        try:
            txt_clip = TextClip(
                hook_text,
                fontsize=55,
                color="white",
                stroke_color="black",
                stroke_width=3,
                method="caption",
                size=(900, None),
                align="center"
            ).set_position(("center", 120)).set_duration(5)

            # Add topic label at bottom
            topic_clip = TextClip(
                f"📰 {topic[:40]}",
                fontsize=35,
                color="yellow",
                stroke_color="black",
                stroke_width=2,
                method="caption",
                size=(900, None),
                align="center"
            ).set_position(("center", 1700)).set_duration(audio_duration)

            final = CompositeVideoClip([video, txt_clip, topic_clip])
        except Exception:
            # Fallback: video without text overlay
            final = video

        final.write_videofile(
            output_path,
            fps=24,
            codec="libx264",
            audio_codec="aac",
            logger=None
        )
        return True
    except ImportError:
        print("   Installing MoviePy...")
        os.system("pip install moviepy --break-system-packages -q")
        print("   ✅ MoviePy installed. Please run again.")
        return False
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

    created_videos = []

    for i, (script_data, audio_data) in enumerate(zip(scripts_data, audio_files), 1):
        print(f"🎥 Creating video {i}/{len(scripts_data)}: {script_data['topic'][:40]}...")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Download stock video
        stock_path = os.path.join(ASSETS_DIR, f"stock_{i}_{timestamp}.mp4")
        query = get_search_query(script_data["topic"])
        print(f"   Fetching stock footage: '{query}'...")
        download_stock_video(query, stock_path)

        # Create final video
        audio_path = audio_data["audio_file"]
        output_path = os.path.join(VIDEO_DIR, f"reel_{i}_{timestamp}.mp4")

        hook = script_data.get("hook", script_data["topic"])
        print(f"   Adding captions and audio...")
        success = add_captions_and_audio(stock_path, audio_path, hook, script_data["topic"], output_path)

        if success:
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

    # Save video manifest
    v_manifest = os.path.join(VIDEO_DIR, "manifest.json")
    with open(v_manifest, "w") as f:
        json.dump({"videos": created_videos, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")}, f, indent=2)

    print(f"\n✅ {len(created_videos)} videos ready!")
    print(f"📁 Video folder: {VIDEO_DIR}")
    print("\n💡 TIP: For better quality, import these into CapCut for final polish before posting.")

if __name__ == "__main__":
    main()
