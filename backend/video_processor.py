import os
import tempfile
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from modules.report_builder import save_html_report
from modules.audio_extractor import extract_audio
from modules.speech_analysis import SpeechAnalyzer
from modules.behavior_analysis import build_behavior_insights
from modules.model_inference.behavior_fusion import infer_behavior_confidence
from modules.model_inference.speech_scorer import infer_speech_clarity
from modules.training_data_logger import build_training_row, append_training_row_jsonl

# Speed vs quality: fewer frames + higher subsample = faster analysis (slightly less accurate)
MAX_FRAMES = int(os.environ.get("INTERVEUX_MAX_FRAMES", "20"))  # default 20 for speed (raise for more coverage)
SUBSAMPLE_STEP = int(os.environ.get("INTERVEUX_SUBSAMPLE_STEP", "4"))  # process every Nth frame (4 = faster)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def extract_frames(video_path, output_dir, fps=1):
    """
    Extract frames at a given FPS. 
    Sequential reading is used because seeking (CAP_PROP_POS_FRAMES) 
    is often unreliable with browser-recorded WebM files.
    """
    os.makedirs(output_dir, exist_ok=True)
    try:
        import cv2
    except Exception as e:
        print(f"[WARN] OpenCV unavailable, skipping frame extraction: {e}")
        return 0

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        # Avoid non-ASCII characters that break Windows consoles
        print(f"[ERROR] Could not open video file: {video_path}")
        return 0
        
    source_fps = cap.get(cv2.CAP_PROP_FPS)
    if source_fps <= 0:
        source_fps = 30 # Fallback
    
    interval = max(int(source_fps / fps), 1)
    
    saved = 0
    max_to_save = MAX_FRAMES
    current_frame = 0

    print(f"[INFO] Starting frame extraction (Source FPS: {source_fps}, Interval: {interval})")

    while saved < max_to_save:
        ret, frame = cap.read()
        if not ret:
            break
            
        if current_frame % interval == 0:
            # Resize for speed; lower JPEG quality (85) for faster I/O
            frame_small = cv2.resize(frame, (320, 240))
            path = os.path.join(output_dir, f"frame_{saved}.jpg")
            cv2.imwrite(path, frame_small, [cv2.IMWRITE_JPEG_QUALITY, 85])
            saved += 1
            
        current_frame += 1

    cap.release()
    print(f"[INFO] Extracted {saved} frames total.")
    return saved


def run_emotion_analysis(frames_dir, subsample_step=None):
    if subsample_step is None:
        subsample_step = SUBSAMPLE_STEP
    try:
        from modules.emotion_vit import analyze_emotions_vit
        return analyze_emotions_vit(frames_dir, subsample_step=subsample_step)
    except Exception as e:
        print(f"[WARN] Emotion analysis unavailable: {e}")
        return {
            "dominant_emotion": "Neutral",
            "emotion_counts": {},
            "emotion_history": [],
            "emotion_per_frame": [],
            "frames_analyzed": 0,
            "error": str(e),
        }


def run_body_language_analysis(frames_dir, subsample_step=None):
    if subsample_step is None:
        subsample_step = SUBSAMPLE_STEP
    try:
        from modules.body_language import _get_body_analyzer
        return _get_body_analyzer().analyze_video(frames_dir, subsample_step=subsample_step)
    except Exception as e:
        print(f"[WARN] Body language analysis unavailable: {e}")
        return {
            "posture_score": 0,
            "movement_score": 0,
            "gesture_label": "Body analysis unavailable in current environment",
            "posture_per_frame": [],
            "error": str(e),
        }


def run_eye_contact_analysis(frames_dir, subsample_step=None):
    """Per-frame eye contact via MediaPipe Face Mesh (same subsample as emotion/body)."""
    if subsample_step is None:
        subsample_step = SUBSAMPLE_STEP
    try:
        from modules.eye_contact import analyze_eye_contact_frames_dir
        return analyze_eye_contact_frames_dir(str(frames_dir), subsample_step=subsample_step)
    except Exception as e:
        print(f"[WARN] Eye contact analysis unavailable: {e}")
        return {
            "eye_contact_per_frame": [],
            "avg_eye_contact": 0.0,
            "frames_analyzed": 0,
            "eye_contact_available": False,
            "error": str(e),
        }


# Shared SpeechAnalyzer (reuse across analyses)
_speech_analyzer = None

def _get_speech_analyzer():
    global _speech_analyzer
    if _speech_analyzer is None:
        _speech_analyzer = SpeechAnalyzer()
    return _speech_analyzer

