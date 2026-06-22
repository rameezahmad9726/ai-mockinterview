"""
Candidate-facing endpoints (no login; token-protected).

Flow:
    GET    /api/interview/{token}           -> session info (job title, config, questions if any)
    POST   /api/interview/{token}/consent   -> mark STARTED, record consent
    POST   /api/interview/{token}/resume    -> upload resume, parse, generate questions
    POST   /api/interview/{token}/events    -> push integrity events during recording
    POST   /api/interview/{token}/submit    -> upload video, kick off analysis in background
    GET    /api/interview/{token}/status    -> poll progress (progress %, status message, done flag)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from auth import get_session_by_token
from db import SessionLocal, get_db
from models import InterviewSession, Report, SessionStatus
from schemas import CandidateInterviewInfo, IntegrityEvent

log = logging.getLogger("interveux.candidate")

router = APIRouter(prefix="/api/interview", tags=["candidate"])

UPLOAD_ROOT = Path(os.environ.get("INTERVEUX_UPLOAD_ROOT", "uploads"))
UPLOAD_ROOT.mkdir(exist_ok=True)


def _effective_passing_threshold(job) -> int:
    """
    Resolve the report "passing mark" in a way that matches current HR usage.

    Historically, many jobs only changed `auto_reject_threshold` while leaving
    `shortlist_threshold` at its default (80). In that case, using shortlist as
    the pass mark incorrectly looks "fixed at 80".
    """
    shortlist = int(job.shortlist_threshold or 60)
    auto_reject = int(job.auto_reject_threshold or 40)
    # If shortlist was never customized (still default 80) but auto-reject was,
    # treat auto-reject as the effective pass mark for report messaging/tiering.
    if shortlist == 60 and auto_reject != 40:
        return auto_reject
    return shortlist


def _session_dep(token: str, db: Session = Depends(get_db)) -> InterviewSession:
    return get_session_by_token(token, db)


def _summarize(sess: InterviewSession) -> CandidateInterviewInfo:
    job = sess.job
    return CandidateInterviewInfo(
        session_external_id=sess.external_id,
        job_title=job.title,
        company=os.environ.get("COMPANY_NAME"),
        num_questions=job.num_questions,
        seconds_per_answer=job.seconds_per_answer,
        allow_retakes=job.allow_retakes,
        expires_at=sess.expires_at,
        status=sess.status,
        has_resume=bool(sess.resume_path),
        questions=sess.questions,
    )


@router.get("/{token}", response_model=CandidateInterviewInfo)
def get_interview(sess: InterviewSession = Depends(_session_dep)) -> CandidateInterviewInfo:
    return _summarize(sess)


@router.post("/{token}/consent", response_model=CandidateInterviewInfo)
def give_consent(
    sess: InterviewSession = Depends(_session_dep),
    db: Session = Depends(get_db),
):
    if sess.status == SessionStatus.INVITED:
        sess.status = SessionStatus.STARTED
        sess.started_at = datetime.utcnow()

    # Retake: resume on file but questions cleared — generate a fresh set.
    if sess.resume_path and not sess.questions:
        prior = []
        if isinstance(sess.resume_context, dict):
            prior = list(sess.resume_context.get("_prior_questions") or [])
        try:
            _regenerate_session_questions(sess, db, previous_questions=prior)
        except Exception:
            log.exception("Failed to regenerate questions for session %s", sess.external_id)

    db.commit()
    db.refresh(sess)
    return _summarize(sess)


def _trim_questions(questions: list, limit: int) -> list:
    """Keep `limit` questions, preserving order and dropping duplicates by text."""
    seen: set[str] = set()
    out: list = []
    for q in questions or []:
        if not isinstance(q, dict):
            continue
        text = (q.get("question") or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append({"type": q.get("type", "General"), "question": text})
        if len(out) >= limit:
            break
    return out


def _ensure_question_count(questions: list, limit: int, job_title: str) -> list:
    """
    Guarantee exactly `limit` questions even when the LLM returns duplicates/fewer
    items than requested.
    """
    out = list(questions or [])[:limit]
    idx = len(out) + 1
    while len(out) < limit:
        out.append({
            "type": "Behavioral",
            "question": (
                f"Question {idx}: Tell us about a relevant experience for the {job_title} role "
                "and the impact you made."
            ),
        })
        idx += 1
    return out


def _build_questions_from_resume(
    resume_text: str,
    job,
    *,
    previous_questions: Optional[list] = None,
) -> tuple[dict[str, Any], list]:
    """Parse resume text and return (resume_context, questions)."""
    from modules.question_generator import extract_resume_context, generate_questions

    prior = list(previous_questions or [])
    context = extract_resume_context(
        resume_text,
        previous_questions=prior,
        num_questions=job.num_questions,
    ) or {}

    if context.get("error") and not context.get("questions"):
        fallback = generate_questions(
            resume_text,
            previous_questions=prior,
            num_questions=job.num_questions,
        )
        context = {
            "domain": "General",
            "certifications": [],
            "key_skills": [],
            "questions": fallback.get("questions", []),
            "error": fallback.get("error"),
        }

    resume_context: dict[str, Any] = {
        "domain": context.get("domain", "General"),
        "certifications": context.get("certifications", []),
        "key_skills": context.get("key_skills", []),
        "resume_text_snippet": resume_text[:4000],
    }
    questions = _trim_questions(context.get("questions") or [], job.num_questions)
    questions = _ensure_question_count(questions, job.num_questions, job.title)
    return resume_context, questions


def _regenerate_session_questions(
    sess: InterviewSession,
    db: Session,
    *,
    previous_questions: Optional[list] = None,
) -> None:
    """Rebuild questions from the stored resume (retake / consent path)."""
    if not sess.resume_path or not Path(sess.resume_path).exists():
        return
    from modules.resume_parser import parse_resume

    prior = list(previous_questions or sess.questions or [])
    resume_text = parse_resume(sess.resume_path) or ""
    resume_context, questions = _build_questions_from_resume(
        resume_text,
        sess.job,
        previous_questions=prior,
    )
    if not questions:
        questions = _ensure_question_count(
            [],
            sess.job.num_questions,
            sess.job.title,
        )
    sess.resume_context = resume_context
    sess.questions = questions

    session_dir = Path(sess.resume_path).parent
    try:
        ctx_path = session_dir / "context.json"
        with ctx_path.open("w", encoding="utf-8") as fh:
            json.dump(
                {**resume_context, "questions": questions},
                fh, ensure_ascii=False, indent=2,
            )
    except Exception as e:
        log.warning("Could not persist context.json: %s", e)


@router.post("/{token}/resume", response_model=CandidateInterviewInfo)
async def upload_resume(
    file: UploadFile = File(...),
    sess: InterviewSession = Depends(_session_dep),
    db: Session = Depends(get_db),
):
    """
    Persist resume, parse to text, call the LLM to build domain/skills/questions.
    Questions are trimmed to the job's `num_questions` and stored on the session.
    """
    if sess.status not in {SessionStatus.INVITED, SessionStatus.STARTED}:
        raise HTTPException(status_code=409, detail=f"Cannot upload resume in status {sess.status.value}")

    session_dir = UPLOAD_ROOT / sess.external_id / "resume"
    session_dir.mkdir(parents=True, exist_ok=True)
    dest = session_dir / (file.filename or "resume.pdf")

    try:
        with open(dest, "wb") as buf:
            shutil.copyfileobj(file.file, buf)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save resume: {e}")

    sess.resume_path = str(dest)

    previous_questions = list(sess.questions or [])
    resume_context: dict[str, Any] = {}
    questions: list = []
    try:
        from modules.resume_parser import parse_resume

        resume_text = parse_resume(str(dest)) or ""
        resume_context, questions = _build_questions_from_resume(
            resume_text,
            sess.job,
            previous_questions=previous_questions,
        )
    except Exception as e:  # pragma: no cover - depends on optional libs
        log.exception("Resume processing failed")
        resume_context = {"error": str(e)[:500]}

    if not questions:
        # Guarantee the candidate has something to answer, even on LLM failure.
        questions = [
            {"type": "Behavioral", "question": f"Tell us about your experience relevant to the {sess.job.title} role."}
        ]
    questions = _ensure_question_count(questions, sess.job.num_questions, sess.job.title)

    sess.resume_context = resume_context
    sess.questions = questions
    if sess.status == SessionStatus.INVITED:
        sess.status = SessionStatus.STARTED
        sess.started_at = datetime.utcnow()
    db.commit()
    db.refresh(sess)

    # Also persist context.json for video_processor's resume_session_id fallback.
    try:
        ctx_path = session_dir / "context.json"
        with ctx_path.open("w", encoding="utf-8") as fh:
            json.dump(
                {**resume_context, "questions": questions},
                fh, ensure_ascii=False, indent=2,
            )
    except Exception as e:
        log.warning("Could not persist context.json: %s", e)

    return _summarize(sess)


@router.post("/{token}/events", status_code=status.HTTP_202_ACCEPTED)
def push_integrity_event(
    event: IntegrityEvent,
    sess: InterviewSession = Depends(_session_dep),
    db: Session = Depends(get_db),
):
    flags = list(sess.integrity_flags or [])
    flags.append(event.dict())
    sess.integrity_flags = flags
    db.commit()
    return {"accepted": True, "count": len(flags)}


# ---------- Submit + analyze ----------

def _run_analysis(external_id: str) -> None:
    """
    Background worker: load session, run video_processor, persist Report.
    Uses its own DB session since request scope is closed by now.
    """
    db = SessionLocal()
    try:
        sess = db.query(InterviewSession).filter(InterviewSession.external_id == external_id).first()
        if not sess:
            log.error("Analysis task: session %s not found", external_id)
            return
        if not sess.video_path or not Path(sess.video_path).exists():
            sess.status = SessionStatus.FAILED
            sess.error_message = "Video file missing on disk"
            db.commit()
            return

        sess.status = SessionStatus.ANALYZING
        sess.progress = 1
        sess.progress_message = "Starting analysis..."
        db.commit()

        def on_progress(percent: int, message: str) -> None:
            # Use a fresh session for each update to avoid long-held transactions
            # blocking concurrent HR dashboard polls on SQLite.
            inner = SessionLocal()
            try:
                row = inner.query(InterviewSession).filter(
                    InterviewSession.external_id == external_id
                ).first()
                if row:
                    row.progress = int(percent)
                    row.progress_message = (message or "")[:500]
                    inner.commit()
            finally:
                inner.close()

        try:
            from video_processor import process_video

            result = process_video(
                sess.video_path,
                sess.external_id,
                sess.questions or [],
                on_progress=on_progress,
                resume_context=sess.resume_context,
                answer_windows=sess.answer_windows,
                passing_threshold_0_100=_effective_passing_threshold(sess.job),
            )

            report_payload = (result or {}).get("report") or {}
            scoring = report_payload.get("scoring") or {}
            overall = scoring.get("total_0_100")

            sub_scores = {
                "confidence": result.get("confidence_score"),
                "eye_contact": result.get("eye_contact_score"),
                "trend": result.get("trend"),
                # Pass through any top-level category scores from the scoring engine.
                **{k: v for k, v in scoring.items() if k not in {"total_0_100", "recommendation", "domain"}},
            }

            if sess.report:
                db.delete(sess.report)
                db.flush()

            report_row = Report(
                session_id=sess.id,
                overall_score=overall,
                sub_scores=sub_scores,
                ai_summary=None,
                raw_report=report_payload,
                report_json_path=result.get("report_json_path"),
                report_html_path=result.get("report_html_path"),
            )
            from services.llm_summary import ensure_report_summary

            ensure_report_summary(
                report_row,
                sess.job.title,
                sess.job.required_skills or [],
            )
            db.add(report_row)
            sess.status = SessionStatus.SCORED
            sess.progress = 100
            sess.progress_message = "Analysis complete"
            sess.analyzed_at = datetime.utcnow()
            db.commit()

            # Run the auto-decision engine (LLM summary + threshold policy +
            # outcome email). Failures here should not mark the analysis as
            # failed — HR can always manually override.
            try:
                from services.decision_engine import run_for_session
                company = os.environ.get("COMPANY_NAME", "Interveux")
                run_for_session(db, sess.external_id, company=company)
            except Exception:
                log.exception("Decision engine failed for session %s", sess.external_id)
        except Exception as e:
            log.exception("Analysis failed for session %s", external_id)
            sess.status = SessionStatus.FAILED
            sess.error_message = str(e)[:2000]
            sess.progress_message = "Analysis failed"
            db.commit()
    finally:
        db.close()


@router.post("/{token}/submit")
async def submit_interview(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    answer_windows: Optional[str] = Form(None),
    sess: InterviewSession = Depends(_session_dep),
    db: Session = Depends(get_db),
):
    """
    Candidate submits the recorded interview video. Persists the file, marks the
    session SUBMITTED, and schedules `process_video` in the background.
    """
    if sess.status not in {SessionStatus.STARTED, SessionStatus.INVITED}:
        # Allow re-submit only if retakes are enabled.
        if not (sess.status == SessionStatus.SUBMITTED and sess.job.allow_retakes):
            raise HTTPException(status_code=409, detail=f"Cannot submit in status {sess.status.value}")

    session_dir = UPLOAD_ROOT / sess.external_id / "original"
    session_dir.mkdir(parents=True, exist_ok=True)
    dest = session_dir / (file.filename or f"interview_{sess.external_id}.webm")

    try:
        with open(dest, "wb") as buf:
            shutil.copyfileobj(file.file, buf)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save video: {e}")

    sess.video_path = str(dest)
    sess.submitted_at = datetime.utcnow()
    sess.status = SessionStatus.SUBMITTED
    sess.progress = 0
    sess.progress_message = "Queued for analysis"

    if answer_windows:
        try:
            parsed = json.loads(answer_windows)
            if isinstance(parsed, list):
                sess.answer_windows = [
                    {
                        "question_idx": int(w.get("question_idx", -1)),
                        "start_sec": float(w.get("start_sec", 0.0)),
                        "end_sec": float(w.get("end_sec", 0.0)),
                    }
                    for w in parsed
                    if isinstance(w, dict)
                ]
        except Exception as e:
            log.warning("Could not parse answer_windows: %s", e)

    db.commit()

    background.add_task(_run_analysis, sess.external_id)

    return {
        "status": "submitted",
        "session_external_id": sess.external_id,
    }


@router.get("/{token}/status")
def get_status(sess: InterviewSession = Depends(_session_dep)):
    """
    Poll for submission + analysis progress. Designed for the candidate's
    post-submit waiting screen; no report internals are leaked here.
    """
    done = sess.status in {SessionStatus.SCORED, SessionStatus.FAILED}
    return {
        "status": sess.status.value,
        "progress": sess.progress or 0,
        "message": sess.progress_message or "",
        "done": done,
        "error": sess.error_message if sess.status == SessionStatus.FAILED else None,
    }
