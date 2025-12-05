import asyncio
from pathlib import Path
import tempfile
import os

async def fake_save(original_filename: str, content: bytes):
    UPLOAD_DIR = Path(__file__).resolve().parent.parent / "backend" / "uploads"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    original_stem = Path(original_filename).stem or "uploaded_video"
    video_dir_path = tempfile.mkdtemp(prefix=f"{original_stem}_", dir=str(UPLOAD_DIR))
    video_folder = Path(video_dir_path)

    original_dir = video_folder / "original"
    audio_dir = video_folder / "audio"
    frames_dir = video_folder / "frames"

    original_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)

    video_path = original_dir / original_filename
    with open(video_path, "wb") as f:
        f.write(content)

    return video_folder, video_path, audio_dir, frames_dir

async def main():
    folder, vpath, a, f = await fake_save("myvideo.mp4", b"hello world")
    print("Created folder:", folder)
    print("Video saved:", vpath.exists())
    print("Audio dir exists:", a.exists())
    print("Frames dir exists:", f.exists())

if __name__ == "__main__":
    asyncio.run(main())
