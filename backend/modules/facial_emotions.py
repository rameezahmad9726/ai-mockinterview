import os
import glob
from typing import TYPE_CHECKING

# Allow static type checkers / editors to see these names without forcing
# runtime imports (which may be missing in lightweight environments).
if TYPE_CHECKING:
    import cv2  # type: ignore
    import numpy as np  # type: ignore
    from deepface import DeepFace  # type: ignore


def analyze_emotions(frames_dir: str, max_frames: int = 100):
    frame_paths = sorted(glob.glob(os.path.join(frames_dir, "*.jpg")))

    if not frame_paths:
        return {
            "frames_analyzed": 0,
            "dominant_emotion": None,
            "emotion_counts": {},
            "emotion_timeline": [],
            "emotion_score": 0,
            "comments": ["No frames found for emotion analysis."]
        }

    emotions_timeline = []
    emotion_counts = {}

    for idx, frame in enumerate(frame_paths[:max_frames]):
        img = cv2.imread(frame)
        if img is None:
            continue

        try:
            result = DeepFace.analyze(
                img_path=img,
                actions=["emotion"],
                enforce_detection=False
            )
        except Exception:
            continue

        emo = result.get("dominant_emotion", "unknown")
        confidence = result.get("emotion", {}).get(emo, 0)

        emotions_timeline.append({
            "frame": idx,
            "emotion": emo,
            "confidence": float(confidence)
        })

        emotion_counts[emo] = emotion_counts.get(emo, 0) + 1

    if not emotion_counts:
        return {
            "frames_analyzed": 0,
            "dominant_emotion": None,
            "emotion_counts": {},
            "emotion_timeline": [],
            "emotion_score": 0,
            "comments": ["No detectable faces found in frames."]
        }

    dominant = max(emotion_counts, key=emotion_counts.get)

    stable = ["neutral", "happy"]
    emotion_score = 9 if dominant in stable else 6

    comments = []
    if dominant == "happy":
        comments.append("Your facial expressions appear confident and positive.")
    elif dominant == "neutral":
        comments.append("You maintained a calm, professional expression.")
    elif dominant == "sad":
        comments.append("Your expression seems low-energy. Try appearing more engaged.")
    elif dominant == "angry":
        comments.append("Your facial tension suggests frustration. Relax facial muscles.")
    elif dominant == "fear":
        comments.append("You look nervous. Practice maintaining eye contact and relaxing.")
    elif dominant == "surprise":
        comments.append("Your expressions fluctuate too much. Try staying composed.")
    else:
        comments.append("Your expressions vary a lot. Try to maintain a stable expression.")

    return {
        "frames_analyzed": len(emotions_timeline),
        "dominant_emotion": dominant,
        "emotion_counts": emotion_counts,
        "emotion_timeline": emotions_timeline,
        "emotion_score": emotion_score,
        "comments": comments
    }
