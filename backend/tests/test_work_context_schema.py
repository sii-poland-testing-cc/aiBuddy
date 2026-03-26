"""
Phase 1 schema tests — work_context & lifecycle tables.
=======================================================
Verifies that:
  - All new tables exist and are queryable after DB initialisation
  - WorkContext CRUD works (create / read / delete)
  - ArtifactAuditLog rows can be created
  - PromotionConflict CRUD works
  - ArtifactLifecycle manifest rows work (including unique constraint)
  - Existing Requirement rows default to lifecycle_status="promoted"
  - Existing AuditSnapshot rows default to lifecycle_status="promoted"

These are schema-level tests only — no API, no business logic.
"""

import asyncio
import uuid
from datetime import datetime, timezone

import pytest

from app.db.engine import AsyncSessionLocal
from app.db.models import ArtifactAuditLog, ArtifactLifecycle, AuditSnapshot, Project, PromotionConflict, WorkContext
from app.db.requirements_models import Requirement
from sqlalchemy import select, text


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _project_id(app_client) -> str:
    """Create a project via the API and return its id."""
    r = app_client.post("/api/projects/", json={"name": "lifecycle-schema-test"})
    assert r.status_code in (200, 201)
    return r.json()["project_id"]


def _run(coro):
    """Run an async coroutine from a sync test."""
    return asyncio.run(coro)


# ─── Schema presence ─────────────────────────────────────────────────────────

def test_new_tables_exist(app_client):
    """All four new tables should be queryable after app startup."""
    async def _check():
        async with AsyncSessionLocal() as db:
            for tbl in (
                "work_contexts",
                "artifact_audit_log",
                "promotion_conflicts",
                "artifact_lifecycle",
            ):
                result = await db.execute(text(f"SELECT 1 FROM {tbl} LIMIT 1"))
                # Query succeeds (empty is fine)
                result.fetchall()

    _run(_check())


def test_requirements_has_lifecycle_columns(app_client):
    """requirements table must have work_context_id and lifecycle_status columns."""
    async def _check():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text("SELECT work_context_id, lifecycle_status FROM requirements LIMIT 1")
            )
            result.fetchall()  # no error = columns exist

    _run(_check())


def test_audit_snapshots_has_lifecycle_columns(app_client):
    """audit_snapshots table must have work_context_id and lifecycle_status columns."""
    async def _check():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text("SELECT work_context_id, lifecycle_status FROM audit_snapshots LIMIT 1")
            )
            result.fetchall()

    _run(_check())


# ─── WorkContext CRUD ─────────────────────────────────────────────────────────

def test_work_context_create_and_read(app_client):
    """WorkContext can be inserted and queried back."""
    project_id = _project_id(app_client)

    async def _run_test():
        async with AsyncSessionLocal() as db:
            wc = WorkContext(
                project_id=project_id,
                parent_id=None,
                level="domain",
                name="Test Domain",
                status="draft",
            )
            db.add(wc)
            await db.commit()
            await db.refresh(wc)
            wc_id = wc.id

        async with AsyncSessionLocal() as db:
            fetched = await db.get(WorkContext, wc_id)
            assert fetched is not None
            assert fetched.level == "domain"
            assert fetched.name == "Test Domain"
            assert fetched.status == "draft"
            assert fetched.project_id == project_id
            assert fetched.parent_id is None

    _run(_run_test())


def test_work_context_hierarchy(app_client):
    """Epic references Domain via parent_id; Story references Epic."""
    project_id = _project_id(app_client)

    async def _run_test():
        async with AsyncSessionLocal() as db:
            domain = WorkContext(project_id=project_id, level="domain", name="D", status="draft")
            db.add(domain)
            await db.flush()

            epic = WorkContext(
                project_id=project_id,
                level="epic",
                name="E",
                status="draft",
                parent_id=domain.id,
            )
            db.add(epic)
            await db.flush()

            story = WorkContext(
                project_id=project_id,
                level="story",
                name="S",
                status="draft",
                parent_id=epic.id,
            )
            db.add(story)
            await db.commit()

            story_id = story.id
            epic_id = epic.id

        async with AsyncSessionLocal() as db:
            s = await db.get(WorkContext, story_id)
            assert s is not None
            assert s.parent_id == epic_id

    _run(_run_test())


