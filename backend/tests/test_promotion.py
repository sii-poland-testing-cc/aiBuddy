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
  - D10 visibility-based promotion (visibility rows, no data copy)
  - Chained promotion: Story → Epic → Domain
  - Edit-after-promotion: changes in source visible at higher levels
"""

import asyncio
import uuid

import pytest

from app.db.engine import AsyncSessionLocal
from app.db.models import ArtifactVisibility, Project, WorkContext
from sqlalchemy import select


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


# ── D10 visibility-based promotion ──────────────────────────────────────────

def _run(coro):
    """Run an async coroutine from sync test code."""
    return asyncio.get_event_loop().run_until_complete(coro)


async def _seed_graph_items(project_id: str, story_id: str):
    """
    Seed a project with mind_map data and ArtifactVisibility rows
    for 2 graph nodes and 1 edge in the given story context.
    """
    async with AsyncSessionLocal() as db:
        project = await db.get(Project, project_id)
        project.mind_map = {
            "nodes": [
                {"id": "e1", "label": "Payment", "type": "data"},
                {"id": "e2", "label": "User", "type": "actor"},
            ],
            "edges": [
                {"source": "e1", "target": "e2", "label": "initiates"},
            ],
        }
        now_dt = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)

        for item_id, art_type in [("e1", "graph_node"), ("e2", "graph_node"),
                                   ("e1→e2", "graph_edge")]:
            db.add(ArtifactVisibility(
                id=str(uuid.uuid4()),
                project_id=project_id,
                artifact_type=art_type,
                artifact_item_id=item_id,
                source_context_id=story_id,
                visible_in_context_id=story_id,
                lifecycle_status="active",
                created_at=now_dt,
            ))
        await db.commit()


async def _seed_glossary_items(project_id: str, story_id: str):
    """Seed a project with glossary data and visibility rows."""
    async with AsyncSessionLocal() as db:
        project = await db.get(Project, project_id)
        project.glossary = [
            {"term": "Payment", "definition": "A transfer of money."},
        ]
        now_dt = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        db.add(ArtifactVisibility(
            id=str(uuid.uuid4()),
            project_id=project_id,
            artifact_type="glossary_term",
            artifact_item_id="payment",
            source_context_id=story_id,
            visible_in_context_id=story_id,
            lifecycle_status="active",
            created_at=now_dt,
        ))
        await db.commit()


async def _count_visibility_rows(project_id: str, visible_in: str, art_type: str) -> int:
    """Count ArtifactVisibility rows visible in a given context for a type."""
    async with AsyncSessionLocal() as db:
        stmt = select(ArtifactVisibility).where(
            ArtifactVisibility.project_id == project_id,
            ArtifactVisibility.artifact_type == art_type,
            ArtifactVisibility.visible_in_context_id == visible_in,
        )
        rows = (await db.execute(stmt)).scalars().all()
        return len(rows)


async def _get_visibility_rows(project_id: str, item_id: str, art_type: str) -> list:
    """Get all visibility rows for a specific item across all contexts."""
    async with AsyncSessionLocal() as db:
        stmt = select(ArtifactVisibility).where(
            ArtifactVisibility.project_id == project_id,
            ArtifactVisibility.artifact_type == art_type,
            ArtifactVisibility.artifact_item_id == item_id,
        )
        return (await db.execute(stmt)).scalars().all()


def test_promote_story_creates_visibility_rows(app_client):
    """
    D10: promoting a story with graph nodes creates ArtifactVisibility rows
    in the epic context. No data is copied.
    """
    pid = _make_project(app_client, "promo-d10-vis")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    _run(_seed_graph_items(pid, story["id"]))

    _patch_status(app_client, pid, story["id"], "active")
    _patch_status(app_client, pid, story["id"], "ready")
    r = _promote(app_client, pid, story["id"])
    assert r.status_code == 200

    data = r.json()
    assert data["promoted_count"] == 3  # 2 nodes + 1 edge
    assert data["conflict_count"] == 0

    # Verify visibility rows created in epic
    epic_nodes = _run(_count_visibility_rows(pid, epic["id"], "graph_node"))
    assert epic_nodes == 2
    epic_edges = _run(_count_visibility_rows(pid, epic["id"], "graph_edge"))
    assert epic_edges == 1


def test_promote_items_remain_in_source_story(app_client):
    """
    D10: after promotion, items are still visible in the source story.
    Promotion inserts new rows, does NOT move/delete originals.
    """
    pid = _make_project(app_client, "promo-d10-remain")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    _run(_seed_graph_items(pid, story["id"]))

    _patch_status(app_client, pid, story["id"], "active")
    _patch_status(app_client, pid, story["id"], "ready")
    _promote(app_client, pid, story["id"])

    # Original visibility rows in story still exist
    story_nodes = _run(_count_visibility_rows(pid, story["id"], "graph_node"))
    assert story_nodes == 2  # NOT moved, still there
    story_edges = _run(_count_visibility_rows(pid, story["id"], "graph_edge"))
    assert story_edges == 1


def test_promote_visibility_row_has_correct_source_context(app_client):
    """
    D10: promoted visibility rows point back to the original source context
    (the story where the item was created), NOT the target context.
    """
    pid = _make_project(app_client, "promo-d10-source")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    _run(_seed_graph_items(pid, story["id"]))

    _patch_status(app_client, pid, story["id"], "active")
    _patch_status(app_client, pid, story["id"], "ready")
    _promote(app_client, pid, story["id"])

    # Check that the epic-level visibility row has source_context_id = story
    rows = _run(_get_visibility_rows(pid, "e1", "graph_node"))
    epic_rows = [r for r in rows if r.visible_in_context_id == epic["id"]]
    assert len(epic_rows) == 1
    assert epic_rows[0].source_context_id == story["id"]
    assert epic_rows[0].lifecycle_status == "promoted"


def test_chained_promotion_story_epic_domain(app_client):
    """
    D10 chained promotion: Story→Epic→Domain produces 3 visibility rows
    for the same item, all pointing to the same source_context_id (story).
    """
    pid = _make_project(app_client, "promo-d10-chain")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    _run(_seed_graph_items(pid, story["id"]))

    # Story → Epic
    _patch_status(app_client, pid, story["id"], "active")
    _patch_status(app_client, pid, story["id"], "ready")
    r1 = _promote(app_client, pid, story["id"])
    assert r1.status_code == 200
    assert r1.json()["promoted_count"] == 3

    # Epic → Domain
    _patch_status(app_client, pid, epic["id"], "active")
    _patch_status(app_client, pid, epic["id"], "ready")
    r2 = _promote(app_client, pid, epic["id"])
    assert r2.status_code == 200
    assert r2.json()["promoted_count"] == 3

    # Node "e1" should now have 3 visibility rows:
    # 1. story (original), 2. epic (promoted), 3. domain (promoted)
    rows = _run(_get_visibility_rows(pid, "e1", "graph_node"))
    assert len(rows) == 3

    contexts = {r.visible_in_context_id for r in rows}
    assert story["id"] in contexts
    assert epic["id"] in contexts
    assert domain["id"] in contexts

    # All rows point to the same source context (the story)
    source_ids = {r.source_context_id for r in rows}
    assert source_ids == {story["id"]}


def test_promote_glossary_creates_visibility_rows(app_client):
    """D10: glossary terms get visibility rows on promotion, not data copies."""
    pid = _make_project(app_client, "promo-d10-gloss")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    _run(_seed_glossary_items(pid, story["id"]))

    _patch_status(app_client, pid, story["id"], "active")
    _patch_status(app_client, pid, story["id"], "ready")
    r = _promote(app_client, pid, story["id"])
    assert r.status_code == 200

    # Glossary term should have 1 new visibility row in epic
    epic_terms = _run(_count_visibility_rows(pid, epic["id"], "glossary_term"))
    assert epic_terms == 1

    # Original still in story
    story_terms = _run(_count_visibility_rows(pid, story["id"], "glossary_term"))
    assert story_terms == 1


def test_preview_does_not_create_visibility_rows(app_client):
    """Preview (dry-run) must not create any ArtifactVisibility rows."""
    pid = _make_project(app_client, "promo-d10-preview")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    _run(_seed_graph_items(pid, story["id"]))

    r = _preview(app_client, pid, story["id"])
    assert r.status_code == 200
    assert r.json()["promoted_count"] == 3

    # No visibility rows should exist in epic
    epic_nodes = _run(_count_visibility_rows(pid, epic["id"], "graph_node"))
    assert epic_nodes == 0


def test_edit_after_promotion_visible_at_epic(app_client):
    """
    D10: after promotion, there is only ONE copy of the data (Project.mind_map).
    Visibility rows in both story and epic reference the same project,
    so any edit to the JSON blob is automatically visible at all levels.

    We verify this by checking that:
    1. Visibility rows exist in both story and epic
    2. Both point to the same project (no data copy)
    3. The mind_map on the project is the single source of truth
    """
    pid = _make_project(app_client, "promo-d10-edit")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    _run(_seed_graph_items(pid, story["id"]))

    _patch_status(app_client, pid, story["id"], "active")
    _patch_status(app_client, pid, story["id"], "ready")
    _promote(app_client, pid, story["id"])

    # Verify: e1 has visibility rows in both story and epic,
    # and both reference the same project_id (same underlying data)
    rows = _run(_get_visibility_rows(pid, "e1", "graph_node"))
    assert len(rows) == 2
    visible_contexts = {r.visible_in_context_id for r in rows}
    assert story["id"] in visible_contexts
    assert epic["id"] in visible_contexts

    # All rows reference the same project — no data copied anywhere else
    project_ids = {r.project_id for r in rows}
    assert project_ids == {pid}

    # The D10 model guarantees: since both visibility rows reference
    # the same Project.mind_map (via project_id), any edit to mind_map
    # is immediately visible at all levels without additional DB writes.
