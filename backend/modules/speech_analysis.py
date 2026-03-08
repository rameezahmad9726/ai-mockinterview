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

    def _validate_interviewee_segments(self, formatted, transcript):
        """
        Remove hallucinated interviewee segments. LLM may invent answers not in the transcript.
        Returns (validated_formatted, interviewee_word_count).
        """
        import re
        trans_norm = re.sub(r"[^\w\s]", "", transcript.lower())
        trans_words = set(trans_norm.split())
        total_interviewee_words = 0
        validated = []
        for seg in formatted:
            text = seg.get("text", "").strip()
            speaker = seg.get("speaker", "")
            if speaker != "Interviewee":
                validated.append(seg)
                continue
            if not text:
                validated.append(seg)
                continue
            seg_words = re.sub(r"[^\w\s]", "", text.lower()).split()
            if not seg_words:
                validated.append(seg)
                continue
            matches = sum(1 for w in seg_words if len(w) > 2 and w in trans_words)
            ratio = matches / len(seg_words) if seg_words else 0
            if ratio >= 0.5:
                validated.append(seg)
                total_interviewee_words += len(seg_words)
            else:
                validated.append({"speaker": "Interviewee", "text": "[No audible response]"})
                print(f"[WARN] Removed hallucinated interviewee segment (only {ratio:.0%} words in transcript)")
        return validated, total_interviewee_words

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

CRITICAL RULES - DO NOT VIOLATE:
- Use ONLY the exact words that appear in the Raw Transcript. Copy them verbatim.
- If the candidate did NOT speak, there will be NO "Interviewee" segments. Do NOT invent, generate, or paraphrase answers.
- The Raw Transcript is the ONLY source. If you don't see candidate words in it, assign everything to "Interviewer" only.
- Interviewer = questions being asked. Interviewee = ONLY words the candidate actually said (from the transcript).

Task 2 (Tone): Analyze ONLY the Interviewee's actual responses (from transcript) for confidence and tone.
If there are no Interviewee segments, set confidence_rating to 1 and tone_analysis to "No candidate response detected."
{clarity_note}