def run_speech_analysis(audio_path, questions=None):
    return _get_speech_analyzer().analyze_audio(audio_path, questions)


def _compute_recommendation(emotion, body, speech, c_score, conf_score):
    """Compute detailed recommendation with specific strengths and areas to improve."""
    insufficient = speech.get("insufficient_candidate_speech") or speech.get("candidate_speech_detected") is False
    # If no or insufficient candidate speech (user didn't answer / barely participated), always Not Recommended
    if insufficient:
        return {
            "recommended": False,
            "label": "Not Recommended",
            "reason": "No candidate response detected. Speak into the microphone when answering questions.",
            "summary": "No audible candidate speech was captured. Ensure your microphone is on and that you speak when answering.",
            "strengths": [],
            "areas_to_improve": [
                {
                    "metric": "Response",
                    "score": None,
                    "feedback": "No candidate answers were detected in the recording.",
                    "suggestion": "Speak clearly when it's your turn to answer. Check that your microphone is working and not muted.",
                }
            ],
        }

    posture = body.get("posture_score")
    if posture is None:
        posture = 0
    gesture = (body.get("gesture_label") or "").lower()
    filler = speech.get("filler_words_count") or speech.get("filler_words") or 0
    wpm = speech.get("speaking_speed_wpm") or 0
    dominant_emotion = (emotion.get("dominant_emotion") or "").strip()

    # Build detailed breakdown for each metric
    strengths = []
    areas_to_improve = []

    # Clarity (0-10) - skip when insufficient (c_score can be None)
    if speech.get("insufficient_candidate_speech"):
        pass  # Don't add Clarity when insufficient - would be misleading
    elif c_score is not None and c_score >= 8:
        strengths.append({
            "metric": "Clarity",
            "score": c_score,
            "feedback": f"Excellent clarity ({c_score}/10). Speech was articulate and easy to follow.",
        })
    elif c_score is not None and c_score >= 6:
        strengths.append({
            "metric": "Clarity",
            "score": c_score,
            "feedback": f"Good clarity ({c_score}/10). Consider enunciating more clearly for complex points.",
        })
    elif c_score is not None:
        areas_to_improve.append({
            "metric": "Clarity",
            "score": c_score,
            "feedback": f"Clarity score {c_score}/10 is below target.",
            "suggestion": "Speak more slowly, pause between key points, and avoid mumbling. Practice articulating technical terms.",
        })

    # Confidence (0-10)
    if conf_score >= 8:
        strengths.append({
            "metric": "Confidence",
            "score": conf_score,
            "feedback": f"Strong confidence ({conf_score}/10). Delivery was assured and professional.",
        })
    elif conf_score >= 6:
        strengths.append({
            "metric": "Confidence",
            "score": conf_score,
            "feedback": f"Decent confidence ({conf_score}/10). Use more assertive language and fewer hedging phrases.",
        })
    else:
        areas_to_improve.append({
            "metric": "Confidence",
            "score": conf_score,
            "feedback": f"Confidence score {conf_score}/10 needs improvement.",
            "suggestion": "Avoid phrases like 'I think', 'maybe', 'kind of'. State your points directly. Maintain steady eye contact.",
        })

    # Posture (0-10) - skip body-based strengths when insufficient (misleading to say "excellent posture" when user didn't speak)
    if speech.get("insufficient_candidate_speech"):
        pass  # Don't add Posture/Gestures as strengths when insufficient
    elif posture >= 8:
        strengths.append({
            "metric": "Posture",
            "score": posture,
            "feedback": f"Excellent posture ({posture}/10). Upright, professional presence.",
        })
    elif posture >= 6:
        strengths.append({
            "metric": "Posture",
            "score": posture,
            "feedback": f"Good posture ({posture}/10). Keep shoulders level and avoid slouching.",
        })
    elif posture > 0:
        areas_to_improve.append({
            "metric": "Posture",
            "score": posture,
            "feedback": f"Posture score {posture}/10. Shoulders may be uneven or slouched.",
            "suggestion": "Sit up straight, keep shoulders level, and face the camera directly. Ensure upper body is visible.",
        })

    # Gesture / Body language
    if "excessive hand movement" in gesture:
        areas_to_improve.append({
            "metric": "Gestures",
            "score": None,
            "feedback": "Excessive hand movement detected.",
            "suggestion": "Use controlled, purposeful gestures. Rest hands on the desk when not emphasizing a point. Avoid fidgeting.",
        })
    elif "very still" in gesture or "stiff" in gesture:
        areas_to_improve.append({
            "metric": "Gestures",
            "score": None,
            "feedback": "Very limited movement; may appear stiff.",
            "suggestion": "Add natural hand gestures to emphasize key points. Relax your shoulders and vary your expression.",
        })
    elif "normal" in gesture or "controlled" in gesture:
        strengths.append({
            "metric": "Gestures",
            "score": None,
            "feedback": "Natural, controlled body language. Gestures supported your message well.",
        })

    # Filler words
    if filler > 10:
        areas_to_improve.append({
            "metric": "Filler words",
            "score": filler,
            "feedback": f"{filler} filler words (um, uh, like) detected.",
            "suggestion": "Pause briefly instead of using fillers. Practice speaking with deliberate pauses. Record yourself to build awareness.",
        })
    elif filler > 0:
        strengths.append({
            "metric": "Filler words",
            "score": filler,
            "feedback": f"Low filler usage ({filler} detected). Speech was mostly fluent.",
        })

    # Speaking speed (context: 120-180 WPM is typical for interviews) - skip when insufficient (WPM is from full transcript, not candidate)
    interviewee_words = speech.get("interviewee_word_count", 0)
    if speech.get("insufficient_candidate_speech") or interviewee_words < 15:
        pass  # Don't add Speaking pace feedback when insufficient - WPM would be misleading
    elif 100 <= wpm <= 180 and wpm > 0:
        strengths.append({
            "metric": "Speaking pace",
            "score": wpm,
            "feedback": f"Appropriate speaking pace ({wpm:.0f} WPM). Easy to follow.",
        })
    elif not insufficient and wpm > 180:
        areas_to_improve.append({
            "metric": "Speaking pace",
            "score": wpm,
            "feedback": f"Speaking speed ({wpm:.0f} WPM) may be too fast.",
            "suggestion": "Slow down for important points. Pause after key statements to let them land.",
        })
    elif not insufficient and 0 < wpm < 100:
        areas_to_improve.append({
            "metric": "Speaking pace",
            "score": wpm,
            "feedback": f"Speaking speed ({wpm:.0f} WPM) may be too slow.",
            "suggestion": "Practice concise answers. Avoid long pauses that can suggest uncertainty.",
        })

    # Emotion (optional insight)
    if dominant_emotion and dominant_emotion.lower() in ("neutral", "happy", "surprise"):
        strengths.append({
            "metric": "Emotion",
            "score": None,
            "feedback": f"Displayed {dominant_emotion} expression—appropriate for an interview setting.",
        })

    # Overall verdict
    positive_count = len([s for s in strengths if s["metric"] in ("Clarity", "Confidence", "Posture")])
    critical_issues = len([a for a in areas_to_improve if a["metric"] in ("Clarity", "Confidence")])
    recommended = positive_count >= 2 and critical_issues == 0

    # Summary text
    if recommended:
        reason = "Overall strong performance. " + " ".join(s["feedback"] for s in strengths[:3])
        if areas_to_improve:
            reason += " Minor improvements possible in " + ", ".join(a["metric"].lower() for a in areas_to_improve[:2]) + "."
    else:
        reason = "Key areas need improvement before recommendation. " + " ".join(
            a["feedback"] for a in areas_to_improve[:3]
        )

    return {
        "recommended": recommended,
        "label": "Recommended" if recommended else "Not Recommended",
        "reason": reason,
        "strengths": strengths,
        "areas_to_improve": areas_to_improve,
        "summary": "Strong candidate with professional delivery." if recommended else "Focus on the areas below to strengthen your interview performance.",
    }


