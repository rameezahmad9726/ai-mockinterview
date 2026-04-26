"""
HR-only admin endpoints: jobs CRUD, candidate invites, pipeline view, decisioning.

Phase 1 scope: jobs CRUD + a stub invite endpoint that creates sessions and
signed tokens but does not yet email. Email sending is wired in Phase 2.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session

from auth import create_session_token, require_hr, require_hr_bearer_or_query
from db import SessionLocal, get_db
from services.email_service import send_email
from services.email_templates import render_invite, render_reject, render_shortlist

log = logging.getLogger("interveux.admin")
from models import (
    ActorType,
    AuditLog,
    Candidate,
    Decision,
    DecisionStatus,
    EmailLog,
    InterviewSession,
    Job,
    JobStatus,
    Report,
    SessionStatus,
    User,
)
from schemas import (
    BulkDecisionRequest,
    BulkDecisionResult,
    BulkInviteRequest,
    BulkInviteResult,
    DecisionUpdate,
    JobCreate,
    JobOut,
    JobUpdate,
    SessionDetail,
    SessionSummary,
)

router = APIRouter(prefix="/api/hr", tags=["hr"])

_REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def _safe_report_html_file(stored_path: str) -> Path:
    """Resolve stored report path to a file under backend/reports/ (by basename only)."""
    name = Path(stored_path).name
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid report path")
    candidate = (_REPORTS_DIR / name).resolve()
    try:
        candidate.relative_to(_REPORTS_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid report path")
    return candidate


# ---------- Jobs ----------

@router.post("/jobs", response_model=JobOut, status_code=status.HTTP_201_CREATED)
def create_job(
    body: JobCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_hr),
) -> Job:
    job = Job(
        **body.dict(),
        created_by_id=current.id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    db.add(AuditLog(
        actor_user_id=current.id,
        actor_type=ActorType.HR,
        action="job.create",
        entity_type="job",
        entity_id=str(job.id),
        meta={"title": job.title},
    ))
    db.commit()
    return job


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(
    db: Session = Depends(get_db),
    _: User = Depends(require_hr),
    status_filter: Optional[JobStatus] = None,
) -> list[Job]:
    q = db.query(Job).order_by(Job.created_at.desc())
    if status_filter:
        q = q.filter(Job.status == status_filter)
    return q.all()


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db), _: User = Depends(require_hr)) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.patch("/jobs/{job_id}", response_model=JobOut)
def update_job(
    job_id: int,
    body: JobUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(require_hr),
) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    for field, value in body.dict(exclude_unset=True).items():
        setattr(job, field, value)
    db.commit()
    db.refresh(job)

    db.add(AuditLog(
        actor_user_id=current.id,
        actor_type=ActorType.HR,
        action="job.update",
        entity_type="job",
        entity_id=str(job.id),
    ))
    db.commit()
    return job


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: int, db: Session = Depends(get_db), current: User = Depends(require_hr)) -> None:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    db.delete(job)
    db.add(AuditLog(
        actor_user_id=current.id,
        actor_type=ActorType.HR,
        action="job.delete",
        entity_type="job",
        entity_id=str(job_id),
    ))
    db.commit()


# ---------- Invites / Sessions ----------

def _build_invite_url(token: str) -> str:
    base = (os.environ.get("APP_BASE_URL") or "http://localhost:3000").rstrip("/")
    return f"{base}/interview/{token}"


def _dispatch_invite_email(email_log_id: int) -> None:
    """
    Send a queued invite email by its EmailLog id. Runs in BackgroundTasks so
    HTTP responses don't block on SMTP. Opens its own DB session because the
    request-scoped session is already closed by the time this runs.
    """
    db = SessionLocal()
    try:
        log_row: Optional[EmailLog] = db.get(EmailLog, email_log_id)
        if not log_row or log_row.status == "sent":
            return
        sess: Optional[InterviewSession] = (
            db.get(InterviewSession, log_row.session_id) if log_row.session_id else None
        )
        if not sess:
            log_row.status = "failed"
            log_row.error = "session missing"
            db.commit()
            return

        job = sess.job
        candidate = sess.candidate
        company = os.environ.get("COMPANY_NAME") or "Interveux"

        rendered = render_invite(
            candidate_name=candidate.full_name or candidate.email.split("@")[0],
            company=company,
            job_title=job.title,
            interview_url=_build_invite_url(sess.token),
            expires_at=sess.expires_at.strftime("%Y-%m-%d %H:%M UTC"),
            num_questions=job.num_questions,
            seconds_per_answer=job.seconds_per_answer,
        )
        log_row.subject = rendered.subject

        try:
            send_email(
                to=candidate.email,
                subject=rendered.subject,
                text=rendered.text,
                html=rendered.html,
            )
            log_row.status = "sent"
            log_row.error = None
        except Exception as e:  # pragma: no cover - network
            log.exception("Failed to send invite email to %s", candidate.email)
            log_row.status = "failed"
            log_row.error = str(e)[:500]
        db.commit()
    finally:
        db.close()


@router.post("/jobs/{job_id}/invites", response_model=BulkInviteResult)
def bulk_invite(
    job_id: int,
    body: BulkInviteRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    current: User = Depends(require_hr),
) -> BulkInviteResult:
    """
    Create (or reuse) a Candidate per email and an InterviewSession per (job, candidate).
    Emits a signed session token and dispatches the invite email in the background.
    """
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    created = 0
    skipped = 0
    session_ids: list[str] = []
    queued_email_ids: list[int] = []

    for item in body.invites:
        email = item.email.lower()
        candidate = db.query(Candidate).filter(Candidate.email == email).first()
        if not candidate:
            candidate = Candidate(email=email, full_name=item.full_name)
            db.add(candidate)
            db.flush()

        existing = db.query(InterviewSession).filter(
            InterviewSession.job_id == job.id,
            InterviewSession.candidate_id == candidate.id,
        ).first()
        if existing:
            skipped += 1
            session_ids.append(existing.external_id)
            continue

        external_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(hours=job.link_expiry_hours or 72)
        token = create_session_token(external_id, expires_at)

        sess = InterviewSession(
            token=token,
            external_id=external_id,
            job_id=job.id,
            candidate_id=candidate.id,
            status=SessionStatus.INVITED,
            expires_at=expires_at,
        )
        db.add(sess)
        db.flush()

        email_log = EmailLog(
            session_id=sess.id,
            candidate_email=email,
            template="invite",
            status="queued",
        )
        db.add(email_log)
        db.flush()
        queued_email_ids.append(email_log.id)

        created += 1
        session_ids.append(external_id)

    db.add(AuditLog(
        actor_user_id=current.id,
        actor_type=ActorType.HR,
        action="job.invite",
        entity_type="job",
        entity_id=str(job.id),
        meta={"created": created, "skipped": skipped},
    ))
    db.commit()

    for eid in queued_email_ids:
        background.add_task(_dispatch_invite_email, eid)

    return BulkInviteResult(created=created, skipped=skipped, session_ids=session_ids)


@router.post("/sessions/{external_id}/rerun-decision")
def rerun_decision(
    external_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(require_hr),
):
    """
    Re-run the auto-decision engine on an already-analyzed session. Useful
    after HR adjusts the job's thresholds. Does NOT overwrite manual HR
    decisions; the decision engine respects those.
    """
    sess = db.query(InterviewSession).filter(InterviewSession.external_id == external_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    if not sess.report:
        raise HTTPException(status_code=409, detail="Session has no report yet")

    from services.decision_engine import run_for_session

    company = os.environ.get("COMPANY_NAME", "Interveux")
    decision = run_for_session(db, sess.external_id, company=company)
    db.add(AuditLog(
        actor_user_id=current.id,
        actor_type=ActorType.HR,
        action="decision.rerun",
        entity_type="session",
        entity_id=sess.external_id,
    ))
    db.commit()
    return {
        "status": decision.status.value if decision else None,
        "reason": decision.reason if decision else None,
    }


@router.post("/sessions/{external_id}/rerun-analysis")
def rerun_analysis(
    external_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    current: User = Depends(require_hr),
):
    """
    Re-submit the stored video through the analysis pipeline. Useful when the
    first run failed (status=FAILED) or after an ML model update.
    """
    sess = db.query(InterviewSession).filter(InterviewSession.external_id == external_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    if not sess.video_path:
        raise HTTPException(status_code=409, detail="Session has no video to analyze")

    from routes.candidate import _run_analysis  # local import to avoid cycle at load
    sess.status = SessionStatus.SUBMITTED
    sess.progress = 0
    sess.progress_message = "Re-queued for analysis"
    sess.error_message = None
    db.add(AuditLog(
        actor_user_id=current.id,
        actor_type=ActorType.HR,
        action="analysis.rerun",
        entity_type="session",
        entity_id=sess.external_id,
    ))
    db.commit()
    background.add_task(_run_analysis, sess.external_id)
    return {"queued": True}


@router.post("/sessions/{external_id}/resend-invite")
def resend_invite(
    external_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    current: User = Depends(require_hr),
):
    sess = db.query(InterviewSession).filter(InterviewSession.external_id == external_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    reset_for_retake = sess.status in {
        SessionStatus.SUBMITTED,
        SessionStatus.ANALYZING,
        SessionStatus.SCORED,
        SessionStatus.FAILED,
        SessionStatus.EXPIRED,
    }
    if reset_for_retake:
        if not sess.job.allow_retakes:
            raise HTTPException(
                status_code=409,
                detail=(
                    "This interview is already completed/closed and retakes are disabled for this job. "
                    "Enable retakes on the job, then resend invite."
                ),
            )
        # Reset session lifecycle + artifacts for a clean retake attempt.
        sess.token = create_session_token(
            sess.external_id,
            datetime.utcnow() + timedelta(hours=sess.job.link_expiry_hours),
        )
        sess.status = SessionStatus.INVITED
        sess.invited_at = datetime.utcnow()
        sess.expires_at = datetime.utcnow() + timedelta(hours=sess.job.link_expiry_hours)
        sess.started_at = None
        sess.submitted_at = None
        sess.analyzed_at = None
        sess.video_path = None
        sess.answer_windows = None
        sess.integrity_flags = []
        sess.progress = 0
        sess.progress_message = None
        sess.error_message = None
        if sess.report:
            db.delete(sess.report)
        if sess.decision:
            db.delete(sess.decision)

    email_log = EmailLog(
        session_id=sess.id,
        candidate_email=sess.candidate.email,
        template="invite",
        status="queued",
    )
    db.add(email_log)
    db.add(AuditLog(
        actor_user_id=current.id,
        actor_type=ActorType.HR,
        action="invite.resend",
        entity_type="session",
        entity_id=sess.external_id,
        meta={"reset_for_retake": reset_for_retake},
    ))
    db.commit()
    background.add_task(_dispatch_invite_email, email_log.id)
    return {"queued": True, "email_log_id": email_log.id}


# ---------- Pipeline / Candidate views ----------

def _summarize(sess: InterviewSession) -> dict:
    return {
        "id": sess.id,
        "external_id": sess.external_id,
        "job_id": sess.job_id,
        "candidate": sess.candidate,
        "status": sess.status,
        "invited_at": sess.invited_at,
        "expires_at": sess.expires_at,
        "submitted_at": sess.submitted_at,
        "overall_score": sess.report.overall_score if sess.report else None,
        "decision": sess.decision.status if sess.decision else None,
    }


@router.get("/jobs/{job_id}/sessions", response_model=list[SessionSummary])
def list_sessions_for_job(
    job_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_hr),
    status_filter: Optional[SessionStatus] = None,
    decision_filter: Optional[DecisionStatus] = None,
):
    if not db.get(Job, job_id):
        raise HTTPException(status_code=404, detail="Job not found")

    q = db.query(InterviewSession).filter(InterviewSession.job_id == job_id)
    if status_filter:
        q = q.filter(InterviewSession.status == status_filter)
    if decision_filter:
        q = q.join(Decision).filter(Decision.status == decision_filter)
    rows = q.order_by(InterviewSession.invited_at.desc()).all()
    return [_summarize(r) for r in rows]


@router.get("/sessions/{external_id}", response_model=SessionDetail)
def session_detail(
    external_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_hr),
):
    sess = db.query(InterviewSession).filter(InterviewSession.external_id == external_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    summary = _summarize(sess)
    report: Optional[Report] = sess.report
    summary.update({
        "questions": sess.questions,
        "answer_windows": sess.answer_windows,
        "integrity_flags": sess.integrity_flags,
        "sub_scores": report.sub_scores if report else None,
        "ai_summary": report.ai_summary if report else None,
        "report_json_path": report.report_json_path if report else None,
        "report_html_path": report.report_html_path if report else None,
    })
    return summary


@router.get("/sessions/{external_id}/report", response_class=HTMLResponse)
def session_report_html(
    external_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_hr_bearer_or_query),
):
    """Full HTML analysis report for HR session view (iframe-friendly via `?token=`)."""
    sess = db.query(InterviewSession).filter(InterviewSession.external_id == external_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    report = sess.report
    if not report or not report.report_html_path:
        raise HTTPException(status_code=404, detail="Report not available yet")
    path = _safe_report_html_file(report.report_html_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Report file missing on disk")
    return HTMLResponse(content=path.read_text(encoding="utf-8", errors="replace"))


def _send_decision_email(db: Session, sess: InterviewSession, status: DecisionStatus) -> None:
    """Dispatch a shortlist or rejection email for an HR-set decision."""
    company = os.environ.get("COMPANY_NAME") or "Interveux"
    if status == DecisionStatus.SHORTLISTED or status == DecisionStatus.ADVANCED:
        rendered = render_shortlist(
            candidate_name=sess.candidate.full_name or sess.candidate.email.split("@")[0],
            company=company,
            job_title=sess.job.title,
            calendly_url=sess.job.calendly_url,
        )
        template = "shortlist"
    elif status == DecisionStatus.REJECTED:
        rendered = render_reject(
            candidate_name=sess.candidate.full_name or sess.candidate.email.split("@")[0],
            company=company,
            job_title=sess.job.title,
        )
        template = "reject"
    else:
        return  # REVIEW / WITHDRAWN: no candidate email

    row = EmailLog(
        session_id=sess.id,
        candidate_email=sess.candidate.email,
        template=template,
        subject=rendered.subject,
        status="queued",
    )
    db.add(row)
    db.flush()
    try:
        send_email(to=sess.candidate.email, subject=rendered.subject, text=rendered.text, html=rendered.html)
        row.status = "sent"
    except Exception as e:  # pragma: no cover
        log.exception("Manual decision email failed")
        row.status = "failed"
        row.error = str(e)[:500]


def _apply_decision(
    db: Session,
    sess: InterviewSession,
    new_status: DecisionStatus,
    reason: Optional[str],
    current_user: User,
) -> None:
    if sess.decision is None:
        db.add(Decision(
            session_id=sess.id,
            status=new_status,
            reason=reason,
            actor_type=ActorType.HR,
            actor_user_id=current_user.id,
        ))
    else:
        sess.decision.status = new_status
        sess.decision.reason = reason
        sess.decision.actor_type = ActorType.HR
        sess.decision.actor_user_id = current_user.id


@router.post("/sessions/{external_id}/decision", response_model=SessionDetail)
def set_decision(
    external_id: str,
    body: DecisionUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(require_hr),
):
    sess = db.query(InterviewSession).filter(InterviewSession.external_id == external_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    _apply_decision(db, sess, body.status, body.reason, current)
    db.add(AuditLog(
        actor_user_id=current.id,
        actor_type=ActorType.HR,
        action="decision.set",
        entity_type="session",
        entity_id=sess.external_id,
        meta={"status": body.status.value, "reason": body.reason, "send_email": body.send_email},
    ))
    db.commit()
    db.refresh(sess)

    if body.send_email:
        _send_decision_email(db, sess, body.status)
        db.commit()

    return session_detail(external_id, db=db, _=current)


@router.post("/jobs/{job_id}/bulk-decision", response_model=BulkDecisionResult)
def bulk_decision(
    job_id: int,
    body: BulkDecisionRequest,
    db: Session = Depends(get_db),
    current: User = Depends(require_hr),
) -> BulkDecisionResult:
    """
    Apply the same decision to many sessions in one shot. Either pass explicit
    `session_ids`, or use a rule:
      - rule="top_n"       + top_n=N          → N highest-scoring scored sessions
      - rule="above_score" + score=X          → sessions with overall_score >= X
      - rule="below_score" + score=X          → sessions with overall_score < X
    Only SCORED sessions with a report are considered for rule-based selection.
    """
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    base = (
        db.query(InterviewSession)
        .filter(InterviewSession.job_id == job_id)
    )

    if body.session_ids:
        sessions = base.filter(InterviewSession.external_id.in_(body.session_ids)).all()
    else:
        q = (
            base.join(Report, Report.session_id == InterviewSession.id)
            .filter(InterviewSession.status == SessionStatus.SCORED)
        )
        if body.rule == "top_n":
            if not body.top_n or body.top_n <= 0:
                raise HTTPException(status_code=400, detail="top_n must be > 0")
            sessions = q.order_by(Report.overall_score.desc()).limit(body.top_n).all()
        elif body.rule == "above_score":
            if body.score is None:
                raise HTTPException(status_code=400, detail="score is required for above_score")
            sessions = q.filter(Report.overall_score >= body.score).all()
        elif body.rule == "below_score":
            if body.score is None:
                raise HTTPException(status_code=400, detail="score is required for below_score")
            sessions = q.filter(Report.overall_score < body.score).all()
        else:
            raise HTTPException(status_code=400, detail="Provide session_ids or a valid rule")

    updated = 0
    skipped = 0
    touched_ids: list[str] = []
    email_targets: list[InterviewSession] = []

    for sess in sessions:
        if sess.decision and sess.decision.actor_type == ActorType.HR and sess.decision.status == body.status:
            skipped += 1
            continue
        _apply_decision(db, sess, body.status, body.reason or "Bulk action", current)
        updated += 1
        touched_ids.append(sess.external_id)
        if body.send_email:
            email_targets.append(sess)

    db.add(AuditLog(
        actor_user_id=current.id,
        actor_type=ActorType.HR,
        action="decision.bulk",
        entity_type="job",
        entity_id=str(job_id),
        meta={"status": body.status.value, "updated": updated, "rule": body.rule, "send_email": body.send_email},
    ))
    db.commit()

    for sess in email_targets:
        db.refresh(sess)
        _send_decision_email(db, sess, body.status)
    db.commit()

    return BulkDecisionResult(updated=updated, skipped=skipped, session_ids=touched_ids)


@router.get("/compare")
def compare_sessions(
    ids: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_hr),
):
    """
    Side-by-side payload for 2..10 sessions. Accepts ?ids=a,b,c (external_ids).
    Returns a compact, UI-friendly shape (no raw_report blob).
    """
    external_ids = [x.strip() for x in (ids or "").split(",") if x.strip()]
    if not 2 <= len(external_ids) <= 10:
        raise HTTPException(status_code=400, detail="Pick between 2 and 10 candidates to compare")

    rows = db.query(InterviewSession).filter(InterviewSession.external_id.in_(external_ids)).all()
    by_id = {r.external_id: r for r in rows}
    out = []
    for ext in external_ids:
        sess = by_id.get(ext)
        if not sess:
            continue
        report = sess.report
        out.append({
            "external_id": sess.external_id,
            "candidate": {
                "email": sess.candidate.email,
                "full_name": sess.candidate.full_name,
            },
            "job_id": sess.job_id,
            "job_title": sess.job.title,
            "status": sess.status.value,
            "overall_score": report.overall_score if report else None,
            "sub_scores": report.sub_scores if report else None,
            "ai_summary": report.ai_summary if report else None,
            "decision": sess.decision.status.value if sess.decision else None,
            "integrity_flags": sess.integrity_flags or [],
            "submitted_at": sess.submitted_at,
            "invited_at": sess.invited_at,
        })
    return {"candidates": out}


def _iter_csv_rows(db: Session, job_id: int):
    yield (
        "external_id,candidate_email,candidate_name,status,decision,overall_score,"
        "submitted_at,invited_at,integrity_flag_count\n"
    )
    rows = (
        db.query(InterviewSession)
        .filter(InterviewSession.job_id == job_id)
        .order_by(InterviewSession.invited_at.desc())
        .all()
    )
    for s in rows:
        score = s.report.overall_score if s.report else ""
        decision = s.decision.status.value if s.decision else ""
        flags = len(s.integrity_flags or [])
        name = (s.candidate.full_name or "").replace(",", " ")
        email = s.candidate.email.replace(",", " ")
        yield (
            f"{s.external_id},{email},{name},{s.status.value},{decision},{score},"
            f"{s.submitted_at.isoformat() if s.submitted_at else ''},"
            f"{s.invited_at.isoformat() if s.invited_at else ''},{flags}\n"
        )


@router.get("/jobs/{job_id}/export.csv")
def export_job_csv(
    job_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_hr),
):
    if not db.get(Job, job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return StreamingResponse(
        _iter_csv_rows(db, job_id),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="job_{job_id}_candidates.csv"'},
    )


# ---------- Dashboard summary ----------

@router.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db), _: User = Depends(require_hr)):
    jobs_total = db.query(Job).count()
    jobs_open = db.query(Job).filter(Job.status == JobStatus.OPEN).count()
    sessions_total = db.query(InterviewSession).count()
    sessions_submitted = db.query(InterviewSession).filter(
        InterviewSession.status == SessionStatus.SUBMITTED
    ).count()
    shortlisted = db.query(Decision).filter(Decision.status == DecisionStatus.SHORTLISTED).count()
    rejected = db.query(Decision).filter(Decision.status == DecisionStatus.REJECTED).count()
    return {
        "jobs": {"total": jobs_total, "open": jobs_open},
        "sessions": {"total": sessions_total, "submitted": sessions_submitted},
        "decisions": {"shortlisted": shortlisted, "rejected": rejected},
    }
