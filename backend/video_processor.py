import os
import cv2
import tempfile
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from modules.report_builder import save_html_report
from modules.emotion_vit import analyze_emotions_vit
from modules.body_language import BodyLanguageAnalyzer
from modules.audio_extractor import extract_audio
from modules.speech_analysis import SpeechAnalyzer


def extract_frames(video_path, output_dir, fps=1):
    """
    Extract frames at a given FPS. 
    Sequential reading is used because seeking (CAP_PROP_POS_FRAMES) 
    is often unreliable with browser-recorded WebM files.
    """
    os.makedirs(output_dir, exist_ok=True)

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
    max_to_save = 60
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


def run_emotion_analysis(frames_dir):
    return analyze_emotions_vit(frames_dir)


def run_body_language_analysis(frames_dir, subsample_step=2):
    from modules.body_language import _get_body_analyzer
    return _get_body_analyzer().analyze_video(frames_dir, subsample_step=subsample_step)


# Shared SpeechAnalyzer (reuse across analyses)
_speech_analyzer = None

def _get_speech_analyzer():
    global _speech_analyzer
    if _speech_analyzer is None:
        _speech_analyzer = SpeechAnalyzer()
    return _speech_analyzer

def run_speech_analysis(audio_path, questions=None):
    return _get_speech_analyzer().analyze_audio(audio_path, questions)


def build_final_report(emotion, body, speech, audio_path):
    return {
        "emotion_analysis": emotion,
        "body_language": body,
        "speech_analysis": speech,
        "audio_file": audio_path,
        "final_summary": {
            "dominant_emotion": emotion.get("dominant_emotion"),
            "gesture_label": body.get("gesture_label"),
            "posture_score": body.get("posture_score"),
            "movement_score": body.get("movement_score"),
            "speaking_speed_wpm": speech.get("speaking_speed_wpm"),
            "clarity_score": speech.get("clarity_score"),
            "confidence_score": speech.get("confidence_score"),
            "tone_analysis": speech.get("tone_analysis"),
            "improvement_tip": speech.get("improvement_tip")
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
    _get_speech_analyzer()._ensure_model_loaded()

    # Parallel analysis: speech, emotion, body (all independent after extraction)
    speech = None
    emotion_data = None
    body_data = None

    def run_speech():
        if not audio_path or not Path(audio_path).exists():
            return {
                "error": "No audio extracted",
                "transcript": "",
                "word_count": 0,
                "speaking_speed_wpm": 0,
                "clarity_score": 0,
                "confidence_score": 0,
            }
        return run_speech_analysis(audio_path, questions)

    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {
            ex.submit(run_speech): "speech",
            ex.submit(run_emotion_analysis, str(frames_dir)): "emotion",
            ex.submit(run_body_language_analysis, str(frames_dir)): "body",
        }
        for fut in as_completed(futures):
            key = futures[fut]
            try:
                result = fut.result()
                if key == "speech":
                    speech = result
                elif key == "emotion":
                    emotion_data = result
                else:
                    body_data = result
            except Exception as e:
                print(f"[ERROR] {key} failed: {e}")
                if key == "speech":
                    speech = {"error": str(e), "transcript": "", "word_count": 0, "speaking_speed_wpm": 0, "clarity_score": 0, "confidence_score": 0}
                elif key == "emotion":
                    emotion_data = {"dominant_emotion": "Neutral", "emotion_counts": {}, "frames_analyzed": 0}
                else:
                    body_data = {"posture_score": 0, "movement_score": 0, "gesture_label": "Analysis failed"}

    if speech is None:
        speech = {"error": "Speech analysis failed", "transcript": "", "word_count": 0, "speaking_speed_wpm": 0, "clarity_score": 0, "confidence_score": 0}
    if emotion_data is None:
        emotion_data = {"dominant_emotion": "Neutral", "emotion_counts": {}, "frames_analyzed": 0}
    if body_data is None:
        body_data = {"posture_score": 0, "movement_score": 0, "gesture_label": "Analysis failed"}

    update_progress(90, "Generating final report and insights...")
    print("[STEP] Creating final report...")
    report = build_final_report(emotion_data, body_data, speech, str(audio_path))

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

    return {
    "report": report,
    "report_json_path": str(json_path),
    "report_html_path": str(html_path)
    }