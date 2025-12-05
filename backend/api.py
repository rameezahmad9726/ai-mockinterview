from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import shutil
from pathlib import Path
import uuid

from video_processor import process_video

app = FastAPI(title="AI Mock Interview API")

# Allow frontend access (React / Next.js / Flutter)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


UPLOAD_DIR = Path("uploads/api_uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.post("/process-video")
async def process_video_api(file: UploadFile = File(...)):
    """
    Upload a video and run full pipeline.
    """

    # Generate unique filename
    ext = file.filename.split(".")[-1]
    vid_name = f"{uuid.uuid4()}.{ext}"
    saved_path = UPLOAD_DIR / vid_name

    # Save uploaded video locally
    with saved_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    # Run your existing pipeline
    result = process_video(str(saved_path))

    return {
        "message": "Video processed successfully",
        "json_report": result["report_json_path"],
        "html_report": result["report_html_path"],
        "final_summary": result["report"]["final_summary"],
    }
