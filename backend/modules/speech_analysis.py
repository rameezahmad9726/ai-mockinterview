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

    def _format_transcript_with_speakers(self, transcript, questions=None):
        """
        AI-powered diarization: Splits the transcript into Interviewer and Interviewee segments.
        Uses LLM to understand context and flow.
        """
        from modules.question_generator import _get_client, OPENAI_MODEL
        
        if not transcript.strip():
            return []

        try:
            client = _get_client()
            
            # Prepare context if questions are provided
            context_prompt = ""
            if questions:
                # Extract question strings if they are objects
                q_list = [q['question'] if isinstance(q, dict) else q for q in questions]
                context_prompt = f"The interviewer was scheduled to ask these questions: {q_list}. "

            prompt = f"""
            Task: Segment the following raw interview transcript into "Interviewer" and "Interviewee" turns.
            
            Context: {context_prompt}
            
            Diarization Guide:
            - The "Interviewer" is a professional AI asking questions.
            - The "Interviewee" is the candidate responding to those questions.
            - Even if the "Interviewee" speaks briefly or softly, their words MUST be captured as a separate segment.
            - Use the provided context to identify the exact words of the Interviewer.
            - Any content that is NOT a question being asked by the AI is almost certainly the "Interviewee".
            
            STRICT RULES:
            1. DO NOT hallucinate any dialogue. ONLY use the words found in the "Raw Transcript" below.
            2. Split segments whenever the speaker changes.
            3. Return ONLY a JSON object with a key "formatted_transcript".
            4. If a speaker is repeating something or stuttering, keep it in the transcript.

            Raw Transcript:
            \"\"\"{transcript}\"\"\"

            Format: {{"formatted_transcript": [{{"speaker": "Interviewer", "text": "..."}}, {{"speaker": "Interviewee", "text": "..."}}]}}
            """

            print(f"DEBUG: Processing diarization with LLM... (Input: {len(transcript)} chars)")
            
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a transcript processor. Your job is to classify segments, NOT to write dialogue. Strictly follow the raw transcript."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                response_format={ "type": "json_object" }
            )
            
            content = response.choices[0].message.content
            data = json.loads(content)
            formatted = data.get("formatted_transcript", [])
            print(f"DEBUG: Diarization complete. Segments: {len(formatted)}")
            return formatted
            
        except Exception as e:
            print(f"AI Diarization failed: {e}. Falling back to simple heuristic.")
            # Simple fallback if AI fails
            return [{"speaker": "Interviewer", "text": transcript}]

    def _analyze_tone(self, formatted_transcript):
        """
        Uses LLM to evaluate the confidence and tone of the interviewee's responses.
        """
        from modules.question_generator import _get_client, OPENAI_MODEL
        
        interviewee_text = " ".join([seg['text'] for seg in formatted_transcript if seg['speaker'] == 'Interviewee'])
        
        if not interviewee_text.strip():
            return {"confidence_rating": 5, "tone_analysis": "No response detected."}

        try:
            client = _get_client()
            prompt = f"""
            Analyze the following candidate's interview responses for confidence and professional tone.
            
            Responses:
            "{interviewee_text[:2000]}"
            
            Evaluate based on:
            1. Language directness (avoiding "I think", "maybe", "I guess").
            2. Logic and structure.
            3. Professionalism.
            
            Return ONLY a JSON object:
            {{
                "confidence_rating": (1-10 integer),
                "tone_analysis": "Short summary of their communication style",
                "improvement_tip": "One specific tip to sound more confident"
            }}
            """
            
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are an expert communication coach analyzing interview confidence."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                response_format={ "type": "json_object" }
            )
            
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"Tone analysis failed: {e}")
            return {"confidence_rating": 5, "tone_analysis": "Evaluation unavailable."}

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

            options = whisper.DecodingOptions(fp16=False)
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

            # Clarity & confidence simple estimates
            clarity_score = round(max(3.0, 10 - filler_count * 0.5), 2)
            
            # Format transcript with speaker separation
            formatted_transcript = self._format_transcript_with_speakers(transcript, questions)
            
            # AI Tone Analysis
            tone_data = self._analyze_tone(formatted_transcript)

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
