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

from modules.resume_parser import parse_resume
from modules.question_generator import generate_questions
from modules.tts import generate_speech, generate_speech_batch

app = FastAPI()

# Allow frontend to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_ROOT = Path("uploads")
UPLOAD_ROOT.mkdir(exist_ok=True)

# Global store for tracking analysis progress
progress_store = {}

@app.get("/analysis-status/{session_id}")
async def get_analysis_status(session_id: str):
    if session_id not in progress_store:
        return {"status": "error", "message": "Session not found"}
    return progress_store[session_id]

def run_analysis_task(video_path, session_id, parsed_questions):
    try:
        from video_processor import process_video

        def on_progress(percent, message):
            progress_store[session_id]["progress"] = percent
            progress_store[session_id]["status"] = message

        result = process_video(str(video_path), session_id, parsed_questions, on_progress=on_progress)
        
        progress_store[session_id]["progress"] = 100
        progress_store[session_id]["status"] = "Completed"
        progress_store[session_id]["result"] = result
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error in background task: {e}")
        progress_store[session_id]["status"] = "error"
        progress_store[session_id]["message"] = str(e)

@app.post("/analyze")
async def analyze_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    questions: str = Form(None)
):
    """
    Upload a video → start background analysis → return session_id.
    """
    session_id = str(uuid.uuid4())
    session_dir = UPLOAD_ROOT / session_id
    original_dir = session_dir / "original"
    original_dir.mkdir(parents=True, exist_ok=True)

    video_path = original_dir / file.filename
    with open(video_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    parsed_questions = json.loads(questions) if questions else []
    
    # Initialize progress
    progress_store[session_id] = {"progress": 0, "status": "Uploading and initializing...", "result": None}
    
    # Start task in background
    background_tasks.add_task(run_analysis_task, video_path, session_id, parsed_questions)

    return {
        "status": "started",
        "session_id": session_id
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
        # 1. Parse Text
        resume_text = parse_resume(str(file_path))
        
        # 2. Generate Questions
        questions_data = generate_questions(resume_text)
        if questions_data.get("error"):
            # Surface API errors to the client for debugging
            return {
                "status": "error",
                "message": questions_data["error"],
                "questions": questions_data.get("questions", []),
            }

        return {
            "status": "success",
            "session_id": session_id,
            "questions": questions_data.get("questions", []),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/")
def home():
    return {"message": "Interveux API is running!"}


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

    path = generate_speech(text, session_id, index)
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
    results = generate_speech_batch(session_id, questions)
    return {"urls": results}


@app.get("/tts/{session_id}/{filename}")
def get_tts_file(session_id: str, filename: str):
    file_path = Path("uploads") / session_id / "tts" / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="TTS file not found")
    return FileResponse(path=str(file_path))


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
