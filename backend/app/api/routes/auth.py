"""
Auth API endpoints — register, login, logout, me (Phase 2)
==========================================================
Provides:
  - POST /register — create user account; returns 201 with {id, email}
  - POST /login    — validate credentials; sets httpOnly access_token cookie
  - POST /logout   — clears access_token cookie
  - GET  /me       — returns current user info (requires auth)
"""

from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.auth_models import User
from app.core.auth import hash_password, verify_password, create_access_token, get_current_user
from app.core.config import settings

router = APIRouter()


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    password: str


class RegisterResponse(BaseModel):
    id: str
    email: str


class LoginRequest(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    is_superadmin: bool


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    AUTH-02: Create a new user account.

    Returns 201 with {id, email} on success.
    Returns 409 if the email is already registered.
    Open access — no auth required (D-09).
    """
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(email=body.email, hashed_password=hash_password(body.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return RegisterResponse(id=user.id, email=user.email)


@router.post("/login")
async def login(body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    """
    AUTH-03: Authenticate user and set httpOnly access_token cookie.

    Returns 200 {"message": "ok"} on success with Set-Cookie header.
    Returns 401 on wrong password or unknown email.
    Cookie attributes: httpOnly, samesite=lax, path=/, max_age=JWT_TTL_SECONDS.
    secure=True only in production (APP_ENV=production).
    """
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(user.id)
    secure = settings.APP_ENV == "production"
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=secure,
        max_age=settings.JWT_TTL_SECONDS,
        path="/",
    )
    return {"message": "ok"}


@router.post("/logout")
async def logout(response: Response):
    """
    AUTH-04: Clear the access_token cookie.

    Returns 200 {"message": "ok"} and sets Set-Cookie with max_age=0.
    No auth required — safe to call when already unauthenticated.
    """
    response.delete_cookie(key="access_token", path="/")
    return {"message": "ok"}


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    """
    AUTH-05: Return the currently authenticated user's info.

    Returns 200 with {id, email, is_superadmin} when authenticated.
    Returns 401 when no valid access_token cookie is present (or ENFORCE_AUTH=true).
    When ENFORCE_AUTH=false, returns the anonymous user.
    """
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        is_superadmin=current_user.is_superadmin,
    )
