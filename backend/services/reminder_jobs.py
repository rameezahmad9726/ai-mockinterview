"""
Scheduled background jobs:

  - expire_past_deadline_sessions: every 10 minutes; marks INVITED/STARTED
    sessions past `expires_at` as EXPIRED.
  - send_expiry_reminders: every 15 minutes; dispatches invite reminders to
    candidates whose session expires in ~24h or ~2h and hasn't been started
    (each reminder template fires at most once per session).
  - send_daily_digest: once per day at a configurable hour (UTC); emails the
    active HR users a summary of the last 24h.

Everything is idempotent: each job records a per-session or per-day marker in
the `EmailLog` / `AuditLog` tables so restarts don't re-send.

The scheduler is lazily created so unit tests / smoke scripts can run jobs
directly via the public functions without starting an event loop.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import func
from sqlalchemy.orm import Session

from db import SessionLocal
from models import (
    ActorType,
    AuditLog,
    Decision,
    DecisionStatus,
    EmailLog,
    InterviewSession,
    Job,
    SessionStatus,
    User,
    UserRole,
)
from services.email_service import send_email
from services.email_templates import render_digest, render_reminder

log = logging.getLogger("interveux.jobs")


def _now() -> datetime:
    return datetime.utcnow()


def _app_base_url() -> str:
    return (os.environ.get("APP_BASE_URL") or "http://localhost:3000").rstrip("/")


def _company() -> str:
    return os.environ.get("COMPANY_NAME") or "Interveux"


# ---------- Expire past-deadline sessions ----------

def expire_past_deadline_sessions(db: Optional[Session] = None) -> int:
    """Flip INVITED / STARTED sessions past `expires_at` to EXPIRED."""
    owned = db is None
    db = db or SessionLocal()
    try:
        now = _now()
        rows = (
            db.query(InterviewSession)
            .filter(
                InterviewSession.expires_at < now,
                InterviewSession.status.in_([SessionStatus.INVITED, SessionStatus.STARTED]),
            )
            .all()
        )
        count = 0
        for sess in rows:
            sess.status = SessionStatus.EXPIRED
            sess.progress_message = "Link expired"
            db.add(AuditLog(
                actor_type=ActorType.SYSTEM,
                action="session.expire",
                entity_type="session",
                entity_id=sess.external_id,
                meta={"expires_at": sess.expires_at.isoformat()},
            ))
            count += 1
        if count:
            db.commit()
            log.info("Expired %d stale sessions", count)
        return count
    finally:
        if owned:
            db.close()


# ---------- Candidate reminders ----------

def _already_reminded(db: Session, session_id: int, template: str) -> bool:
    return db.query(EmailLog).filter(
        EmailLog.session_id == session_id,
        EmailLog.template == template,
        EmailLog.status.in_(["sent", "queued"]),
    ).first() is not None


def _send_reminder(db: Session, sess: InterviewSession, template: str) -> None:
    rendered = render_reminder(
        candidate_name=sess.candidate.full_name or sess.candidate.email.split("@")[0],
        company=_company(),
        job_title=sess.job.title,
        interview_url=f"{_app_base_url()}/interview/{sess.token}",
        expires_at=sess.expires_at.strftime("%Y-%m-%d %H:%M UTC"),
    )
    log_row = EmailLog(
        session_id=sess.id,
        candidate_email=sess.candidate.email,
        template=template,
        subject=rendered.subject,
        status="queued",
    )
    db.add(log_row)
    db.flush()
    try:
        send_email(
            to=sess.candidate.email,
            subject=rendered.subject,
            text=rendered.text,
            html=rendered.html,
        )
        log_row.status = "sent"
    except Exception as e:  # pragma: no cover
        log.exception("Failed to send reminder %s", template)
        log_row.status = "failed"
        log_row.error = str(e)[:500]


def send_expiry_reminders(db: Optional[Session] = None) -> int:
    """Dispatch 24h and 2h reminders to stale INVITED/STARTED sessions."""
    owned = db is None
    db = db or SessionLocal()
    try:
        now = _now()
        sent = 0
        # 24h-remaining window: (22h, 26h). 2h-remaining window: (1h, 3h).
        windows = [
            ("reminder_24h", now + timedelta(hours=22), now + timedelta(hours=26)),
            ("reminder_2h",  now + timedelta(hours=1),  now + timedelta(hours=3)),
        ]
        for template, lo, hi in windows:
            rows = (
                db.query(InterviewSession)
                .filter(
                    InterviewSession.status.in_([SessionStatus.INVITED, SessionStatus.STARTED]),
                    InterviewSession.expires_at >= lo,
                    InterviewSession.expires_at <= hi,
                )
                .all()
            )
            for sess in rows:
                if _already_reminded(db, sess.id, template):
                    continue
                _send_reminder(db, sess, template)
                sent += 1
        if sent:
            db.commit()
            log.info("Sent %d reminder emails this tick", sent)
        return sent
    finally:
        if owned:
            db.close()


# ---------- HR daily digest ----------

def _digest_already_sent_today(db: Session, when: datetime) -> bool:
    """Whether a digest for the given UTC date has already been dispatched."""
    day_key = when.strftime("%Y-%m-%d")
    return db.query(EmailLog).filter(
        EmailLog.template == "hr_digest",
        EmailLog.subject.like(f"%({day_key})%"),
    ).first() is not None


def _digest_body(db: Session, since: datetime) -> tuple[str, str]:
    """Per-job breakdown for the digest body (plain-text + HTML)."""
    submitted_counts = (
        db.query(Job.id, Job.title, func.count(InterviewSession.id))
        .select_from(Job)
        .join(InterviewSession, InterviewSession.job_id == Job.id)
        .filter(InterviewSession.submitted_at >= since)
        .group_by(Job.id, Job.title)
        .all()
    )

    if not submitted_counts:
        return (
            "No job-level activity in the last 24 hours.\n",
            "<p><em>No job-level activity in the last 24 hours.</em></p>",
        )

    text_lines: list[str] = []
    html_lines: list[str] = ["<ul>"]
    for job_id, title, submitted in submitted_counts:
        shortlisted = (
            db.query(Decision)
            .join(InterviewSession, InterviewSession.id == Decision.session_id)
            .filter(
                InterviewSession.job_id == job_id,
                Decision.status == DecisionStatus.SHORTLISTED,
                Decision.updated_at >= since,
            )
            .count()
        )
        review = (
            db.query(Decision)
            .join(InterviewSession, InterviewSession.id == Decision.session_id)
            .filter(
                InterviewSession.job_id == job_id,
                Decision.status == DecisionStatus.REVIEW,
                Decision.updated_at >= since,
            )
            .count()
        )
        text_lines.append(
            f"- {title}: submitted={submitted}, shortlisted={shortlisted}, review={review}"
        )
        html_lines.append(
            f"<li><strong>{title}</strong> &mdash; submitted: {submitted}, "
            f"shortlisted: {shortlisted}, review: {review}</li>"
        )
    html_lines.append("</ul>")
    return ("\n".join(text_lines) + "\n", "".join(html_lines))


def send_daily_digest(db: Optional[Session] = None, *, force: bool = False) -> int:
    """Email active HR users a 24h activity digest."""
    owned = db is None
    db = db or SessionLocal()
    try:
        now = _now()
        if not force and _digest_already_sent_today(db, now):
            return 0

        since = now - timedelta(hours=24)

        new_shortlists = db.query(Decision).filter(
            Decision.status == DecisionStatus.SHORTLISTED,
            Decision.updated_at >= since,
        ).count()
        new_reviews = db.query(Decision).filter(
            Decision.status == DecisionStatus.REVIEW,
            Decision.updated_at >= since,
        ).count()
        new_rejects = db.query(Decision).filter(
            Decision.status == DecisionStatus.REJECTED,
            Decision.updated_at >= since,
        ).count()
        new_submits = db.query(InterviewSession).filter(
            InterviewSession.submitted_at >= since,
        ).count()

        body_text, body_html = _digest_body(db, since)

        rendered = render_digest(
            new_shortlists=new_shortlists,
            new_reviews=new_reviews,
            new_rejects=new_rejects,
            new_submits=new_submits,
            digest_body_text=body_text,
            digest_body_html=body_html,
            dashboard_url=f"{_app_base_url()}/hr",
        )
        rendered = type(rendered)(
            subject=f"{rendered.subject} ({now.strftime('%Y-%m-%d')})",
            text=rendered.text,
            html=rendered.html,
        )

        recipients = (
            db.query(User)
            .filter(User.is_active.is_(True), User.role.in_([UserRole.HR, UserRole.ADMIN]))
            .all()
        )
        if not recipients:
            log.info("Digest: no active HR users to notify")
            return 0

        sent = 0
        for user in recipients:
            row = EmailLog(
                candidate_email=user.email,
                template="hr_digest",
                subject=rendered.subject,
                status="queued",
            )
            db.add(row)
            db.flush()
            try:
                send_email(to=user.email, subject=rendered.subject, text=rendered.text, html=rendered.html)
                row.status = "sent"
                sent += 1
            except Exception as e:  # pragma: no cover
                log.exception("Digest email failed to %s", user.email)
                row.status = "failed"
                row.error = str(e)[:500]

        db.add(AuditLog(
            actor_type=ActorType.SYSTEM,
            action="digest.sent",
            entity_type="digest",
            entity_id=now.strftime("%Y-%m-%d"),
            meta={
                "day": now.strftime("%Y-%m-%d"),
                "shortlists": new_shortlists,
                "reviews": new_reviews,
                "rejects": new_rejects,
                "submits": new_submits,
                "recipients": len(recipients),
            },
        ))
        db.commit()
        log.info("Digest delivered to %d HR recipients", sent)
        return sent
    finally:
        if owned:
            db.close()


# ---------- Scheduler lifecycle ----------

_scheduler: Optional[BackgroundScheduler] = None


def start_scheduler() -> BackgroundScheduler:
    """Start APScheduler with the three recurring jobs. Idempotent."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    digest_hour = int(os.environ.get("DIGEST_HOUR_UTC", "13"))  # default 1pm UTC

    sched = BackgroundScheduler(timezone="UTC", daemon=True)
    sched.add_job(expire_past_deadline_sessions, "interval", minutes=10, id="expire_sessions", replace_existing=True)
    sched.add_job(send_expiry_reminders, "interval", minutes=15, id="send_reminders", replace_existing=True)
    sched.add_job(send_daily_digest, "cron", hour=digest_hour, minute=0, id="daily_digest", replace_existing=True)
    sched.start()
    _scheduler = sched
    log.info("Scheduler started (digest at %02d:00 UTC)", digest_hour)
    return sched


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
