import subprocess
import os
from pathlib import Path
from typing import Union
import imageio_ffmpeg

def extract_audio(video_path: Union[str, Path], output_dir: Union[str, Path]):
    """
    Extract audio from a video using imageio-ffmpeg (portable ffmpeg).
    """
    video_path = Path(video_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_path = output_dir / "audio.wav"

    # Get portable ffmpeg path
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    # Avoid emojis in logs to prevent Windows console encoding issues
    print(f"[INFO] Using ffmpeg from: {ffmpeg_exe}")

    print(f"[INFO] Probing audio for: {video_path}")

    # Step 1: Check for audio stream (using ffprobe if available, or just try extraction)
    # Note: imageio-ffmpeg doesn't expose ffprobe directly easily, so we skip probe 
    # and just try to extract. If it fails, it fails.
    
    # Step 2: Extract audio
    print("[STEP] Extracting audio to WAV...")
    command = [
        ffmpeg_exe,
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
        # Hide window on Windows
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            # Correct flag name is STARTF_USESHOWWINDOW (no extra underscore)
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        proc = subprocess.run(
            command, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True,
            startupinfo=startupinfo
        )
        
        if proc.returncode != 0:
            print(f"[ERROR] ffmpeg extraction failed: {proc.stderr}")
            return None
            
        if audio_path.exists():
            print(f"[INFO] Audio successfully extracted: {audio_path}")
            return str(audio_path)
        else:
            print("[ERROR] ffmpeg success but file missing")
            return None
    except Exception as e:
        print(f"[ERROR] ffmpeg process error: {e}")
        return None
