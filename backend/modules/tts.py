import os
from pathlib import Path
from modules.question_generator import _get_client, OPENAI_MODEL

# We'll use a specific TTS model
TTS_MODEL = "tts-1"

def generate_speech(text: str, session_id: str, question_index: int):
    """
    Generate speech from text using OpenAI TTS.
    Saves to a file and returns the path.
    """
    try:
        client = _get_client()
        
        # Create output directory
        output_dir = Path("uploads") / session_id / "tts"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = output_dir / f"question_{question_index}.mp3"
        
        response = client.audio.speech.create(
            model=TTS_MODEL,
            voice="alloy", # or nova, shimmer, etc.
            input=text
        )
        
        response.stream_to_file(str(output_path))
        return str(output_path)
    except Exception as e:
        print(f"TTS Error: {e}")
        return None