def build_final_report(emotion, body, speech, audio_path):
    # Use 5 as neutral default for scores when missing (avoid showing 0/10 for failed steps)
    # When insufficient candidate speech, keep clarity/confidence as None so frontend shows N/A
    insufficient = speech.get("insufficient_candidate_speech") or speech.get("candidate_speech_detected") is False
    c_score = speech.get("clarity_score")
    conf_score = speech.get("confidence_score")
    if c_score is None and not insufficient:
        c_score = 5
    if conf_score is None and not insufficient:
        conf_score = 5
    if insufficient:
        c_score = None
        conf_score = None

    recommendation = _compute_recommendation(emotion, body, speech, c_score or 5, conf_score or 5)

    return {
        "emotion_analysis": emotion,
        "body_language": body,
        "speech_analysis": speech,
        "audio_file": audio_path,
        "final_summary": {
            "dominant_emotion": emotion.get("dominant_emotion"),
            "gesture_label": body.get("gesture_label") or "—",
            "posture_score": body.get("posture_score"),
            "movement_score": body.get("movement_score"),
            "speaking_speed_wpm": None if insufficient else speech.get("speaking_speed_wpm"),
            "clarity_score": c_score,
            "confidence_score": conf_score,
            "insufficient_candidate_speech": insufficient,
            "tone_analysis": speech.get("tone_analysis"),
            "improvement_tip": speech.get("improvement_tip"),
            "recommendation": recommendation,
        }
    }


