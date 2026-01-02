import subprocess
from pathlib import Path
from typing import Union


def extract_audio(video_path: Union[str, Path], output_dir: Union[str, Path]):
    """
    Extract audio from a video using ffmpeg.
    """
    video_path = Path(video_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_path = output_dir / "audio.wav"

    print(f"🔍 Probing audio for: {video_path}")

    # Step 1: Check for audio stream
    probe_cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=index",
        "-of", "csv=p=0",
        str(video_path),
    ]

    try:
        probe = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if probe.returncode != 0:
            print(f"❌ ffprobe failed: {probe.stderr}")
            return None
            
        if not probe.stdout.strip():
            print("⚠️ No audio stream found in video file.")
            return None
            
        print(f"✅ Audio stream found (Index: {probe.stdout.strip()})")
    except Exception as e:
        print(f"❌ Error during probe: {e}")
        return None

    # Step 2: Extract audio
    print("🔊 Extracting audio to WAV...")
    command = [
        "ffmpeg",
        "-y",
        "-nostdin",
        "-i", str(video_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        str(audio_path),
    ]

    try:
        proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0:
            print(f"❌ ffmpeg extraction failed: {proc.stderr}")
            return None
            
        if audio_path.exists():
            print(f"✅ Audio successfully extracted: {audio_path}")
            return str(audio_path)
        else:
            print("❌ ffmpeg success but file missing")
            return None
    except Exception as e:
        print(f"❌ ffmpeg process error: {e}")
        return None
