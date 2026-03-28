"""
Auth utilities — JWT + password hashing + FastAPI dependency (Phase 2)
======================================================================
Exports:
  - hash_password(plain)         — Argon2 hash via pwdlib
  - verify_password(plain, hash) — verify plain against stored hash
  - create_access_token(user_id) — encode JWT with user_id + exp
  - decode_access_token(token)   — decode and verify JWT, return payload dict
  - get_current_user(request, db) — FastAPI Depends; reads httpOnly cookie;
                                    returns User (or AnonymousUser when ENFORCE_AUTH=false)
  - AnonymousUser                — dataclass returned when ENFORCE_AUTH=false
"""

import jwt
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.auth_models import User
from app.db.engine import get_db


# ── Password hashing (Argon2 via pwdlib) ─────────────────────────────────────

_password_hash = PasswordHash([Argon2Hasher()])


def hash_password(plain: str) -> str:
    """Hash a plain-text password using Argon2."""
    return _password_hash.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against a stored Argon2 hash."""
    return _password_hash.verify(plain, hashed)


# ── JWT encode / decode ───────────────────────────────────────────────────────

def create_access_token(user_id: str) -> str:
    """Encode a JWT containing only user_id and exp claims (HS256)."""
    payload = {
        "user_id": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(seconds=settings.JWT_TTL_SECONDS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    """Decode and verify a JWT. Raises jwt.PyJWTError on invalid/expired tokens."""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])


# ── Anonymous user (dev/test bypass) ─────────────────────────────────────────

@dataclass
class AnonymousUser:
    """Returned by get_current_user() when ENFORCE_AUTH=false."""
    id: str = "anonymous"
    email: str = "anon@local"
    is_superadmin: bool = False


# ── FastAPI dependency ────────────────────────────────────────────────────────

async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI dependency that resolves the current authenticated user.

    - When ENFORCE_AUTH=false (dev/test): returns AnonymousUser without DB lookup.
    - When ENFORCE_AUTH=true:
        1. Reads JWT from the httpOnly cookie named "access_token".
        2. Validates and decodes the JWT.
        3. Fetches the User row from the DB by user_id.
        4. Raises HTTP 401 if token is missing, invalid, expired, or user not found.
    """
    if not settings.ENFORCE_AUTH:
        return AnonymousUser()

    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    try:
        payload = decode_access_token(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user = await db.get(User, payload["user_id"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user
