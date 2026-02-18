import os
import json
from pathlib import Path

# Try to import speech analysis libraries
try:
    import whisper
    import librosa
    SPEECH_LIBS_AVAILABLE = True
except (ImportError, Exception) as e:
    print(f"Warning: Speech analysis libraries missing ({e}). Speech analysis disabled.")
    SPEECH_LIBS_AVAILABLE = False
    whisper = None
    librosa = None


class SpeechAnalyzer:

    def __init__(self, model_name="tiny"):
        self.model_name = model_name
        self.model = None  # Lazy load on first use
        self._load_error = None  # Set if model load fails (for tests and introspection)

    def _ensure_loaded(self):
        """Load Whisper model on first use (lazy loading)."""
        if self.model is None and SPEECH_LIBS_AVAILABLE:
            print(f"Loading Whisper model: {self.model_name}...")
            try:
                import ssl
                import urllib.request
                # Bypass SSL verification for model download
                ssl._create_default_https_context = ssl._create_unverified_context
                self.model = whisper.load_model(self.model_name)
                self._load_error = None
                print("[INFO] Whisper model loaded successfully")
            except Exception as e:
                print(f"Failed to load Whisper model: {e}")
                self._load_error = e
                self.model = None

    def _ensure_model_loaded(self):
        """Ensure the Whisper model is loaded. Returns True if loaded, False otherwise (for tests)."""
        self._ensure_loaded()
        return self.model is not None

    def _diarize_and_analyze_tone(self, transcript, questions=None, clarity_score=None, filler_count=0):
        """
        Single LLM call: diarize transcript + analyze tone. Saves one API call.
        Returns (formatted_transcript, tone_data).
        """
        from modules.question_generator import _get_client, OPENAI_MODEL
        
        if not transcript.strip():
            return [], {"confidence_rating": 5, "tone_analysis": "No response detected.", "improvement_tip": ""}

        context_prompt = ""
        if questions:
            q_list = [q['question'] if isinstance(q, dict) else q for q in questions]
            context_prompt = f"The interviewer was scheduled to ask these questions: {q_list}. "

        clarity_note = ""
        if clarity_score is not None and clarity_score >= 8:
            clarity_note = f"\n\nIMPORTANT: The candidate's clarity score is {clarity_score}/10. Do NOT suggest improving clarity or reducing fillers. Focus on confidence, structure, or professionalism."
        elif clarity_score is not None and filler_count > 0:
            clarity_note = f"\n\nThe candidate used {filler_count} filler word(s); clarity score is {clarity_score}/10. Do not contradict numeric scores."

        prompt = f"""
Task 1 (Diarization): Segment the raw transcript into "Interviewer" and "Interviewee" turns.
Context: {context_prompt}
- Interviewer = AI asking questions. Interviewee = candidate responding.
- DO NOT hallucinate. Use ONLY words from the Raw Transcript.
- Split segments when speaker changes.

Task 2 (Tone): Analyze the Interviewee's responses for confidence and tone.
Evaluate: directness, logic/structure, professionalism.
{clarity_note}

Raw Transcript:
\"\"\"{transcript[:4000]}\"\"\"

Return ONLY a JSON object:
{{
    "formatted_transcript": [{{"speaker": "Interviewer"|"Interviewee", "text": "..."}}],
    "confidence_rating": (1-10 integer),
    "tone_analysis": "Short summary of communication style",
    "improvement_tip": "One specific tip to sound more confident"
}}
"""

        try:
            client = _get_client()
            print(f"DEBUG: Combined diarization+tone with LLM... ({len(transcript)} chars)")
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a transcript processor and communication coach. Output strictly JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
            data = json.loads(response.choices[0].message.content)
            formatted = data.get("formatted_transcript", [])
            tone_data = {
                "confidence_rating": data.get("confidence_rating", 5),
                "tone_analysis": data.get("tone_analysis", ""),
                "improvement_tip": data.get("improvement_tip", ""),
            }
            print(f"DEBUG: Combined call complete. Segments: {len(formatted)}")
            return formatted, tone_data
        except Exception as e:
            print(f"Combined diarization+tone failed: {e}. Using fallback.")
            fallback_formatted = [{"speaker": "Interviewer", "text": transcript}]
            return fallback_formatted, {"confidence_rating": 5, "tone_analysis": "Evaluation unavailable.", "improvement_tip": ""}

    def analyze_audio(self, audio_path: str, questions=None):
        self._ensure_loaded()  # Load model on first use
        
        if not SPEECH_LIBS_AVAILABLE or self.model is None:
            return {
                "error": "Speech analysis libraries not installed or model failed to load.",
                "transcript": "",
                "word_count": 0,
                "speaking_speed_wpm": 0,
                "filler_words_count": 0,
                "clarity_score": 0,
                "confidence_score": 0,
                "audio_duration_seconds": 0
            }

        audio_file = Path(audio_path)

        if not audio_file.exists():
            return {"error": f"Audio file does not exist: {audio_path}"}

        try:
            print("Transcribing with Whisper (no external ffmpeg)...")

            # Load audio with librosa (pure Python/Libsndfile, avoids ffmpeg dependency)
            audio_data, sr = librosa.load(audio_path, sr=16000)
            duration = librosa.get_duration(y=audio_data, sr=sr)

            # Prepare mel spectrogram for Whisper directly
            import numpy as np
            import whisper

            audio_np = whisper.pad_or_trim(audio_data.astype(np.float32))
            mel = whisper.log_mel_spectrogram(audio_np).to(self.model.device)

            # FP16 on CUDA for faster inference; CPU needs fp16=False
            try:
                import torch
                use_fp16 = torch.cuda.is_available() and str(self.model.device) != 'cpu'
            except ImportError:
                use_fp16 = False
            options = whisper.DecodingOptions(fp16=use_fp16)
            result = whisper.decode(self.model, mel, options)

            transcript = (result.text or "").strip()
            print(f"DEBUG: RAW TRANSCRIPT: {transcript}")
            words = transcript.split()
            word_count = len(words)

            # Speaking speed
            speaking_wpm = round((word_count / duration) * 60, 2) if duration > 0 else 0

            # Filler words
            filler_words = [w for w in words if w.lower() in ["um", "uh", "like", "you know"]]
            filler_count = len(filler_words)

            # Clarity & confidence simple estimates (clarity = low filler usage)
            clarity_score = round(max(3.0, 10 - filler_count * 0.5), 2)
            
            # Single LLM call: diarization + tone analysis
            formatted_transcript, tone_data = self._diarize_and_analyze_tone(
                transcript, questions=questions, clarity_score=clarity_score, filler_count=filler_count
            )

            return {
                "transcript": transcript,
                "formatted_transcript": formatted_transcript,
                "word_count": word_count,
                "speaking_speed_wpm": speaking_wpm,
                "filler_words_count": filler_count,
                "clarity_score": clarity_score,
                "confidence_score": tone_data.get("confidence_rating", 5),
                "tone_analysis": tone_data.get("tone_analysis", ""),
                "improvement_tip": tone_data.get("improvement_tip", ""),
                "audio_duration_seconds": round(duration, 2)
            }

        except Exception as e:
            return {"error": str(e)}