Raw Transcript (this is the ONLY speech captured from the recording):
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

            # Validate: remove hallucinated interviewee segments (text must come from transcript)
            transcript_lower = transcript.lower()
            transcript_words = set(transcript_lower.split())
            validated = []
            for seg in formatted:
                text = (seg.get("text") or "").strip()
                speaker = seg.get("speaker") or "Interviewer"
                if speaker == "Interviewee" and text:
                    text_norm = " ".join(text.lower().split())
                    seg_words = [w for w in text_norm.split() if len(w) > 1]  # skip single chars
                    # Valid if: (a) exact substring, or (b) >=50% of words appear in transcript
                    exact_match = len(text_norm) <= 15 or text_norm in transcript_lower
                    word_overlap = (len(seg_words) >= 3 and
                        sum(1 for w in seg_words if w in transcript_words) / max(len(seg_words), 1) >= 0.5)
                    if len(text_norm) > 10 and not (exact_match or word_overlap):
                        validated.append({"speaker": "Interviewee", "text": "[No audible response]"})
                        print(f"[WARN] Removed hallucinated interviewee segment (not in transcript)")
                    else:
                        validated.append(seg)
                else:
                    validated.append(seg)
            formatted = validated

            # If no real interviewee content, override tone
            interviewee_words = sum(len(s.get("text", "").split()) for s in formatted if s.get("speaker") == "Interviewee" and "[No audible response]" not in (s.get("text") or ""))
            if interviewee_words == 0:
                tone_data = {
                    "confidence_rating": 1,
                    "tone_analysis": "No candidate response detected. Speak into the microphone when answering questions.",
                    "improvement_tip": "Ensure your microphone is working and that you are speaking when it's your turn to answer.",
                }
            else:
                tone_data = {
                    "confidence_rating": data.get("confidence_rating", 5),
                    "tone_analysis": data.get("tone_analysis", ""),
                    "improvement_tip": data.get("improvement_tip", ""),
                }
            tone_data["candidate_speech_detected"] = interviewee_words > 0
            tone_data["interviewee_word_count"] = interviewee_words
            tone_data["insufficient_candidate_speech"] = interviewee_words < 15
            if interviewee_words < 15 and interviewee_words > 0:
                tone_data["improvement_tip"] = "Very little speech was captured. Speak more when answering to get a meaningful evaluation."
            print(f"DEBUG: Combined call complete. Segments: {len(formatted)}, interviewee words: {interviewee_words}")
            return formatted, tone_data
        except Exception as e:
            print(f"Combined diarization+tone failed: {e}. Using fallback.")
            fallback_formatted = [{"speaker": "Interviewer", "text": transcript}]
            return fallback_formatted, {
                "confidence_rating": 5,
                "tone_analysis": "Evaluation unavailable.",
                "improvement_tip": "",
                "candidate_speech_detected": False,
                "interviewee_word_count": 0,
                "insufficient_candidate_speech": True,
            }

    def analyze_audio(self, audio_path: str, questions=None):
        self._ensure_loaded()  # Load model on first use
        
        if not SPEECH_LIBS_AVAILABLE or self.model is None:
            return {
                "error": "Speech analysis libraries not installed or model failed to load.",
                "transcript": "",
                "word_count": 0,
                "speaking_speed_wpm": 0,
                "filler_words_count": 0,
                "clarity_score": 5,
                "confidence_score": 5,
                "audio_duration_seconds": 0
            }

        audio_file = Path(audio_path).resolve()

        if not audio_file.exists():
            return {
                "error": f"Audio file does not exist: {audio_path}",
                "transcript": "",
                "word_count": 0,
                "speaking_speed_wpm": 0,
                "clarity_score": 5,
                "confidence_score": 5,
            }

        try:
            # Transcribe FULL audio (not just first 30s). For speed, set INTERVEUX_FAST_SPEECH=1 to use first 30s only.
            fast_speech = os.environ.get("INTERVEUX_FAST_SPEECH", "").strip().lower() in ("1", "true", "yes")
            if fast_speech:
                print("Transcribing with Whisper (fast mode: first 30s only)...")
                import numpy as np
                audio_data, sr = librosa.load(str(audio_file), sr=16000)
                duration = min(30.0, librosa.get_duration(y=audio_data, sr=sr))
                audio_np = whisper.pad_or_trim(audio_data.astype(np.float32))
                mel = whisper.log_mel_spectrogram(audio_np).to(self.model.device)
                try:
                    import torch
                    use_fp16 = torch.cuda.is_available() and str(self.model.device) != 'cpu'
                except ImportError:
                    use_fp16 = False
                result = whisper.decode(self.model, mel, whisper.DecodingOptions(fp16=use_fp16))
                transcript = (result.text or "").strip()
            else:
                print("Transcribing full audio with Whisper (this may take a while on CPU)...")
                # Load with librosa to avoid Whisper calling ffmpeg (WinError 2 on Windows if ffmpeg not in PATH)
                import numpy as np
                audio_data, sr = librosa.load(str(audio_file), sr=16000, mono=True)
                duration = librosa.get_duration(y=audio_data, sr=sr)
                audio_np = audio_data.astype(np.float32)
                try:
                    import torch
                    use_fp16 = torch.cuda.is_available() and str(self.model.device) != 'cpu'
                except ImportError:
                    use_fp16 = False
                result = self.model.transcribe(audio_np, language="en", verbose=False, fp16=use_fp16)
                transcript = (result.get("text") or "").strip()
                if duration <= 0 and result.get("segments"):
                    duration = max(s.get("end", 0) for s in result["segments"])
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

            # When insufficient candidate speech, don't show misleading clarity (from empty transcript)
            insufficient = tone_data.get("insufficient_candidate_speech", False)
            out_clarity = None if insufficient else clarity_score
            return {
                "transcript": transcript,
                "formatted_transcript": formatted_transcript,
                "word_count": word_count,
                "speaking_speed_wpm": speaking_wpm,
                "filler_words_count": filler_count,
                "clarity_score": out_clarity,
                "confidence_score": tone_data.get("confidence_rating", 5),
                "tone_analysis": tone_data.get("tone_analysis", ""),
                "improvement_tip": tone_data.get("improvement_tip", ""),
                "audio_duration_seconds": round(duration, 2),
                "candidate_speech_detected": tone_data.get("candidate_speech_detected", True),
                "interviewee_word_count": tone_data.get("interviewee_word_count", 0),
                "insufficient_candidate_speech": insufficient,
            }

        except Exception as e:
            return {
                "error": str(e),
                "transcript": "",
                "word_count": 0,
                "speaking_speed_wpm": 0,
                "filler_words_count": 0,
                "clarity_score": 5,
                "confidence_score": 5,
                "tone_analysis": "",
                "improvement_tip": "",
                "audio_duration_seconds": 0,
            }
