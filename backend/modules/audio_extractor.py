import subprocess
from pathlib import Path
from typing import Union


def extract_audio(video_path: Union[str, Path], output_dir: Union[str, Path]):
    """
    Extract audio from a video using ffmpeg.

    - Creates output directory
    - Detects if video has NO audio stream (prevents runtime error)
    - Returns None if no audio exists
    - Otherwise returns the path to extracted WAV audio
    """

    video_path = Path(video_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------
    # Step 1 — Detect if file contains an audio stream
    # ---------------------------------------------------
    probe_cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=index",
        "-of", "csv=p=0",
        str(video_path),
    ]

    probe = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    # If ffprobe finds no audio stream
    if probe.stdout.strip() == "":
        return None  # <-- IMPORTANT: gracefully handle silent videos

    # ---------------------------------------------------
    # Step 2 — Extract audio (since audio exists)
    # ---------------------------------------------------
    audio_path = output_dir / "audio.wav"

    command = [
        "ffmpeg",
        "-y",
        "-i", str(video_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        str(audio_path),
    ]

    proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed extracting audio: {proc.stderr.strip()}")

    if not audio_path.exists():
        raise RuntimeError("ffmpeg reported success but audio file not found")

    return str(audio_path)
