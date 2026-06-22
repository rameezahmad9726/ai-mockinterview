import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def generate_speech_batch(session_id: str, questions: list):
    """
    Pre-generate TTS for all questions in parallel.
    questions: list of {"text": "...", "index": int}
    Returns: list of {"index": int, "url": str} or None on error
    """
    output_dir = Path("uploads") / session_id / "tts"
    output_dir.mkdir(parents=True, exist_ok=True)
    base_url = "http://localhost:8000/tts"

    def _gen_one(item):
        idx = item["index"]
        text = item.get("text", "")
        path = generate_speech(text, session_id, idx)
        if path:
            return {"index": idx, "url": f"{base_url}/{session_id}/{Path(path).name}"}
        return {"index": idx, "url": None}

    results = []
    with ThreadPoolExecutor(max_workers=min(5, len(questions))) as ex:
        futures = [ex.submit(_gen_one, q) for q in questions]
        for fut in as_completed(futures):
            try:
                results.append(fut.result())
            except Exception as e:
                print(f"TTS batch item failed: {e}")
    return sorted(results, key=lambda x: x["index"])
