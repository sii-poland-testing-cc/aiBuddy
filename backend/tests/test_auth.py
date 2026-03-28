"""
test_auth.py — Comprehensive tests for auth API endpoints (Phase 2).
=====================================================================
Covers: register, login, logout, /me, JWT payload shape, ENFORCE_AUTH bypass.

AUTH-01: users table exists with correct columns
AUTH-02: register creates user, 409 on duplicate
AUTH-03: login sets httpOnly cookie, 401 on bad creds
AUTH-04: logout clears cookie
AUTH-05: /me returns user info or 401
AUTH-06: JWT payload contains only user_id + exp
AUTH-07: get_current_user raises 401 when no cookie
AUTH-08: ENFORCE_AUTH=false returns anonymous user; existing routes work

Run from backend/ with:
    pytest tests/test_auth.py -v
"""

import os
import pytest
from app.core.auth import create_access_token, decode_access_token


# ── Auth toggle fixture ───────────────────────────────────────────────────────

@pytest.fixture
def auth_enabled():
    """Temporarily enable auth enforcement for tests that require it.

    The fixture patches settings in all modules that import it by name,
    because `from app.core.config import settings` creates a local binding
    that won't be updated by reassigning config_mod.settings alone.
    """
    old = os.environ.get("ENFORCE_AUTH")
    os.environ["ENFORCE_AUTH"] = "true"
    from app.core.config import Settings
    import app.core.config as config_mod
    import app.core.auth as auth_mod
    new_settings = Settings()
    config_mod.settings = new_settings
    # Patch the reference in auth module (from app.core.config import settings)
    auth_mod.settings = new_settings
    yield
    if old is not None:
        os.environ["ENFORCE_AUTH"] = old
    else:
        os.environ.pop("ENFORCE_AUTH", None)
    restored = Settings()
    config_mod.settings = restored
    auth_mod.settings = restored


# ── Test helpers ──────────────────────────────────────────────────────────────

def register_user(client, email="test@example.com", password="securepass123"):
    return client.post("/api/auth/register", json={"email": email, "password": password})


