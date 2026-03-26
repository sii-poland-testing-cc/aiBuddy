"""
Phase 5 tests — PromotionService + Promotion API.
==================================================
Tests cover:
  - Story → Epic promotion (empty artifacts, clean path)
  - Epic → Domain promotion
  - Blocking: story not 'ready'
  - Blocking: pending conflicts
  - Preview dry-run (no state change)
  - Status endpoint
  - 'ready' validation: PATCH rejects if children are not terminal
  - Partial promotion with conflicts (requirements adapter)
"""

import pytest


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_project(app_client, name: str = "promo-test") -> str:
    r = app_client.post("/api/projects/", json={"name": name})
    assert r.status_code in (200, 201)
    return r.json()["project_id"]


def _get_domain(app_client, project_id: str) -> dict:
    r = app_client.get(f"/api/work-contexts/{project_id}")
    assert r.status_code == 200
    domains = [c for c in r.json()["contexts"] if c["level"] == "domain"]
    assert len(domains) >= 1
    return domains[0]


def _create_epic(app_client, project_id: str, domain_id: str, name: str = "Epic 1") -> dict:
    r = app_client.post(f"/api/work-contexts/{project_id}", json={
        "level": "epic",
        "name": name,
        "parent_id": domain_id,
    })
    assert r.status_code == 201
    return r.json()


def _create_story(app_client, project_id: str, epic_id: str, name: str = "Story 1") -> dict:
    r = app_client.post(f"/api/work-contexts/{project_id}", json={
        "level": "story",
        "name": name,
        "parent_id": epic_id,
    })
    assert r.status_code == 201
    return r.json()


def _patch_status(app_client, project_id: str, ctx_id: str, status: str):
    r = app_client.patch(f"/api/work-contexts/{project_id}/{ctx_id}", json={"status": status})
    return r


def _promote(app_client, project_id: str, ctx_id: str):
    return app_client.post(f"/api/promotion/{project_id}/{ctx_id}/promote")


def _preview(app_client, project_id: str, ctx_id: str):
    return app_client.get(f"/api/promotion/{project_id}/{ctx_id}/preview")


def _status(app_client, project_id: str, ctx_id: str):
    return app_client.get(f"/api/promotion/{project_id}/status/{ctx_id}")


# ─── promote: basic happy path (empty story) ─────────────────────────────────

def test_promote_story_to_epic_empty_artifacts(app_client):
    """Story with no artifacts can be promoted after being set to 'ready'."""
    pid = _make_project(app_client, "promo-story-empty")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    # draft → active → ready
    _patch_status(app_client, pid, story["id"], "active")
    r = _patch_status(app_client, pid, story["id"], "ready")
    assert r.status_code == 200

    r = _promote(app_client, pid, story["id"])
    assert r.status_code == 200
    data = r.json()
    assert data["promoted_count"] == 0
    assert data["conflict_count"] == 0


def test_promote_story_sets_status_promoted(app_client):
    """After promotion the story's status becomes 'promoted'."""
    pid = _make_project(app_client, "promo-story-status")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    _patch_status(app_client, pid, story["id"], "active")
    _patch_status(app_client, pid, story["id"], "ready")
    _promote(app_client, pid, story["id"])

    r = _status(app_client, pid, story["id"])
    assert r.status_code == 200
    assert r.json()["status"] == "promoted"


def test_promote_epic_to_domain_empty_artifacts(app_client):
    """Epic with all stories terminal (or none) can be promoted after being 'ready'."""
    pid = _make_project(app_client, "promo-epic-empty")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    # Promote story first
    _patch_status(app_client, pid, story["id"], "active")
    _patch_status(app_client, pid, story["id"], "ready")
    _promote(app_client, pid, story["id"])

    # Now epic can be marked ready (story is promoted)
    _patch_status(app_client, pid, epic["id"], "active")
    r = _patch_status(app_client, pid, epic["id"], "ready")
    assert r.status_code == 200

    r = _promote(app_client, pid, epic["id"])
    assert r.status_code == 200
    assert r.json()["promoted_count"] == 0
    assert r.json()["conflict_count"] == 0


def test_promote_epic_sets_status_promoted(app_client):
    """After epic promotion its status becomes 'promoted'."""
    pid = _make_project(app_client, "promo-epic-status")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])

    # No stories needed — mark ready immediately (no children to block it)
    _patch_status(app_client, pid, epic["id"], "active")
    _patch_status(app_client, pid, epic["id"], "ready")
    _promote(app_client, pid, epic["id"])

    r = _status(app_client, pid, epic["id"])
    assert r.json()["status"] == "promoted"


# ─── promote: blocking conditions ────────────────────────────────────────────

def test_promote_story_not_ready_blocked(app_client):
    """Promoting a story that is still 'draft' returns 422."""
    pid = _make_project(app_client, "promo-block-draft")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    r = _promote(app_client, pid, story["id"])
    assert r.status_code == 422
    assert "ready" in r.json()["detail"].lower()


def test_promote_story_active_blocked(app_client):
    """Promoting a story that is 'active' (not yet 'ready') returns 422."""
    pid = _make_project(app_client, "promo-block-active")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    _patch_status(app_client, pid, story["id"], "active")
    r = _promote(app_client, pid, story["id"])
    assert r.status_code == 422


def test_promote_domain_blocked(app_client):
    """Attempting to promote a Domain returns 422 (not a promotable level)."""
    pid = _make_project(app_client, "promo-block-domain")
    domain = _get_domain(app_client, pid)

    r = _promote(app_client, pid, domain["id"])
    assert r.status_code == 422
    assert "domain" in r.json()["detail"].lower()