def process_video(video_path, session_id=None, questions=None, on_progress=None):
    def update_progress(percent, message):
        if on_progress:
            on_progress(percent, message)

    temp_root = Path(tempfile.mkdtemp())
    frames_dir = temp_root / "frames"
    audio_dir = temp_root / "audio"

    frames_dir.mkdir(exist_ok=True)
    audio_dir.mkdir(exist_ok=True)

    # Parallel extraction: frames + audio
    update_progress(10, "Extracting frames and audio...")
    print("[STEP] Extracting frames and audio in parallel...")
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_frames = ex.submit(extract_frames, video_path, str(frames_dir))
        f_audio = ex.submit(extract_audio, video_path, audio_dir)
        f_frames.result()
        audio_path = f_audio.result()
    update_progress(35, "Extraction complete, analyzing...")

    # Load speech model on main thread first (Whisper can fail when loaded from worker threads)
    update_progress(38, "Loading speech model...")
    _get_speech_analyzer()._ensure_model_loaded()

    # Parallel analysis: speech, emotion, body, eye contact (independent after extraction)
    speech = None
    emotion_data = None
    body_data = None
    eye_data = None
    completed = 0
    _progress_steps = [
        (48, "Analyzing... (1/4)"),
        (58, "Analyzing... (2/4)"),
        (68, "Analyzing... (3/4)"),
        (78, "Analyzing... (4/4)"),
    ]

    def run_speech():
        if not audio_path or not Path(audio_path).exists():
            return {
                "error": "No audio extracted",
                "transcript": "",
                "word_count": 0,
                "speaking_speed_wpm": 0,
                "clarity_score": 5,
                "confidence_score": 5,
            }
        return run_speech_analysis(audio_path, questions)

    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {
            ex.submit(run_speech): "speech",
            ex.submit(run_emotion_analysis, str(frames_dir), SUBSAMPLE_STEP): "emotion",
            ex.submit(run_body_language_analysis, str(frames_dir), SUBSAMPLE_STEP): "body",
            ex.submit(run_eye_contact_analysis, str(frames_dir), SUBSAMPLE_STEP): "eye",
        }
        for fut in as_completed(futures):
            key = futures[fut]
            if completed < len(_progress_steps):
                pct, msg = _progress_steps[completed]
                update_progress(pct, msg)
                completed += 1
            try:
                result = fut.result()
                if key == "speech":
                    speech = result
                elif key == "emotion":
                    emotion_data = result
                elif key == "body":
                    body_data = result
                else:
                    eye_data = result
            except Exception as e:
                print(f"[ERROR] {key} failed: {e}")
                if key == "speech":
                    speech = {"error": str(e), "transcript": "", "word_count": 0, "speaking_speed_wpm": 0, "clarity_score": 5, "confidence_score": 5}
                elif key == "emotion":
                    emotion_data = {
                        "dominant_emotion": "Neutral",
                        "emotion_counts": {},
                        "frames_analyzed": 0,
                        "emotion_per_frame": [],
                    }
                elif key == "body":
                    body_data = {
                        "posture_score": 0,
                        "movement_score": 0,
                        "gesture_label": "Pose not detected (ensure upper body visible)",
                        "posture_per_frame": [],
                    }
                else:
                    eye_data = {
                        "eye_contact_per_frame": [],
                        "avg_eye_contact": 0.0,
                        "frames_analyzed": 0,
                        "eye_contact_available": False,
                    }

    if speech is None:
        speech = {"error": "Speech analysis failed", "transcript": "", "word_count": 0, "speaking_speed_wpm": 0, "clarity_score": 5, "confidence_score": 5}
    if emotion_data is None:
        emotion_data = {
            "dominant_emotion": "Neutral",
            "emotion_counts": {},
            "frames_analyzed": 0,
            "emotion_per_frame": [],
        }
    if body_data is None:
        body_data = {
            "posture_score": 0,
            "movement_score": 0,
            "gesture_label": "Analysis failed",
            "posture_per_frame": [],
        }
    if eye_data is None:
        eye_data = {
            "eye_contact_per_frame": [],
            "avg_eye_contact": 0.0,
            "frames_analyzed": 0,
            "eye_contact_available": False,
        }

    update_progress(90, "Generating final report and insights...")
    print("[STEP] Creating final report...")

    # Optional learned speech score (phase rollout, disabled by default).
    use_learned_speech = _env_bool("USE_LEARNED_SPEECH_MODEL", default=False)
    speech_inference = infer_speech_clarity(speech)
    if use_learned_speech and speech_inference.model_loaded and speech_inference.clarity_score is not None:
        speech["clarity_score"] = round(float(speech_inference.clarity_score), 2)

    report = build_final_report(emotion_data, body_data, speech, str(audio_path))

    behavior_insights = build_behavior_insights(emotion_data, body_data, eye_data)
    heuristic_behavior = dict(behavior_insights)

    # Optional learned behavior confidence score (phase rollout, disabled by default).
    use_learned_behavior = _env_bool("USE_LEARNED_BEHAVIOR_MODEL", default=False)
    dual_run = _env_bool("USE_DUAL_RUN_MODE", default=True)
    behavior_inference = infer_behavior_confidence(report, behavior_insights)
    if use_learned_behavior and behavior_inference.model_loaded and behavior_inference.confidence_score is not None:
        learned_conf_0_1 = max(0.0, min(1.0, behavior_inference.confidence_score / 10.0))
        behavior_insights["confidence_score"] = round(learned_conf_0_1, 3)
        report["final_summary"]["confidence_score"] = round(float(behavior_inference.confidence_score), 2)
        report["final_summary"]["recommendation"] = _compute_recommendation(
            emotion_data,
            body_data,
            speech,
            report["final_summary"].get("clarity_score") or 5,
            report["final_summary"].get("confidence_score") or 5,
        )

    report["behavior_insights"] = behavior_insights
    report["model_metadata"] = {
        "inference_mode": "learned" if (use_learned_behavior or use_learned_speech) else "heuristic",
        "flags": {
            "USE_LEARNED_BEHAVIOR_MODEL": use_learned_behavior,
            "USE_LEARNED_SPEECH_MODEL": use_learned_speech,
            "USE_DUAL_RUN_MODE": dual_run,
        },
        "behavior_model": {
            "model_version": behavior_inference.model_version,
            "model_loaded": behavior_inference.model_loaded,
            "error": behavior_inference.error,
        },
        "speech_model": {
            "model_version": speech_inference.model_version,
            "model_loaded": speech_inference.model_loaded,
            "error": speech_inference.error,
        },
    }
    if dual_run:
        report["model_metadata"]["dual_run"] = {
            "heuristic_behavior": heuristic_behavior,
            "learned_behavior_confidence_1_10": behavior_inference.confidence_score,
            "learned_speech_clarity_1_10": speech_inference.clarity_score,
        }

    # ---------------------------------------------------
    # Save JSON + HTML
    # ---------------------------------------------------

    reports_dir = Path(__file__).resolve().parent / "reports"
    reports_dir.mkdir(exist_ok=True)

    base_name = Path(video_path).stem.replace(" ", "_")
    if session_id:
        base_name = f"{session_id}_{base_name}"
    json_path = reports_dir / f"{base_name}.json"
    html_path = reports_dir / f"{base_name}.html"

    # Save JSON
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=4)

    print(f"[INFO] JSON saved to {json_path}")

    # Save HTML
    try:
        save_html_report(report, html_path)
        print(f"[INFO] HTML saved to {html_path}")
        report["report_html_path"] = str(html_path)
    except Exception as e:
        print("[ERROR] HTML generation failed:", e)
        report["report_html_path"] = None

    report["report_json_path"] = str(json_path)
    report["report_html_path"] = str(html_path)

    # Phase 0: continuously log training rows for future model iterations.
    if _env_bool("ENABLE_TRAINING_ROW_LOG", default=True):
        try:
            training_rows_dir = os.environ.get("TRAINING_ROWS_DIR", str(Path(__file__).resolve().parent / "training_rows"))
            training_rows_file = Path(training_rows_dir) / "interview_segments.jsonl"
            row_session_id = session_id if session_id else base_name
            training_row = build_training_row(report, session_id=row_session_id, segment_id="full_interview")
            append_training_row_jsonl(training_row, training_rows_file)
            report["training_row_log_path"] = str(training_rows_file)
        except Exception as e:
            print(f"[WARN] Failed to append training row log: {e}")

    return {
        "report": report,
        "report_json_path": str(json_path),
        "report_html_path": str(html_path),
        "confidence_score": behavior_insights["confidence_score"],
        "trend": behavior_insights["trend"],
        "feedback": behavior_insights["feedback"],
        "eye_contact_score": behavior_insights["eye_contact_score"],
    }