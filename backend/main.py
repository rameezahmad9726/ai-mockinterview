import os
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import uuid
import shutil

from video_processor import process_video
from modules.resume_parser import parse_resume
from modules.question_generator import generate_questions

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


@app.post("/analyze")
async def analyze_video(file: UploadFile = File(...)):
    """
    Upload a video → run full analysis → return JSON report.
    """

    # Create unique folder for each upload
    session_id = str(uuid.uuid4())
    session_dir = UPLOAD_ROOT / session_id
    original_dir = session_dir / "original"
    original_dir.mkdir(parents=True, exist_ok=True)

    # Save uploaded file
    video_path = original_dir / file.filename

    with open(video_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    print("📥 Video saved at:", video_path)

    # Process video (emotion + body language + audio extraction)
    # Run in threadpool to avoid blocking the async event loop
    from fastapi.concurrency import run_in_threadpool
    result = await run_in_threadpool(process_video, str(video_path))

    return {
        "status": "success",
        "session_id": session_id,
        "analysis": result
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
    return {"message": "AI Mock Interview API is running!"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


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