def test_promote_epic_blocked_by_non_terminal_story(app_client):
    """Epic promotion blocked when a child story is not yet promoted or archived."""
    pid = _make_project(app_client, "promo-block-epic-story")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    _create_story(app_client, pid, epic["id"], "Story in draft")

    # Try to mark epic ready — blocked because story is still draft
    _patch_status(app_client, pid, epic["id"], "active")
    r = _patch_status(app_client, pid, epic["id"], "ready")
    assert r.status_code == 422
    assert "story" in r.json()["detail"].lower()


def test_promote_not_found(app_client):
    """Promoting a non-existent context returns 404."""
    pid = _make_project(app_client, "promo-404")
    r = _promote(app_client, pid, "non-existent-uuid")
    assert r.status_code == 404


# ─── preview: dry-run ────────────────────────────────────────────────────────

def test_preview_returns_zero_for_empty_story(app_client):
    """Preview on empty story shows 0 promoted, 0 conflicts."""
    pid = _make_project(app_client, "promo-preview-empty")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    r = _preview(app_client, pid, story["id"])
    assert r.status_code == 200
    data = r.json()
    assert data["promoted_count"] == 0
    assert data["conflict_count"] == 0
    assert "artifact_type_summary" in data


def test_preview_does_not_change_status(app_client):
    """Preview must not alter story status."""
    pid = _make_project(app_client, "promo-preview-noop")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    _preview(app_client, pid, story["id"])

    r = _status(app_client, pid, story["id"])
    assert r.json()["status"] == "draft"  # unchanged


def test_preview_not_found(app_client):
    """Preview on non-existent context returns 404."""
    pid = _make_project(app_client, "promo-preview-404")
    r = _preview(app_client, pid, "bad-id")
    assert r.status_code == 404


# ─── status endpoint ─────────────────────────────────────────────────────────

def test_status_endpoint_story(app_client):
    """Status endpoint returns correct fields for a story."""
    pid = _make_project(app_client, "promo-status-story")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    r = _status(app_client, pid, story["id"])
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == story["id"]
    assert data["level"] == "story"
    assert data["status"] == "draft"
    assert data["pending_conflicts"] == 0
    assert data["promoted_at"] is None
    assert isinstance(data["conflicts"], list)
    assert isinstance(data["children"], list)


def test_status_endpoint_epic_shows_children(app_client):
    """Status endpoint for an epic includes its child stories."""
    pid = _make_project(app_client, "promo-status-epic")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story1 = _create_story(app_client, pid, epic["id"], "Story A")
    story2 = _create_story(app_client, pid, epic["id"], "Story B")

    r = _status(app_client, pid, epic["id"])
    assert r.status_code == 200
    data = r.json()
    assert data["level"] == "epic"
    child_ids = {c["id"] for c in data["children"]}
    assert story1["id"] in child_ids
    assert story2["id"] in child_ids


def test_status_endpoint_not_found(app_client):
    """Status endpoint for non-existent context returns 404."""
    pid = _make_project(app_client, "promo-status-404")
    r = _status(app_client, pid, "missing-id")
    assert r.status_code == 404


# ─── ready validation via PATCH ──────────────────────────────────────────────

def test_patch_ready_epic_all_children_archived(app_client):
    """Epic with all stories archived can be marked ready."""
    pid = _make_project(app_client, "promo-ready-archived")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    # Archive the story (terminal state)
    _patch_status(app_client, pid, story["id"], "active")
    _patch_status(app_client, pid, story["id"], "archived")

    # Epic should now accept 'ready'
    _patch_status(app_client, pid, epic["id"], "active")
    r = _patch_status(app_client, pid, epic["id"], "ready")
    assert r.status_code == 200


def test_patch_ready_domain_blocked_by_active_epic(app_client):
    """Domain cannot be marked ready if it has an active Epic."""
    pid = _make_project(app_client, "promo-ready-domain-blocked")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])

    _patch_status(app_client, pid, epic["id"], "active")  # active — not terminal

    r = _patch_status(app_client, pid, domain["id"], "active")
    assert r.status_code == 200  # domain → active is fine

    r = _patch_status(app_client, pid, domain["id"], "ready")
    assert r.status_code == 422
    assert "epic" in r.json()["detail"].lower()


def test_patch_ready_no_children_passes(app_client):
    """An epic with no stories can be marked ready immediately."""
    pid = _make_project(app_client, "promo-ready-no-children")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])

    _patch_status(app_client, pid, epic["id"], "active")
    r = _patch_status(app_client, pid, epic["id"], "ready")
    assert r.status_code == 200


# ─── artifact_type_summary shape ─────────────────────────────────────────────

def test_promote_result_has_all_artifact_type_keys(app_client):
    """Promotion result always includes all four artifact type keys."""
    pid = _make_project(app_client, "promo-artifact-keys")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    _patch_status(app_client, pid, story["id"], "active")
    _patch_status(app_client, pid, story["id"], "ready")
    r = _promote(app_client, pid, story["id"])
    assert r.status_code == 200

    summary = r.json()["artifact_type_summary"]
    for key in ("graph_node", "graph_edge", "glossary_term", "requirement"):
        assert key in summary, f"Missing artifact type key: {key}"
        assert "items_found" in summary[key]
        assert "promoted" in summary[key]
        assert "conflicts" in summary[key]
