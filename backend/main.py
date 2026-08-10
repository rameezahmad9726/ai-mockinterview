import asyncio
import os
print("Starting backend...")
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import json
import uuid
import shutil
import os

from modules.question_generator import generate_questions, extract_resume_context
from modules.tts import generate_speech, generate_speech_batch
from modules.training_data_logger import get_training_row_log_status

from db import init_db
from routes import admin as admin_routes
from routes import auth_routes
from routes import candidate as candidate_routes
from services.reminder_jobs import start_scheduler, stop_scheduler

app = FastAPI()


@app.on_event("startup")
def _on_startup() -> None:
    """Initialize the DB schema and start the background scheduler."""
    init_db()
    if os.environ.get("INTERVEUX_ENABLE_SCHEDULER", "true").strip().lower() in {"1", "true", "yes", "on"}:
        start_scheduler()


@app.on_event("shutdown")
def _on_shutdown() -> None:
    stop_scheduler()


app.include_router(auth_routes.router)
app.include_router(admin_routes.router)
app.include_router(candidate_routes.router)

# Allow frontend to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_ROOT = Path(__file__).resolve().parent / "uploads"
UPLOAD_ROOT.mkdir(exist_ok=True)

# Global store for tracking analysis progress
progress_store = {}

def _format_runtime_error(error: Exception) -> str:
    """
    Return a concise, user-friendly runtime error for UI display.

    Keeps full traceback in backend logs while avoiding huge raw dependency
    tracebacks in polling responses.
    """
    raw = str(error) or error.__class__.__name__
    text = raw.lower()
    if "application control policy has blocked this file" in text:
        return (
            "Video analysis is blocked by Windows Application Control on this machine "
            "(a required Python native module/DLL was blocked). Ask IT to allow "
            "NumPy/OpenCV/Pydantic binaries in the project venv, or run the backend in "
            "an unrestricted environment (WSL/Docker)."
        )
    if "importing the numpy c-extensions failed" in text or "_multiarray_umath" in text:
        return (
            "NumPy native extensions could not load, so video analysis cannot run in the "
            "current environment."
        )
    # Keep generic errors short enough for frontend alerts.
    return raw[:400]

@app.get("/analysis-status/{session_id}")
async def get_analysis_status(session_id: str):
    if session_id not in progress_store:
        return {"status": "error", "message": "Session not found"}
    return progress_store[session_id]

def run_analysis_task(video_path, session_id, parsed_questions, resume_context=None, answer_windows=None):
    try:
        from video_processor import process_video

        def on_progress(percent, message):
            progress_store[session_id]["progress"] = percent
            progress_store[session_id]["status"] = message

        result = process_video(
            str(video_path),
            session_id,
            parsed_questions,
            on_progress=on_progress,
            resume_context=resume_context,
            answer_windows=answer_windows,
        )
        
        progress_store[session_id]["progress"] = 100
        progress_store[session_id]["status"] = "Completed"
        progress_store[session_id]["result"] = result
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error in background task: {e}")
        progress_store[session_id]["status"] = "error"
        progress_store[session_id]["message"] = _format_runtime_error(e)

@app.post("/detect-faces")
async def detect_faces(file: UploadFile = File(...)):
    """
    Accepts a JPEG frame from the candidate's webcam and returns face count.
    Used for real-time multi_face / no_face detection in the live interview UI.
    """
    try:
        import cv2
        import numpy as np

        data = await file.read()
        arr = np.frombuffer(data, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return {"faces": -1, "error": "Could not decode image"}

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        f_cas = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        p_cas = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")

        ff = f_cas.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(35, 35))
        pf = p_cas.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(35, 35)) if not p_cas.empty() else []

        boxes = list(ff) + list(pf)
        if not p_cas.empty():
            flipped = cv2.flip(gray, 1)
            pf_flip = p_cas.detectMultiScale(flipped, scaleFactor=1.1, minNeighbors=4, minSize=(35, 35))
            for (x, y, w, h) in pf_flip:
                boxes.append((gray.shape[1] - x - w, y, w, h))

        if boxes:
            merged, _ = cv2.groupRectangles(boxes + boxes, 1, 0.3)
            face_count = int(len(merged))
        else:
            face_count = 0

        return {"faces": face_count}
    except Exception as e:
        return {"faces": -1, "error": str(e)}


