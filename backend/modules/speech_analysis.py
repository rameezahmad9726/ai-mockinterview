import os
import json
from pathlib import Path


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _use_openai_whisper_api() -> bool:
    """Use OpenAI audio transcription (fast on CPU laptops); set INTERVEUX_OPENAI_WHISPER=false for local tiny."""
    raw = os.environ.get("INTERVEUX_OPENAI_WHISPER", "true")
    if raw is None or str(raw).strip() == "":
        return True
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


# OpenAI diarization + tone (default on for split Q/A transcript; set ENABLE_TONE_ANALYSIS=false to skip ~5–15s API call)
DIARIZATION_TRANSCRIPT_CHARS = int(os.environ.get("INTERVEUX_DIARIZATION_TRANSCRIPT_CHARS", "48000"))

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

                old = ssl._create_default_https_context
                try:
                    ssl._create_default_https_context = ssl._create_unverified_context
                    self.model = whisper.load_model(self.model_name)
                finally:
                    ssl._create_default_https_context = old
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

    @staticmethod
    def _normalize_speaker_label(raw: str) -> str:
        r = (raw or "").strip().lower()
        if r in ("interviewee", "candidate", "respondent", "applicant", "speaker_1", "speaker b"):
            return "Interviewee"
        return "Interviewer"

    @staticmethod
    def _normalize_formatted(formatted: list) -> list:
        out = []
        for seg in formatted or []:
            if not isinstance(seg, dict):
                continue
            row = dict(seg)
            row["speaker"] = SpeechAnalyzer._normalize_speaker_label(row.get("speaker", ""))
            out.append(row)
        return out

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

        snippet = transcript[:DIARIZATION_TRANSCRIPT_CHARS]
        truncated = len(transcript) > len(snippet)
        trunc_note = ""
        if truncated:
            trunc_note = (
                f"\nNOTE: Only the first {len(snippet)} characters of the transcript are shown below "
                "(full audio was longer). Segment exactly this excerpt; do not invent text beyond it.\n"
            )

        prompt = f"""
Task 1 (Diarization): Segment the raw transcript into alternating "Interviewer" and "Interviewee" turns.
Context: {context_prompt}
{trunc_note}

CRITICAL RULES - DO NOT VIOLATE:
- Use ONLY the exact words that appear in the Raw Transcript. Copy them verbatim (no paraphrase).
- Interviewer = scheduled questions, setup, and follow-ups from the interviewer.
- Interviewee = the candidate's spoken answers only (verbatim from the transcript).
- When a question ends and the candidate begins answering, START A NEW "Interviewee" segment for that answer.
- Do NOT put the entire recording into a single "Interviewer" block if the candidate clearly speaks between questions.
- If the candidate truly never spoke, use only "Interviewer" segments.

Task 2 (Tone): Analyze ONLY the Interviewee's actual responses for confidence and tone.
If there are no Interviewee segments, set confidence_rating to 1 and tone_analysis to "No candidate response detected."
{clarity_note}

Raw Transcript (ONLY source for diarization):
\"\"\"{snippet}\"\"\"

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
                        print("[WARN] Removed hallucinated interviewee segment (not in transcript)")
                    else:
                        validated.append(seg)
                else:
                    validated.append(seg)
            formatted = SpeechAnalyzer._normalize_formatted(validated)

            # If no real interviewee content, override tone — unless Whisper heard speech
            word_count = len(transcript.split())
            interviewee_words = sum(
                len(s.get("text", "").split())
                for s in formatted
                if s.get("speaker") == "Interviewee"
                and "[no audible response]" not in (s.get("text") or "").lower()
            )
            heard_enough = word_count >= 15
            if interviewee_words == 0 and not heard_enough:
                tone_data = {
                    "confidence_rating": 1,
                    "tone_analysis": "No candidate response detected. Speak into the microphone when answering questions.",
                    "improvement_tip": "Ensure your microphone is working and that you are speaking when it's your turn to answer.",
                }
            elif interviewee_words == 0 and heard_enough:
                tone_data = {
                    "confidence_rating": data.get("confidence_rating", 5),
                    "tone_analysis": data.get("tone_analysis", "") or "Speech was captured; per-question attribution uses answer timestamps.",
                    "improvement_tip": data.get("improvement_tip", ""),
                    "diarization_degraded": True,
                }
            else:
                tone_data = {
                    "confidence_rating": data.get("confidence_rating", 5),
                    "tone_analysis": data.get("tone_analysis", ""),
                    "improvement_tip": data.get("improvement_tip", ""),
                }
            tone_data["candidate_speech_detected"] = interviewee_words > 0 or heard_enough
            tone_data["interviewee_word_count"] = interviewee_words
            tone_data["insufficient_candidate_speech"] = (interviewee_words < 15) and not heard_enough
            if heard_enough and interviewee_words < 15:
                tone_data["diarization_degraded"] = True
            elif interviewee_words < 15 and interviewee_words > 0:
                tone_data["improvement_tip"] = "Very little speech was captured. Speak more when answering to get a meaningful evaluation."
            print(f"DEBUG: Combined call complete. Segments: {len(formatted)}, interviewee words: {interviewee_words}")
            return formatted, tone_data
        except Exception as e:
            print(f"Combined diarization+tone failed: {e}. Using fallback.")
            fallback_formatted = SpeechAnalyzer._normalize_formatted(
                [{"speaker": "Interviewer", "text": transcript}]
            )
            wc = len((transcript or "").split())
            return fallback_formatted, {
                "confidence_rating": 5,
                "tone_analysis": "Evaluation unavailable.",
                "improvement_tip": "",
                "candidate_speech_detected": wc >= 15,
                "interviewee_word_count": 0,
                "insufficient_candidate_speech": wc < 15,
                "diarization_degraded": wc >= 15,
            }

    def _transcribe_openai_whisper(self, audio_file: Path):
        """Transcribe interview audio via OpenAI (whisper-1). Expects 16 kHz mono WAV from extract_audio."""
        import wave
        from modules.question_generator import _get_client

        client = _get_client()
        if not hasattr(client, "audio") or not hasattr(client.audio, "transcriptions"):
            raise RuntimeError("OpenAI SDK too old: need v1 client with audio.transcriptions.create")
        model = os.environ.get("OPENAI_WHISPER_MODEL", "whisper-1")
        with audio_file.open("rb") as fh:
            resp = client.audio.transcriptions.create(
                model=model,
                file=fh,
                language="en",
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )
        text = (getattr(resp, "text", None) or "").strip()
        segments = []
        for seg in getattr(resp, "segments", None) or []:
            seg_text = (getattr(seg, "text", None) or "").strip()
            if not seg_text:
                continue
            segments.append({
                "start": float(getattr(seg, "start", 0) or 0),
                "end": float(getattr(seg, "end", 0) or 0),
                "text": seg_text,
            })
        with wave.open(str(audio_file), "rb") as w:
            rate = float(w.getframerate() or 16000)
            duration = w.getnframes() / rate if rate > 0 else 0.0
        if duration <= 0 and segments:
            duration = float(max(s.get("end", 0) for s in segments))
        return text, float(duration), segments

    def analyze_audio(self, audio_path: str, questions=None):
        try:
            from modules.question_generator import _load_env_files

            _load_env_files()
        except Exception:
            pass

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
            fast_speech = os.environ.get("INTERVEUX_FAST_SPEECH", "").strip().lower() in ("1", "true", "yes")
            transcript = None
            duration = None
            transcript_segments: list = []

            if _use_openai_whisper_api() and not fast_speech:
                try:
                    transcript, duration, transcript_segments = self._transcribe_openai_whisper(audio_file)
                    print(
                        f"[INFO] Transcribed via OpenAI "
                        f"{os.environ.get('OPENAI_WHISPER_MODEL', 'whisper-1')} (set INTERVEUX_OPENAI_WHISPER=false for local CPU Whisper)."
                    )
                except Exception as e:
                    print(f"[WARN] OpenAI transcription failed ({e}); falling back to local Whisper.")

            if transcript is None:
                self._ensure_loaded()
                if not SPEECH_LIBS_AVAILABLE or self.model is None:
                    return {
                        "error": "Speech analysis unavailable (OpenAI transcription failed and local Whisper is missing or did not load).",
                        "transcript": "",
                        "word_count": 0,
                        "speaking_speed_wpm": 0,
                        "filler_words_count": 0,
                        "clarity_score": 5,
                        "confidence_score": 5,
                        "audio_duration_seconds": 0,
                    }

                import numpy as np
                try:
                    import torch
                    use_fp16 = torch.cuda.is_available() and str(self.model.device) != "cpu"
                except ImportError:
                    use_fp16 = False

                if fast_speech:
                    print("Transcribing with Whisper (fast mode: first ~30s, via transcribe)...")
                    audio_data, sr = librosa.load(str(audio_file), sr=16000, mono=True, duration=30.0)
                    duration = float(librosa.get_duration(y=audio_data, sr=sr))
                    audio_np = audio_data.astype(np.float32)
                    result = self.model.transcribe(audio_np, language="en", verbose=False, fp16=use_fp16)
                    transcript = (result.get("text") or "").strip()
                    transcript_segments = [
                        {
                            "start": float(s.get("start", 0) or 0),
                            "end": float(s.get("end", 0) or 0),
                            "text": (s.get("text") or "").strip(),
                        }
                        for s in (result.get("segments") or [])
                        if (s.get("text") or "").strip()
                    ]
                    if duration <= 0 and result.get("segments"):
                        duration = float(max(s.get("end", 0) for s in result["segments"]))
                else:
                    print("Transcribing full audio with local Whisper tiny (slow on CPU; use OpenAI API by default)...")
                    audio_data, sr = librosa.load(str(audio_file), sr=16000, mono=True)
                    duration = float(librosa.get_duration(y=audio_data, sr=sr))
                    audio_np = audio_data.astype(np.float32)
                    result = self.model.transcribe(audio_np, language="en", verbose=False, fp16=use_fp16)
                    transcript = (result.get("text") or "").strip()
                    transcript_segments = [
                        {
                            "start": float(s.get("start", 0) or 0),
                            "end": float(s.get("end", 0) or 0),
                            "text": (s.get("text") or "").strip(),
                        }
                        for s in (result.get("segments") or [])
                        if (s.get("text") or "").strip()
                    ]
                    if duration <= 0 and result.get("segments"):
                        duration = float(max(s.get("end", 0) for s in result["segments"]))

            print(f"DEBUG: RAW TRANSCRIPT: {transcript}")
            words = transcript.split()
            word_count = len(words)

            speaking_wpm = round((word_count / duration) * 60, 2) if duration > 0 else 0

            filler_words = [w for w in words if w.lower() in ["um", "uh", "like", "you know"]]
            filler_count = len(filler_words)

            clarity_score = round(max(3.0, 10 - filler_count * 0.5), 2)

            if _env_bool("ENABLE_TONE_ANALYSIS", default=True):
                formatted_transcript, tone_data = self._diarize_and_analyze_tone(
                    transcript, questions=questions, clarity_score=clarity_score, filler_count=filler_count
                )
            else:
                # No fake speaker labels — UI shows plain transcript block (same as report_builder fallback).
                formatted_transcript = []
                tone_data = {
                    "confidence_rating": 5,
                    "tone_analysis": "",
                    "improvement_tip": "",
                    "tone_analysis_skipped": True,
                    "tone_skip_reason": (
                        "OpenAI diarization and tone were disabled (ENABLE_TONE_ANALYSIS is not true). "
                        "Set ENABLE_TONE_ANALYSIS=true in backend/.env and restart the API."
                    ),
                    "candidate_speech_detected": word_count >= 10,
                    "interviewee_word_count": 0,
                    "insufficient_candidate_speech": word_count < 15,
                }

            # When insufficient candidate speech, don't show misleading clarity (from empty transcript)
            insufficient = tone_data.get("insufficient_candidate_speech", False)
            out_clarity = None if insufficient else clarity_score
            out = {
                "transcript": transcript,
                "transcript_segments": transcript_segments,
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
            if tone_data.get("tone_analysis_skipped"):
                out["tone_analysis_skipped"] = True
                out["tone_skip_reason"] = tone_data.get("tone_skip_reason", "")
            return out

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