def test_work_context_delete_cascades_from_project(app_client):
    """Deleting a project cascades to its WorkContexts."""
    project_id = _project_id(app_client)

    async def _run_test():
        async with AsyncSessionLocal() as db:
            wc = WorkContext(project_id=project_id, level="domain", name="ToDelete", status="draft")
            db.add(wc)
            await db.commit()
            wc_id = wc.id

        # Delete project via API
        r = app_client.delete(f"/api/projects/{project_id}")
        assert r.status_code in (200, 204)

        async with AsyncSessionLocal() as db:
            fetched = await db.get(WorkContext, wc_id)
            assert fetched is None, "WorkContext should be cascade-deleted with project"

    _run(_run_test())


# ─── ArtifactAuditLog ────────────────────────────────────────────────────────

def test_artifact_audit_log_create(app_client):
    """ArtifactAuditLog rows can be appended."""
    project_id = _project_id(app_client)
    req_id = str(uuid.uuid4())

    async def _run_test():
        async with AsyncSessionLocal() as db:
            log_entry = ArtifactAuditLog(
                project_id=project_id,
                artifact_type="requirement",
                artifact_item_id=req_id,
                event_type="created",
                work_context_id=None,
                old_value=None,
                new_value={"title": "FR-001", "status": "draft"},
                actor="system",
                note="test entry",
            )
            db.add(log_entry)
            await db.commit()
            entry_id = log_entry.id

        async with AsyncSessionLocal() as db:
            fetched = await db.get(ArtifactAuditLog, entry_id)
            assert fetched is not None
            assert fetched.artifact_type == "requirement"
            assert fetched.event_type == "created"
            assert fetched.actor == "system"
            assert fetched.new_value == {"title": "FR-001", "status": "draft"}

    _run(_run_test())


def test_artifact_audit_log_multiple_events(app_client):
    """Multiple events for the same item are stored as separate rows."""
    project_id = _project_id(app_client)
    item_id = str(uuid.uuid4())

    async def _run_test():
        async with AsyncSessionLocal() as db:
            for event in ("created", "status_changed", "promoted"):
                db.add(ArtifactAuditLog(
                    project_id=project_id,
                    artifact_type="glossary_term",
                    artifact_item_id=item_id,
                    event_type=event,
                    actor="system",
                ))
            await db.commit()

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ArtifactAuditLog).where(
                    ArtifactAuditLog.project_id == project_id,
                    ArtifactAuditLog.artifact_item_id == item_id,
                )
            )
            rows = result.scalars().all()
            assert len(rows) == 3
            event_types = {r.event_type for r in rows}
            assert event_types == {"created", "status_changed", "promoted"}

    _run(_run_test())


# ─── PromotionConflict ────────────────────────────────────────────────────────

def test_promotion_conflict_create_and_resolve(app_client):
    """PromotionConflict can be created and its status updated."""
    project_id = _project_id(app_client)

    async def _run_test():
        async with AsyncSessionLocal() as db:
            conflict = PromotionConflict(
                project_id=project_id,
                artifact_type="glossary_term",
                artifact_item_id="payment",
                incoming_value={"term": "payment", "definition": "A transfer of funds."},
                existing_value={"term": "payment", "definition": "A financial transaction."},
                conflict_reason="Definition differs by >15% (SequenceMatcher ratio 0.72)",
                status="pending",
            )
            db.add(conflict)
            await db.commit()
            conflict_id = conflict.id

        async with AsyncSessionLocal() as db:
            fetched = await db.get(PromotionConflict, conflict_id)
            assert fetched is not None
            assert fetched.status == "pending"
            assert fetched.artifact_type == "glossary_term"

            # Resolve
            fetched.status = "resolved_accept_new"
            fetched.resolved_by = "user-1"
            fetched.resolved_at = datetime.now(timezone.utc)
            await db.commit()

        async with AsyncSessionLocal() as db:
            resolved = await db.get(PromotionConflict, conflict_id)
            assert resolved.status == "resolved_accept_new"
            assert resolved.resolved_by == "user-1"

    _run(_run_test())


