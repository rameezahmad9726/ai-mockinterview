import os
import torch
from pathlib import Path
from transformers import pipeline

# Switch to a much faster MobileNetV3-based model
MODEL_NAME = "dima806/facial_emotions_image_detection"

def analyze_emotions_vit(frames_dir):
    """
    Lightning-fast emotion analysis using MobileNetV3.
    Processes video frames in batches for maximum throughput.
    """
    print(f"😃 Loading optimized emotion model: {MODEL_NAME}")
    
    # Auto-detect best available device
    device = -1 # Default to CPU
    if torch.cuda.is_available():
        device = 0
    elif torch.backends.mps.is_available():
        device = "mps" # Support for Mac M1/M2 chips
    
    print(f"⚙️ Using device: {device}")
    
    # Initialize classifier pipeline
    try:
        classifier = pipeline("image-classification", model=MODEL_NAME, device=device)
    except Exception as e:
        print(f"⚠️ Could not load on {device}, falling back to CPU: {e}")
        classifier = pipeline("image-classification", model=MODEL_NAME, device=-1)

    # Get all frames
    frames = sorted(list(Path(frames_dir).glob("*.jpg")))
    if not frames:
        return {
            "dominant_emotion": "Neutral", 
            "emotion_counts": {}, 
            "emotion_history": []
        }

    emotion_history = []
    
    # Batch processing significantly speeds up inference
    print(f"⚡ Processing {len(frames)} frames...")
    
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
            print(f"⚠️ Batch error at {i}: {e}")
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

    print(f"✅ Emotion analysis complete. Dominant: {dominant}")

    return {
        "dominant_emotion": dominant,
        "emotion_counts": counts,
        "emotion_history": emotion_history,
        "frames_analyzed": len(emotion_history)
    }
