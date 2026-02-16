import imageio_ffmpeg
try:
    path = imageio_ffmpeg.get_ffmpeg_exe()
    print(f"Success: {path}")
except Exception as e:
    print(f"Error: {e}")
