"""
Pydantic v1 request/response schemas for the HR + candidate APIs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field

from models import DecisionStatus, JobStatus, SessionStatus, UserRole


# ---------- Auth ----------

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: Optional[str] = None
    role: UserRole
    is_active: bool
    created_at: datetime

    class Config:
        orm_mode = True


# ---------- Jobs ----------

class JobBase(BaseModel):
    title: str
    department: Optional[str] = None
    seniority: Optional[str] = None
    jd_text: Optional[str] = None
    required_skills: list[str] = Field(default_factory=list)
    required_certifications: list[str] = Field(default_factory=list)

    num_questions: int = 5
    seconds_per_answer: int = 90
    allow_retakes: bool = False
    link_expiry_hours: int = 72

    auto_reject_threshold: int = 50
    shortlist_threshold: int = 80

    calendly_url: Optional[str] = None
    status: JobStatus = JobStatus.OPEN


class JobCreate(JobBase):
    pass


class JobUpdate(BaseModel):
    title: Optional[str] = None
    department: Optional[str] = None
    seniority: Optional[str] = None
    jd_text: Optional[str] = None
    required_skills: Optional[list[str]] = None
    required_certifications: Optional[list[str]] = None
    num_questions: Optional[int] = None
    seconds_per_answer: Optional[int] = None
    allow_retakes: Optional[bool] = None
    link_expiry_hours: Optional[int] = None
    auto_reject_threshold: Optional[int] = None
    shortlist_threshold: Optional[int] = None
    calendly_url: Optional[str] = None
    status: Optional[JobStatus] = None


class JobOut(JobBase):
    id: int
    created_by_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


# ---------- Candidates & Invites ----------

class InviteItem(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None


class BulkInviteRequest(BaseModel):
    invites: list[InviteItem]


class BulkInviteResult(BaseModel):
    created: int
    skipped: int
    session_ids: list[str]


class CandidateOut(BaseModel):
    id: int
    email: EmailStr
    full_name: Optional[str] = None
    phone: Optional[str] = None
    created_at: datetime

    class Config:
        orm_mode = True


# ---------- Interview sessions (HR view) ----------

class SessionSummary(BaseModel):
    id: int
    external_id: str
    job_id: int
    candidate: CandidateOut
    status: SessionStatus
    invited_at: datetime
    expires_at: datetime
    submitted_at: Optional[datetime] = None
    progress: int = 0
    progress_message: Optional[str] = None
    error_message: Optional[str] = None
    overall_score: Optional[float] = None
    decision: Optional[DecisionStatus] = None

    class Config:
        orm_mode = True


class SessionDetail(SessionSummary):
    questions: Optional[list] = None
    answer_windows: Optional[list] = None
    integrity_flags: Optional[list] = None
    sub_scores: Optional[dict] = None
    ai_summary: Optional[dict] = None
    report_json_path: Optional[str] = None
    report_html_path: Optional[str] = None


# ---------- Candidate-facing (public, token-protected) ----------

class CandidateInterviewInfo(BaseModel):
    """Shape returned to the candidate after validating their token."""
    session_external_id: str
    job_title: str
    company: Optional[str] = None
    num_questions: int
    seconds_per_answer: int
    allow_retakes: bool
    expires_at: datetime
    status: SessionStatus
    has_resume: bool
    questions: Optional[list] = None  # only populated once resume is uploaded / questions generated


class IntegrityEvent(BaseModel):
    kind: str           # tab_switch | no_face | multi_face | silence | copy_paste
    at_sec: float
    meta: Optional[dict[str, Any]] = None


# ---------- Decisions ----------

class DecisionUpdate(BaseModel):
    status: DecisionStatus
    reason: Optional[str] = None
    send_email: bool = False  # when true, notify candidate on shortlist/reject/advanced


class BulkDecisionRequest(BaseModel):
    """
    Flexible bulk-action payload. Either provide `session_ids` to apply the
    status explicitly to a list, OR `rule` in {"top_n","below_score"} with the
    matching parameter to let the server pick.
    """
    status: DecisionStatus
    reason: Optional[str] = None
    send_email: bool = False
    session_ids: Optional[list[str]] = None
    rule: Optional[str] = None              # "top_n" | "below_score" | "above_score"
    top_n: Optional[int] = None
    score: Optional[float] = None


class BulkDecisionResult(BaseModel):
    updated: int
    skipped: int
    session_ids: list[str]
