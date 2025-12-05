import torch
from transformers import AutoImageProcessor, AutoModelForImageClassification
from PIL import Image
import os
import glob

class EmotionViT:
    def __init__(self):
        self.processor = AutoImageProcessor.from_pretrained(
            "dima806/facial_emotions_image_detection"
        )
        self.model = AutoModelForImageClassification.from_pretrained(
            "dima806/facial_emotions_image_detection"
        )
        self.model.eval()

    def predict_emotion(self, image_path):
        image = Image.open(image_path).convert("RGB")
        inputs = self.processor(images=image, return_tensors="pt")

        with torch.no_grad():
            outputs = self.model(**inputs)

        logits = outputs.logits
        probs = torch.softmax(logits, dim=1)[0]

        idx = torch.argmax(probs).item()
        emotion = self.model.config.id2label[idx]
        confidence = float(probs[idx].item())

        return emotion, confidence


def analyze_emotions_vit(frames_dir, max_frames=100):
    predictor = EmotionViT()

    frame_paths = sorted(glob.glob(os.path.join(frames_dir, "*.jpg")))

    timeline = []
    counts = {}

    for i, path in enumerate(frame_paths[:max_frames]):
        emotion, conf = predictor.predict_emotion(path)

        timeline.append({
            "frame": i,
            "emotion": emotion,
            "confidence": conf,
        })

        counts[emotion] = counts.get(emotion, 0) + 1

    dominant = max(counts, key=counts.get) if counts else None

    return {
        "frames_analyzed": len(timeline),
        "dominant_emotion": dominant,
        "emotion_counts": counts,
        "emotion_timeline": []
    }
