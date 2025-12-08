import whisper
import os
from pathlib import Path
import librosa


class SpeechAnalyzer:

    def __init__(self, model_name="tiny"):
        print(f"Loading Whisper model: {model_name}")
        self.model = whisper.load_model(model_name)


    def analyze_audio(self, audio_path: str):
        audio_file = Path(audio_path)

        if not audio_file.exists():
            return {"error": f"Audio file does not exist: {audio_path}"}

        try:
            print("Transcribing with Whisper...")
            result = self.model.transcribe(str(audio_file))

            transcript = result.get("text", "").strip()
            words = transcript.split()
            word_count = len(words)

            # 🔥 TRUE duration using librosa (fixes your issue)
            audio_data, sr = librosa.load(audio_path)
            duration = librosa.get_duration(y=audio_data, sr=sr)

            # Speaking speed
            speaking_wpm = round((word_count / duration) * 60, 2)

            # Filler words
            filler_words = [w for w in words if w.lower() in ["um", "uh", "like", "you know"]]
            filler_count = len(filler_words)

            # Clarity & confidence simple estimates
            clarity_score = round(max(3.0, 10 - filler_count * 0.3), 2)
            confidence_score = round(min(10.0, len(transcript) / 100), 2)

            return {
                "transcript": transcript,
                "word_count": word_count,
                "speaking_speed_wpm": speaking_wpm,
                "filler_words_count": filler_count,
                "clarity_score": clarity_score,
                "confidence_score": confidence_score,
                "audio_duration_seconds": round(duration, 2)
            }

        except Exception as e:
            return {"error": str(e)}
