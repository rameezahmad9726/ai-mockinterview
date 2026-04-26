"""
Authentication + JWT helpers for HR users and candidate session tokens.

- HR access tokens: issued on login, carry user_id + role.
- Candidate session tokens: long-lived, signed JWTs embedded in invite links.
  Both use the same secret but different `typ` claims to prevent confusion.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from db import get_db
from models import InterviewSession, SessionStatus, User, UserRole

_backend_dir = Path(__file__).resolve().parent
load_dotenv(_backend_dir / ".env", override=False)

JWT_SECRET = os.getenv("JWT_SECRET") or secrets.token_urlsafe(48)
JWT_ALG = os.getenv("JWT_ALG", "HS256")
JWT_EXPIRES_MIN = int(os.getenv("JWT_EXPIRES_MIN", "720"))  # 12h default

_TYP_ACCESS = "access"
_TYP_SESSION = "session"

bearer_scheme = HTTPBearer(auto_error=False)


# ---------- Passwords ----------

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ---------- JWT: HR access tokens ----------

def create_access_token(user: User, expires_minutes: Optional[int] = None) -> tuple[str, int]:
    minutes = expires_minutes or JWT_EXPIRES_MIN
    exp = datetime.utcnow() + timedelta(minutes=minutes)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value,
        "typ": _TYP_ACCESS,
        "exp": exp,
        "iat": datetime.utcnow(),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)
    return token, minutes * 60


# ---------- JWT: Candidate session tokens ----------

def create_session_token(external_id: str, expires_at: datetime) -> str:
    """Long-lived token used in invite links. `sub` is the session external_id."""
    payload = {
        "sub": external_id,
        "typ": _TYP_SESSION,
        "exp": expires_at,
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decode_token(token: str, expected_typ: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    if payload.get("typ") != expected_typ:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong token type")
    return payload


# ---------- FastAPI dependencies ----------

def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_token(creds.credentials, _TYP_ACCESS)
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")

    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


def get_current_user_bearer_or_query(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    token: Optional[str] = Query(None, description="HR access JWT for contexts that cannot send Authorization (e.g. iframes)."),
    db: Session = Depends(get_db),
) -> User:
    """Same as get_current_user, but also accepts `?token=` for iframe/embed use."""
    raw = None
    if creds and creds.credentials:
        raw = creds.credentials
    elif token:
        raw = token
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_token(raw, _TYP_ACCESS)
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")

    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


def require_role(*roles: UserRole):
    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user
    return _dep


def require_role_bearer_or_query(*roles: UserRole):
    def _dep(user: User = Depends(get_current_user_bearer_or_query)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user
    return _dep


require_hr = require_role(UserRole.HR, UserRole.ADMIN)
require_hr_bearer_or_query = require_role_bearer_or_query(UserRole.HR, UserRole.ADMIN)
require_admin = require_role(UserRole.ADMIN)


def get_session_by_token(
    token: str,
    db: Session = Depends(get_db),
) -> InterviewSession:
    """Resolve a candidate-facing session token → InterviewSession row.

    Enforces expiry and session lifecycle. Does NOT reveal whether the email
    address on the link matches anyone — token possession is the credential.
    """
    payload = decode_token(token, _TYP_SESSION)
    external_id = payload.get("sub")
    if not external_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session token")

    sess = db.query(InterviewSession).filter(InterviewSession.external_id == external_id).first()
    if not sess:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if sess.token != token:
        # Allows HR to rotate/invalidate old invite links for retakes.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session token")

    now = datetime.utcnow()
    if sess.expires_at and sess.expires_at < now and sess.status in {
        SessionStatus.INVITED,
        SessionStatus.STARTED,
    }:
        sess.status = SessionStatus.EXPIRED
        db.commit()

    if sess.status == SessionStatus.EXPIRED:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Interview link has expired")

    return sess