@app.post("/analyze")
async def analyze_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    questions: str = Form(None),
    resume_context: str = Form(None),
    resume_session_id: str = Form(None),
    answer_windows: str = Form(None),
):
    """
    Upload a video → start background analysis → return session_id.

    Accepts optional `resume_context` (JSON) with keys:
        domain, certifications (list of {name, issuer, relevant}), key_skills.
    As a fallback, if `resume_session_id` is provided, the server looks up the
    saved context at uploads/<resume_session_id>/resume/context.json.
    """
    session_id = str(uuid.uuid4())
    session_dir = UPLOAD_ROOT / session_id
    original_dir = session_dir / "original"
    original_dir.mkdir(parents=True, exist_ok=True)

    video_path = original_dir / file.filename
    with open(video_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    parsed_questions = json.loads(questions) if questions else []

    parsed_context = None
    if resume_context:
        try:
            parsed_context = json.loads(resume_context)
        except Exception as e:
            print(f"[WARN] Could not parse resume_context: {e}")
            parsed_context = None
    if parsed_context is None and resume_session_id:
        ctx_path = UPLOAD_ROOT / resume_session_id / "resume" / "context.json"
        if ctx_path.exists():
            try:
                with ctx_path.open("r", encoding="utf-8") as fh:
                    parsed_context = json.load(fh)
            except Exception as e:
                print(f"[WARN] Could not load resume context from {ctx_path}: {e}")

    parsed_windows = None
    if answer_windows:
        try:
            raw = json.loads(answer_windows)
            if isinstance(raw, list):
                parsed_windows = []
                for w in raw:
                    try:
                        parsed_windows.append({
                            "question_idx": int(w.get("question_idx", -1)),
                            "start_sec": float(w.get("start_sec", 0.0)),
                            "end_sec": float(w.get("end_sec", 0.0)),
                        })
                    except Exception:
                        continue
        except Exception as e:
            print(f"[WARN] Could not parse answer_windows: {e}")

    progress_store[session_id] = {"progress": 0, "status": "Uploading and initializing...", "result": None}

    background_tasks.add_task(
        run_analysis_task, video_path, session_id, parsed_questions, parsed_context, parsed_windows
    )

    return {
        "status": "started",
        "session_id": session_id,
    }


@app.post("/analyze-resume")
async def analyze_resume(file: UploadFile = File(...)):
    """
    Upload a resume (PDF/DOCX) → parse text → generate interview questions.
    """
    session_id = str(uuid.uuid4())
    session_dir = UPLOAD_ROOT / session_id / "resume"
    session_dir.mkdir(parents=True, exist_ok=True)

    file_path = session_dir / file.filename
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        from modules.resume_parser import parse_resume

        resume_text = parse_resume(str(file_path))

        context = extract_resume_context(resume_text)
        if context.get("error") and not context.get("questions"):
            fallback = generate_questions(resume_text)
            if fallback.get("error"):
                return {
                    "status": "error",
                    "message": context.get("error") or fallback.get("error"),
                    "questions": fallback.get("questions", []),
                }
            context = {
                "domain": "General",
                "certifications": [],
                "key_skills": [],
                "questions": fallback.get("questions", []),
            }

        persisted = {
            "domain": context.get("domain", "General"),
            "certifications": context.get("certifications", []),
            "key_skills": context.get("key_skills", []),
            "questions": context.get("questions", []),
            "resume_text_snippet": (resume_text or "")[:4000],
        }
        try:
            with (session_dir / "context.json").open("w", encoding="utf-8") as fh:
                json.dump(persisted, fh, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[WARN] Could not persist resume context.json: {e}")

        return {
            "status": "success",
            "session_id": session_id,
            "domain": persisted["domain"],
            "certifications": persisted["certifications"],
            "key_skills": persisted["key_skills"],
            "questions": persisted["questions"],
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/")
def home():
    return {"message": "Interveux API is running!"}


@app.get("/training-rows/status")
def training_rows_status():
    """
    Quick status for Phase 0 training row logs.
    """
    training_rows_dir = os.environ.get(
        "TRAINING_ROWS_DIR",
        str(Path(__file__).resolve().parent / "training_rows"),
    )
    jsonl_path = Path(training_rows_dir) / "interview_segments.jsonl"
    return get_training_row_log_status(jsonl_path)


@app.post("/generate-tts")
async def tts_endpoint(data: dict):
    """
    Generate TTS for a question.
    Expected data: {"text": "...", "session_id": "...", "index": 0}
    """
    text = data.get("text")
    session_id = data.get("session_id")
    index = data.get("index", 0)

    if not text or not session_id:
        raise HTTPException(status_code=400, detail="Missing text or session_id")

    path = await asyncio.to_thread(generate_speech, text, session_id, index)
    if not path:
        raise HTTPException(status_code=500, detail="TTS generation failed")

    filename = Path(path).name
    return {"url": f"http://localhost:8000/tts/{session_id}/{filename}"}


@app.post("/generate-tts-batch")
async def tts_batch_endpoint(data: dict):
    """
    Pre-generate TTS for all questions in parallel.
    Expected data: {"session_id": "...", "questions": [{"question": "...", "index": 0}, ...]}
    """
    session_id = data.get("session_id")
    questions_raw = data.get("questions", [])

    if not session_id or not questions_raw:
        raise HTTPException(status_code=400, detail="Missing session_id or questions")

    questions = [
        {"text": q.get("question", q.get("text", "")), "index": q.get("index", i)}
        for i, q in enumerate(questions_raw)
    ]
    results = await asyncio.to_thread(generate_speech_batch, session_id, questions)
    return {"urls": results}


@app.get("/tts/{session_id}/{filename}")
def get_tts_file(session_id: str, filename: str):
    file_path = Path(__file__).resolve().parent / "uploads" / session_id / "tts" / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="TTS file not found")
    return FileResponse(path=str(file_path))


@app.get("/frames/{session_id}/{filename}")
def get_lacking_frame(session_id: str, filename: str):
    """
    Serve a persisted representative frame for a lacking interval.
    Saved by the video pipeline under uploads/<session_id>/lacking_frames/.
    Path traversal is blocked by filename restriction.
    """
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    file_path = Path(__file__).resolve().parent / "uploads" / session_id / "lacking_frames" / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Frame not found")
    return FileResponse(path=str(file_path), media_type="image/jpeg")


@app.get("/reports/{filename}")
def get_report(filename: str):
    """Serve generated report files (JSON/HTML) from the backend `reports/` folder.

    Example: GET /reports/example_video.json
    """
    reports_dir = Path(__file__).resolve().parent / "reports"
    file_path = reports_dir / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Report not found")
    # Let the client download the file with a sensible filename
    return FileResponse(path=str(file_path), filename=file_path.name)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