def login_user(client, email="test@example.com", password="securepass123"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# ── AUTH-01: users table ──────────────────────────────────────────────────────

def test_users_table_exists(app_client):
    """AUTH-01: users table exists in DB with correct columns."""
    from app.db.models import Base
    assert "users" in Base.metadata.tables, "users table not in metadata"
    cols = {c.name for c in Base.metadata.tables["users"].columns}
    assert cols >= {"id", "email", "hashed_password", "is_superadmin", "created_at"}, \
        f"Missing columns in users table; found: {cols}"


# ── AUTH-02: register ─────────────────────────────────────────────────────────

def test_register_creates_user(app_client, auth_enabled):
    """AUTH-02: POST /api/auth/register returns 201 with id and email."""
    resp = register_user(app_client, "new@test.com")
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "id" in data, f"Missing 'id' in response: {data}"
    assert data["email"] == "new@test.com", f"Wrong email in response: {data}"
    # id must be a non-empty string (UUID)
    assert isinstance(data["id"], str) and len(data["id"]) > 0


def test_register_duplicate_email(app_client, auth_enabled):
    """AUTH-02: Second register with same email returns 409."""
    register_user(app_client, "dup@test.com")
    resp = register_user(app_client, "dup@test.com")
    assert resp.status_code == 409, f"Expected 409, got {resp.status_code}: {resp.text}"


# ── AUTH-03: login ────────────────────────────────────────────────────────────

def test_login_sets_cookie(app_client, auth_enabled):
    """AUTH-03: POST /api/auth/login with valid credentials sets httpOnly access_token cookie."""
    register_user(app_client, "login@test.com")
    resp = login_user(app_client, "login@test.com")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    # Check Set-Cookie header attributes
    cookie_header = resp.headers.get("set-cookie", "")
    assert "access_token" in cookie_header, f"access_token not in Set-Cookie: {cookie_header}"
    assert "httponly" in cookie_header.lower(), f"httponly not in Set-Cookie: {cookie_header}"
    assert "samesite=lax" in cookie_header.lower(), f"samesite=lax not in Set-Cookie: {cookie_header}"
    assert "path=/" in cookie_header.lower(), f"path=/ not in Set-Cookie: {cookie_header}"


def test_login_wrong_password(app_client, auth_enabled):
    """AUTH-03: POST /api/auth/login with wrong password returns 401."""
    register_user(app_client, "wrongpw@test.com")
    resp = login_user(app_client, "wrongpw@test.com", "badpassword")
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"


def test_login_nonexistent_email(app_client, auth_enabled):
    """AUTH-03: POST /api/auth/login with unknown email returns 401."""
    resp = login_user(app_client, "noexist@test.com")
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"


# ── AUTH-04: logout ───────────────────────────────────────────────────────────

def test_logout_clears_cookie(app_client, auth_enabled):
    """AUTH-04: POST /api/auth/logout clears the access_token cookie."""
    register_user(app_client, "logout@test.com")
    login_user(app_client, "logout@test.com")
    resp = app_client.post("/api/auth/logout")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    cookie_header = resp.headers.get("set-cookie", "")
    assert "access_token" in cookie_header, f"access_token not in Set-Cookie after logout: {cookie_header}"
    # Cookie cleared: max-age=0 or expires in past (Jan 1970)
    cleared = "max-age=0" in cookie_header.lower() or "01 jan 1970" in cookie_header.lower()
    assert cleared, f"Cookie not cleared after logout (expected max-age=0 or expired): {cookie_header}"


# ── AUTH-05: /me ──────────────────────────────────────────────────────────────

def test_me_authenticated(app_client, auth_enabled):
    """AUTH-05: GET /api/auth/me with valid cookie returns {id, email, is_superadmin}."""
    register_user(app_client, "me@test.com")
    login_user(app_client, "me@test.com")
    resp = app_client.get("/api/auth/me")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["email"] == "me@test.com", f"Wrong email: {data}"
    assert "id" in data, f"Missing 'id': {data}"
    assert "is_superadmin" in data, f"Missing 'is_superadmin': {data}"
    assert data["is_superadmin"] is False  # regular user, not superadmin


def test_me_unauthenticated(app_client, auth_enabled):
    """AUTH-05: GET /api/auth/me without cookie returns 401."""
    # Fresh client with no cookies — ensures no session state from other tests
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as fresh_client:
        resp = fresh_client.get("/api/auth/me")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"


# ── AUTH-06: JWT payload shape ────────────────────────────────────────────────

def test_jwt_payload_shape():
    """AUTH-06: create_access_token produces token with exactly user_id and exp claims."""
    token = create_access_token("user-123")
    payload = decode_access_token(token)
    assert set(payload.keys()) == {"user_id", "exp"}, \
        f"Unexpected payload keys: {set(payload.keys())}"
    assert payload["user_id"] == "user-123", f"Wrong user_id: {payload['user_id']}"
    # exp must be a future timestamp (integer or float)
    import time
    assert payload["exp"] > time.time(), f"Token already expired: exp={payload['exp']}"


# ── AUTH-07: get_current_user dependency ─────────────────────────────────────

def test_get_current_user_no_token(app_client, auth_enabled):
    """AUTH-07: GET /api/auth/me without access_token cookie raises 401."""
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as fresh_client:
        resp = fresh_client.get("/api/auth/me")
        assert resp.status_code == 401


# ── AUTH-08: ENFORCE_AUTH bypass ──────────────────────────────────────────────

def test_enforce_auth_false(app_client):
    """AUTH-08: With ENFORCE_AUTH=false (conftest default), /me returns anonymous user."""
    # conftest sets ENFORCE_AUTH=false by default
    resp = app_client.get("/api/auth/me")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["email"] == "anon@local", f"Expected anonymous user, got: {data}"
    assert data["id"] == "anonymous", f"Expected anonymous id, got: {data}"
    assert data["is_superadmin"] is False


def test_existing_project_api_still_works(app_client):
    """AUTH-08: Existing /api/projects/ route works with ENFORCE_AUTH=false."""
    resp = app_client.get("/api/projects/")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
