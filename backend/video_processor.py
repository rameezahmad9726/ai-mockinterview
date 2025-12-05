import os
import cv2
import tempfile
import json
from pathlib import Path

from modules.report_builder import save_html_report
from modules.emotion_vit import analyze_emotions_vit
from modules.body_language import BodyLanguageAnalyzer
from modules.audio_extractor import extract_audio
from modules.speech_analysis import SpeechAnalyzer


def extract_frames(video_path, output_dir, fps=1):
    """Extract frames at a given FPS using OpenCV."""
    os.makedirs(output_dir, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    frame_rate = cap.get(cv2.CAP_PROP_FPS)
    interval = max(int(frame_rate / fps), 1)

    frame_count = 0
    saved = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_count % interval == 0:
            cv2.imwrite(os.path.join(output_dir, f"frame_{saved}.jpg"), frame)
            saved += 1

        frame_count += 1

    cap.release()
    return saved


def run_emotion_analysis(frames_dir):
    return analyze_emotions_vit(frames_dir)


def run_body_language_analysis(frames_dir):
    analyzer = BodyLanguageAnalyzer()
    return analyzer.analyze_video(frames_dir)


def run_speech_analysis(audio_path):
    analyzer = SpeechAnalyzer()
    return analyzer.analyze_audio(audio_path)


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
        }
    }


def process_video(video_path):

    temp_root = Path(tempfile.mkdtemp())
    frames_dir = temp_root / "frames"
    audio_dir = temp_root / "audio"

    frames_dir.mkdir(exist_ok=True)
    audio_dir.mkdir(exist_ok=True)

    print("📸 Extracting frames…")
    extract_frames(video_path, str(frames_dir))

    print("🎵 Extracting audio…")
    audio_path = extract_audio(video_path, audio_dir)

    # -------------------------
    # Handle missing audio
    # -------------------------
    if not audio_path or not Path(audio_path).exists():
        print("⚠️ No audio extracted — skipping speech analysis")
        speech = {
            "error": "No audio extracted",
            "transcript": "",
            "word_count": 0,
            "speaking_speed_wpm": 0,
            "clarity_score": 0,
            "confidence_score": 0,
        }
    else:
        print("🎤 Running speech analysis…")
        speech = run_speech_analysis(audio_path)

    print("😃 Running emotion analysis…")
    emotion_data = run_emotion_analysis(str(frames_dir))

    print("🧍 Running body language analysis…")
    body_data = run_body_language_analysis(str(frames_dir))

    print("📄 Creating final report…")
    report = build_final_report(emotion_data, body_data, speech, str(audio_path))

    # ---------------------------------------------------
    # Save JSON + HTML
    # ---------------------------------------------------

    reports_dir = Path(__file__).resolve().parent / "reports"
    reports_dir.mkdir(exist_ok=True)

    base_name = Path(video_path).stem.replace(" ", "_")
    json_path = reports_dir / f"{base_name}.json"
    html_path = reports_dir / f"{base_name}.html"

    # Save JSON
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=4)

    print(f"✅ JSON saved → {json_path}")

    # Save HTML
    try:
        save_html_report(report, html_path)
        print(f"📄 HTML saved → {html_path}")
        report["report_html_path"] = str(html_path)
    except Exception as e:
        print("❌ HTML generation failed:", e)
        report["report_html_path"] = None

    report["report_json_path"] = str(json_path)
    report["report_html_path"] = str(html_path)

    return {
    "report": report,
    "report_json_path": str(json_path),
    "report_html_path": str(html_path)
    }