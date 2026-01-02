import os
from transformers import AutoImageProcessor, AutoModelForImageClassification

model_name = "DrGM/DrGM-ConvNeXt-V2L-Facial-Emotion-Recognition"
print(f"Downloading model: {model_name}...")
print("This is a larger model (ConvNeXt V2 Large), ensure you have enough space/RAM...")

try:
    AutoImageProcessor.from_pretrained(model_name)
    AutoModelForImageClassification.from_pretrained(model_name)
    print("\n✅ Model downloaded and cached successfully!")
except Exception as e:
    print(f"\n❌ Error downloading model: {e}")
