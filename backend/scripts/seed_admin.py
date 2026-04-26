"""
Create (or update) the bootstrap admin user.

Run from the `backend/` directory so the `modules`/`db`/`auth` absolute imports
resolve correctly:

    cd backend
    python scripts/seed_admin.py

Reads ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_FULL_NAME from `backend/.env`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure backend/ is on sys.path whether run as a script or a module.
_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from dotenv import load_dotenv
load_dotenv(_backend_dir / ".env", override=False)

from auth import hash_password  # noqa: E402
from db import SessionLocal, init_db  # noqa: E402
from models import User, UserRole  # noqa: E402


def main() -> int:
    email = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD") or ""
    full_name = os.environ.get("ADMIN_FULL_NAME") or "Admin"

    if not email or not password:
        print("ERROR: ADMIN_EMAIL and ADMIN_PASSWORD must be set in backend/.env")
        return 2

    init_db()

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            existing.password_hash = hash_password(password)
            existing.full_name = full_name
            existing.role = UserRole.ADMIN
            existing.is_active = True
            db.commit()
            print(f"Updated existing admin user: {email}")
        else:
            user = User(
                email=email,
                password_hash=hash_password(password),
                full_name=full_name,
                role=UserRole.ADMIN,
                is_active=True,
            )
            db.add(user)
            db.commit()
            print(f"Created admin user: {email}")
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
