"""
SQLAlchemy ORM models for the HR automation layer.

Single-org for v1. Add an `organization_id` FK later if multi-tenant is needed.
JSON columns are used for flexible/structured fields (questions, scores, flags,
audit metadata) to keep the schema readable without over-normalizing.
"""

from __future__ import annotations

import enum
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    HR = "hr"


class JobStatus(str, enum.Enum):
    DRAFT = "draft"
    OPEN = "open"
    CLOSED = "closed"


class SessionStatus(str, enum.Enum):
    INVITED = "invited"
    STARTED = "started"
    SUBMITTED = "submitted"
    ANALYZING = "analyzing"
    SCORED = "scored"
    EXPIRED = "expired"
    FAILED = "failed"


class DecisionStatus(str, enum.Enum):
    SHORTLISTED = "shortlisted"
    REJECTED = "rejected"
    REVIEW = "review"
    ADVANCED = "advanced"
    WITHDRAWN = "withdrawn"


class ActorType(str, enum.Enum):
    SYSTEM = "system"
    HR = "hr"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.HR, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    jobs: Mapped[list["Job"]] = relationship(back_populates="created_by")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    department: Mapped[Optional[str]] = mapped_column(String(255))
    seniority: Mapped[Optional[str]] = mapped_column(String(64))
    jd_text: Mapped[Optional[str]] = mapped_column(Text)
    required_skills: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    required_certifications: Mapped[Optional[list]] = mapped_column(JSON, default=list)

    # Interview config (defaults match Phase 1 spec)
    num_questions: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    seconds_per_answer: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    allow_retakes: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    link_expiry_hours: Mapped[int] = mapped_column(Integer, default=72, nullable=False)

    # Decisioning thresholds (0–100)
    auto_reject_threshold: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    shortlist_threshold: Mapped[int] = mapped_column(Integer, default=80, nullable=False)

    # Calendly / human-round self-booking link
    calendly_url: Mapped[Optional[str]] = mapped_column(String(1024))

    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.OPEN, nullable=False)

    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    created_by: Mapped["User"] = relationship(back_populates="jobs")
    sessions: Mapped[list["InterviewSession"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    sessions: Mapped[list["InterviewSession"]] = relationship(back_populates="candidate")


class InterviewSession(Base):
    """
    One row per (candidate, job) interview instance. Holds the signed token,
    lifecycle status, and all artifacts needed for processing + reporting.
    """

    __tablename__ = "interview_sessions"
    __table_args__ = (
        UniqueConstraint("job_id", "candidate_id", name="uq_session_job_candidate"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Public token shared via email (JWT string). Kept indexed for fast lookup.
    token: Mapped[str] = mapped_column(String(1024), unique=True, index=True, nullable=False)

    # External UUID reused as the "session_id" by video_processor for compatibility
    # with existing upload/report paths (uploads/<uuid>/..., reports/<uuid>_*.json).
    external_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False, index=True)

    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus), default=SessionStatus.INVITED, nullable=False, index=True
    )

    # Lifecycle timestamps
    invited_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    analyzed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Content captured at invite / interview time
    questions: Mapped[Optional[list]] = mapped_column(JSON)           # list[{type, question}]
    answer_windows: Mapped[Optional[list]] = mapped_column(JSON)      # list[{question_idx, start_sec, end_sec}]
    integrity_flags: Mapped[Optional[list]] = mapped_column(JSON, default=list)

    # File paths on disk (served by existing upload/reports routes)
    resume_path: Mapped[Optional[str]] = mapped_column(String(1024))
    resume_context: Mapped[Optional[dict]] = mapped_column(JSON)
    video_path: Mapped[Optional[str]] = mapped_column(String(1024))

    # Runtime status text for polling (mirrors progress_store in main.py)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress_message: Mapped[Optional[str]] = mapped_column(String(512))
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    job: Mapped["Job"] = relationship(back_populates="sessions")
    candidate: Mapped["Candidate"] = relationship(back_populates="sessions")
    report: Mapped[Optional["Report"]] = relationship(
        back_populates="session", uselist=False, cascade="all, delete-orphan"
    )
    decision: Mapped[Optional["Decision"]] = relationship(
        back_populates="session", uselist=False, cascade="all, delete-orphan"
    )

    @staticmethod
    def default_expiry(hours: int = 72) -> datetime:
        return _utcnow() + timedelta(hours=hours)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("interview_sessions.id"), unique=True, nullable=False
    )

    overall_score: Mapped[Optional[float]] = mapped_column(Float)
    sub_scores: Mapped[Optional[dict]] = mapped_column(JSON)          # {speech: .., body: .., emotion: ..}
    ai_summary: Mapped[Optional[dict]] = mapped_column(JSON)          # {strengths, concerns, recommendation, quotes}
    raw_report: Mapped[Optional[dict]] = mapped_column(JSON)          # full JSON from video_processor

    report_json_path: Mapped[Optional[str]] = mapped_column(String(1024))
    report_html_path: Mapped[Optional[str]] = mapped_column(String(1024))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    session: Mapped["InterviewSession"] = relationship(back_populates="report")


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("interview_sessions.id"), unique=True, nullable=False
    )

    status: Mapped[DecisionStatus] = mapped_column(Enum(DecisionStatus), nullable=False, index=True)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    actor_type: Mapped[ActorType] = mapped_column(Enum(ActorType), default=ActorType.SYSTEM, nullable=False)
    actor_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    session: Mapped["InterviewSession"] = relationship(back_populates="decision")


class EmailLog(Base):
    __tablename__ = "email_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[Optional[int]] = mapped_column(ForeignKey("interview_sessions.id"), index=True)
    candidate_email: Mapped[str] = mapped_column(String(320), nullable=False)
    template: Mapped[str] = mapped_column(String(64), nullable=False)  # invite, reminder, shortlist, reject, ...
    subject: Mapped[Optional[str]] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)  # queued/sent/failed
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    actor_type: Mapped[ActorType] = mapped_column(Enum(ActorType), default=ActorType.SYSTEM, nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(String(64))
    entity_id: Mapped[Optional[str]] = mapped_column(String(64))
    meta: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
