import os
import torch
from pathlib import Path
from transformers import pipeline

# Switch to a much faster MobileNetV3-based model
MODEL_NAME = "dima806/facial_emotions_image_detection"

# Cached classifier (load once, reuse across analyses)
_classifier = None
_classifier_device = None

def _get_emotion_classifier():
    """Get or create cached emotion classifier for reuse."""
    global _classifier, _classifier_device
    if _classifier is not None:
        return _classifier
    print(f"[INFO] Loading emotion model: {MODEL_NAME}")
    device = -1
    if torch.cuda.is_available():
        device = 0
    elif torch.backends.mps.is_available():
        device = "mps"
    print(f"[INFO] Using device: {device}")
    try:
        _classifier = pipeline("image-classification", model=MODEL_NAME, device=device)
    except Exception as e:
        print(f"[WARN] Could not load on {device}, falling back to CPU: {e}")
        _classifier = pipeline("image-classification", model=MODEL_NAME, device=-1)
    return _classifier

def analyze_emotions_vit(frames_dir, subsample_step=2):
    """
    Lightning-fast emotion analysis. Uses cached model. Processes frames in batches.
    subsample_step: process every Nth frame (2 = every 2nd) for faster analysis.
    """
    classifier = _get_emotion_classifier()

    # Get all frames, optionally subsample for speed
    all_frames = sorted(list(Path(frames_dir).glob("*.jpg")))
    frames = all_frames[::subsample_step] if subsample_step > 1 else all_frames
    if not frames:
        return {
            "dominant_emotion": "Neutral", 
            "emotion_counts": {}, 
            "emotion_history": []
        }

    emotion_history = []
    
    # Batch processing significantly speeds up inference
    print(f"[INFO] Processing {len(frames)} frames...")
    
    # Optimized batch size for average hardware
    batch_size = 16
    for i in range(0, len(frames), batch_size):
        batch_paths = [str(p) for p in frames[i:i+batch_size]]
        try:
            results = classifier(batch_paths)
            for result in results:
                # result is a list of scores, get the top one
                top_emotion = result[0]['label']
                emotion_history.append(top_emotion)
        except Exception as e:
            print(f"[WARN] Batch error at {i}: {e}")
            # Fallback to single processing for this batch if it fails
            for p in batch_paths:
                try:
                    res = classifier(p)
                    emotion_history.append(res[0]['label'])
                except:
                    emotion_history.append("neutral")

    # Calculate statistics
    counts = {}
    for emo in emotion_history:
        # Standardize labels
        emo_key = emo.capitalize()
        counts[emo_key] = counts.get(emo_key, 0) + 1

    dominant = max(counts, key=counts.get) if counts else "Neutral"
    
    print(f"[INFO] Emotion analysis complete. Dominant: {dominant}")

    return {
        "dominant_emotion": dominant,
        "emotion_counts": counts,
        "emotion_history": emotion_history,
        "frames_analyzed": len(emotion_history)
    }
