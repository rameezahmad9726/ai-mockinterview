"""
Post-analysis decision engine.

Runs after a Report has been written by `_run_analysis`. Applies the job's
thresholds + integrity policy to automatically mark each session as
SHORTLISTED / REJECTED / REVIEW, generates an LLM hiring-manager summary,
and queues the appropriate outcome email.

Policy (v1, deterministic and auditable):
  1. If any integrity flag is severe → REVIEW (never auto-decide).
  2. If no overall_score (model failure)  → REVIEW.
  3. If overall_score < job.auto_reject_threshold   → REJECTED.
  4. If overall_score >= job.shortlist_threshold    → SHORTLISTED.
  5. Else                                           → REVIEW.

All decisions are written with actor_type=SYSTEM so HR can distinguish auto-
decisions from manual overrides.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from models import (
    ActorType,
    AuditLog,
    Decision,
    DecisionStatus,
    EmailLog,
    InterviewSession,
    Report,
)
from services.email_service import send_email
from services.email_templates import render_reject, render_shortlist
from services.llm_summary import generate_summary

log = logging.getLogger("interveux.decision")


# Integrity signals that force human review regardless of score.
_SEVERE_FLAG_KINDS = {"multi_face", "face_mismatch", "no_face", "copy_paste"}
_SEVERE_FLAG_COUNT_THRESHOLD = 3  # if more than this of ANY kind, flag for review
_TAB_SWITCH_THRESHOLD = 5


def _is_severe_integrity(flags: Iterable[dict]) -> bool:
    flags = list(flags or [])
    if not flags:
        return False
    counts: dict[str, int] = {}
    for f in flags:
        k = (f or {}).get("kind") or ""
        counts[k] = counts.get(k, 0) + 1
        if k in _SEVERE_FLAG_KINDS and counts[k] >= 1:
            return True
    if counts.get("tab_switch", 0) >= _TAB_SWITCH_THRESHOLD:
        return True
    if sum(counts.values()) >= _SEVERE_FLAG_COUNT_THRESHOLD * 3:
        return True
    return False


def _compute_decision(
    overall_score: Optional[float],
    auto_reject: int,
    shortlist: int,
    has_severe_integrity: bool,
) -> tuple[DecisionStatus, str]:
    if has_severe_integrity:
        return DecisionStatus.REVIEW, "Integrity flags require human review."
    if overall_score is None:
        return DecisionStatus.REVIEW, "No overall score produced by analysis."
    if overall_score < auto_reject:
        return DecisionStatus.REJECTED, f"Score {overall_score:.1f} below auto-reject threshold {auto_reject}."
    if overall_score >= shortlist:
        return DecisionStatus.SHORTLISTED, f"Score {overall_score:.1f} met shortlist threshold {shortlist}."
    return DecisionStatus.REVIEW, (
        f"Score {overall_score:.1f} between thresholds "
        f"({auto_reject}–{shortlist}); manual review."
    )


def _queue_email(
    db: Session,
    sess: InterviewSession,
    template: str,
    subject: str,
    text: str,
    html: str,
) -> Optional[int]:
    """Persist an EmailLog row and dispatch the email synchronously.

    Returns the log id on success. Synchronous dispatch is fine here because
    this function is already running inside a background task.
    """
    log_row = EmailLog(
        session_id=sess.id,
        candidate_email=sess.candidate.email,
        template=template,
        subject=subject,
        status="queued",
    )
    db.add(log_row)
    db.flush()

    try:
        send_email(
            to=sess.candidate.email,
            subject=subject,
            text=text,
            html=html,
        )
        log_row.status = "sent"
    except Exception as e:
        log.exception("Failed to send %s email to %s", template, sess.candidate.email)
        log_row.status = "failed"
        log_row.error = str(e)[:500]
    return log_row.id


def run_for_session(db: Session, session_external_id: str, company: str) -> Optional[Decision]:
    """
    Load a finished session, generate the LLM summary, apply thresholds,
    write the Decision row, and queue the candidate outcome email.
    """
    sess = (
        db.query(InterviewSession)
        .filter(InterviewSession.external_id == session_external_id)
        .first()
    )
    if not sess:
        log.error("Decision engine: session %s not found", session_external_id)
        return None

    report: Optional[Report] = sess.report
    if not report:
        log.info("Decision engine: no report for session %s; skipping", session_external_id)
        return None

    # 1) LLM summary (best-effort).
    if not report.ai_summary:
        summary = generate_summary(
            report.raw_report or {},
            sess.job.title,
            sess.job.required_skills or [],
        )
        if summary:
            report.ai_summary = summary
            db.commit()

    # 2) Auto-decision.
    severe = _is_severe_integrity(sess.integrity_flags or [])
    status, reason = _compute_decision(
        report.overall_score,
        sess.job.auto_reject_threshold,
        sess.job.shortlist_threshold,
        severe,
    )

    existing = sess.decision
    if existing and existing.actor_type == ActorType.HR:
        # Don't overwrite a manual HR decision.
        log.info("Decision engine: manual decision exists for %s; skipping auto", session_external_id)
        return existing

    if existing:
        existing.status = status
        existing.reason = reason
        existing.actor_type = ActorType.SYSTEM
        existing.actor_user_id = None
        existing.updated_at = datetime.utcnow()
        decision = existing
    else:
        decision = Decision(
            session_id=sess.id,
            status=status,
            reason=reason,
            actor_type=ActorType.SYSTEM,
            actor_user_id=None,
        )
        db.add(decision)

    db.add(AuditLog(
        actor_user_id=None,
        actor_type=ActorType.SYSTEM,
        action="decision.auto",
        entity_type="session",
        entity_id=sess.external_id,
        meta={
            "status": status.value,
            "overall_score": report.overall_score,
            "reason": reason,
            "severe_integrity": severe,
        },
    ))
    db.commit()
    db.refresh(sess)

    # 3) Outcome email — only for the two auto-final states.
    if status == DecisionStatus.SHORTLISTED:
        rendered = render_shortlist(
            candidate_name=sess.candidate.full_name or sess.candidate.email.split("@")[0],
            company=company,
            job_title=sess.job.title,
            calendly_url=sess.job.calendly_url,
        )
        _queue_email(db, sess, "shortlist", rendered.subject, rendered.text, rendered.html)
        db.commit()
    elif status == DecisionStatus.REJECTED:
        rendered = render_reject(
            candidate_name=sess.candidate.full_name or sess.candidate.email.split("@")[0],
            company=company,
            job_title=sess.job.title,
        )
        _queue_email(db, sess, "reject", rendered.subject, rendered.text, rendered.html)
        db.commit()
    # REVIEW → no candidate email; HR is the audience.

    return decision