# ─── ArtifactLifecycle ────────────────────────────────────────────────────────

def test_artifact_lifecycle_create(app_client):
    """ArtifactLifecycle manifest rows can be inserted."""
    project_id = _project_id(app_client)

    async def _run_test():
        async with AsyncSessionLocal() as db:
            manifest = ArtifactLifecycle(
                project_id=project_id,
                artifact_type="graph_node",
                artifact_item_id="payment_gateway",
                lifecycle_status="promoted",
            )
            db.add(manifest)
            await db.commit()
            manifest_id = manifest.id

        async with AsyncSessionLocal() as db:
            fetched = await db.get(ArtifactLifecycle, manifest_id)
            assert fetched is not None
            assert fetched.artifact_type == "graph_node"
            assert fetched.artifact_item_id == "payment_gateway"
            assert fetched.lifecycle_status == "promoted"

    _run(_run_test())


def test_artifact_lifecycle_unique_constraint(app_client):
    """Inserting duplicate (project_id, artifact_type, artifact_item_id) raises IntegrityError."""
    from sqlalchemy.exc import IntegrityError

    project_id = _project_id(app_client)

    async def _run_test():
        async with AsyncSessionLocal() as db:
            db.add(ArtifactLifecycle(
                project_id=project_id,
                artifact_type="glossary_term",
                artifact_item_id="transfer",
                lifecycle_status="promoted",
            ))
            await db.commit()

        with pytest.raises(IntegrityError):
            async with AsyncSessionLocal() as db:
                db.add(ArtifactLifecycle(
                    project_id=project_id,
                    artifact_type="glossary_term",
                    artifact_item_id="transfer",  # duplicate
                    lifecycle_status="draft",
                ))
                await db.commit()

    _run(_run_test())


# ─── Existing rows default to "promoted" ─────────────────────────────────────

def test_new_requirement_defaults_to_promoted(app_client):
    """Requirements created after migration have lifecycle_status='promoted' by default."""
    from unittest.mock import AsyncMock, MagicMock, patch
    import json

    project_id = _project_id(app_client)

    minimal_extraction = json.dumps({
        "features": [{
            "title": "Lifecycle Test", "module": "test", "description": "",
            "requirements": [{
                "external_id": "FR-LC-01", "title": "Lifecycle Default",
                "description": "Test default lifecycle status", "level": "functional_req",
                "source_type": "formal",
                "taxonomy": {}, "testability": "high", "confidence": 0.9,
                "needs_review": False, "review_reason": None, "acceptance_criteria": [],
            }],
        }],
        "gaps": [],
        "metadata": {
            "total_features": 1, "total_requirements": 1,
            "total_acceptance_criteria": 0, "formal_count": 1,
            "implicit_count": 0, "avg_confidence": 0.9, "low_confidence_count": 0,
        },
    })

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(return_value=minimal_extraction)

    with patch("app.api.routes.requirements.get_llm", return_value=mock_llm), \
         patch("app.agents.requirements_workflow.ContextBuilder.is_indexed",
               new_callable=AsyncMock, return_value=True), \
         patch("app.agents.requirements_workflow.ContextBuilder.retrieve_nodes",
               new_callable=AsyncMock, return_value=[]), \
         patch("app.agents.requirements_workflow.ContextBuilder.get_indexed_filenames",
               return_value=[]):
        r = app_client.post(f"/api/requirements/{project_id}/extract", json={"message": ""})

    assert r.status_code == 200

    async def _check():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Requirement).where(Requirement.project_id == project_id)
            )
            rows = result.scalars().all()
            assert len(rows) > 0, "Expected at least one requirement after extraction"
            for req in rows:
                assert req.lifecycle_status == "promoted", (
                    f"Requirement {req.id} has lifecycle_status={req.lifecycle_status!r}, expected 'promoted'"
                )
                assert req.work_context_id is None

    _run(_check())
