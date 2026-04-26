"""
Authentication endpoints for HR users.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import create_access_token, get_current_user, verify_password
from db import get_db
from models import ActorType, AuditLog, User
from schemas import LoginRequest, TokenResponse, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        # Intentionally vague to avoid user enumeration.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token, ttl_seconds = create_access_token(user)

    db.add(AuditLog(
        actor_user_id=user.id,
        actor_type=ActorType.HR,
        action="login",
        entity_type="user",
        entity_id=str(user.id),
    ))
    db.commit()

    return TokenResponse(access_token=token, expires_in=ttl_seconds)


@router.get("/me", response_model=UserOut)
def me(current: User = Depends(get_current_user)) -> User:
    return current
