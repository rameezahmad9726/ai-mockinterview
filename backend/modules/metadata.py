import cv2
from typing import Union
from pathlib import Path


def get_video_metadata(video_path: Union[str, Path]):
    vid = cv2.VideoCapture(str(video_path))
    try:
        fps = float(vid.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = float(vid.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
        width = int(vid.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(vid.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        duration = frame_count / fps if fps > 0 else 0

        return {
            "fps": fps,
            "duration_sec": duration,
            "frame_count": int(frame_count),
            "resolution": f"{width}x{height}"
        }
    finally:
        vid.release()
