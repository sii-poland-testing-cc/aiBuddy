"""
ArtifactVisibility schema tests — visibility manifest (Decision D10).
=====================================================================
Verifies that:
  - artifact_visibility table exists and is queryable
  - Multiple rows for the same item in different contexts (visibility fan-out)
  - Unique constraint: cannot have duplicate (item × visible_in_context) pairs
  - source_origin is queryable: "find all items from source X"
  - requirements.source_origin and source_origin_type columns exist

These are schema-level tests only — no API, no business logic.
"""

import asyncio
import uuid
from datetime import datetime, timezone

import pytest

from app.db.engine import AsyncSessionLocal
from app.db.models import ArtifactVisibility, Project, WorkContext
from app.db.requirements_models import Requirement
from sqlalchemy import select, text


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _project_id(app_client) -> str:
    r = app_client.post("/api/projects/", json={"name": "visibility-test"})
    assert r.status_code in (200, 201)
    return r.json()["project_id"]


def _run(coro):
    return asyncio.run(coro)


# ─── Table existence ─────────────────────────────────────────────────────────

def test_artifact_visibility_table_exists(app_client):
    """artifact_visibility table should be queryable after app startup."""
    async def _check():
        async with AsyncSessionLocal() as db:
            result = await db.execute(text("SELECT 1 FROM artifact_visibility LIMIT 1"))
            result.fetchall()

    _run(_check())


def test_requirements_source_origin_columns_exist(app_client):
    """requirements table must have source_origin and source_origin_type columns."""
    async def _check():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text("SELECT source_origin, source_origin_type FROM requirements LIMIT 1")
            )
            result.fetchall()

    _run(_check())


# ─── Basic CRUD ──────────────────────────────────────────────────────────────

def test_artifact_visibility_create(app_client):
    """ArtifactVisibility rows can be inserted and queried."""
    pid = _project_id(app_client)

    async def _run_test():
        async with AsyncSessionLocal() as db:
            # Create a work context
            ctx = WorkContext(project_id=pid, level="story", name="Story-1", status="draft")
            db.add(ctx)
            await db.flush()

            vis = ArtifactVisibility(
                project_id=pid,
                artifact_type="graph_node",
                artifact_item_id="payment_gateway",
                source_context_id=ctx.id,
                visible_in_context_id=ctx.id,
                lifecycle_status="draft",
            )
            db.add(vis)
            await db.commit()
            vis_id = vis.id

        async with AsyncSessionLocal() as db:
            fetched = await db.get(ArtifactVisibility, vis_id)
            assert fetched is not None
            assert fetched.artifact_type == "graph_node"
            assert fetched.artifact_item_id == "payment_gateway"
            assert fetched.source_context_id == fetched.visible_in_context_id
            assert fetched.lifecycle_status == "draft"

    _run(_run_test())


# ─── Multi-context visibility (D10 fan-out) ──────────────────────────────────

def test_visibility_fan_out_multiple_contexts(app_client):
    """
    D10: Same item can be visible in multiple contexts.
    Creating in Story, promoting to Epic, then Domain = 3 visibility rows.
    """
    pid = _project_id(app_client)

    async def _run_test():
        async with AsyncSessionLocal() as db:
            domain = WorkContext(project_id=pid, level="domain", name="Domain", status="promoted")
            db.add(domain)
            await db.flush()
            epic = WorkContext(project_id=pid, level="epic", name="Epic-1", status="active", parent_id=domain.id)
            db.add(epic)
            await db.flush()
            story = WorkContext(project_id=pid, level="story", name="Story-1", status="draft", parent_id=epic.id)
            db.add(story)
            await db.flush()

            item_id = "payment_flow"

            # Created in story (home)
            db.add(ArtifactVisibility(
                project_id=pid,
                artifact_type="graph_node",
                artifact_item_id=item_id,
                source_context_id=story.id,
                visible_in_context_id=story.id,
                lifecycle_status="draft",
            ))
            # Promoted to epic
            db.add(ArtifactVisibility(
                project_id=pid,
                artifact_type="graph_node",
                artifact_item_id=item_id,
                source_context_id=story.id,
                visible_in_context_id=epic.id,
                lifecycle_status="promoted",
            ))
            # Promoted to domain
            db.add(ArtifactVisibility(
                project_id=pid,
                artifact_type="graph_node",
                artifact_item_id=item_id,
                source_context_id=story.id,
                visible_in_context_id=domain.id,
                lifecycle_status="promoted",
            ))
            await db.commit()

        # Query: all visibility rows for this item
        async with AsyncSessionLocal() as db:
            stmt = select(ArtifactVisibility).where(
                ArtifactVisibility.project_id == pid,
                ArtifactVisibility.artifact_type == "graph_node",
                ArtifactVisibility.artifact_item_id == item_id,
            )
            rows = (await db.execute(stmt)).scalars().all()
            assert len(rows) == 3

            visible_contexts = {r.visible_in_context_id for r in rows}
            assert len(visible_contexts) == 3  # story, epic, domain

            # All rows share the same source_context_id (story)
            source_contexts = {r.source_context_id for r in rows}
            assert len(source_contexts) == 1

    _run(_run_test())


def test_query_items_visible_in_context(app_client):
    """Primary query: 'what is visible in context X' uses visible_in_context_id."""
    pid = _project_id(app_client)

    async def _run_test():
        async with AsyncSessionLocal() as db:
            epic = WorkContext(project_id=pid, level="epic", name="Epic", status="active")
            db.add(epic)
            await db.flush()
            story = WorkContext(project_id=pid, level="story", name="Story", status="draft", parent_id=epic.id)
            db.add(story)
            await db.flush()

            # Item visible in both story and epic
            db.add(ArtifactVisibility(
                project_id=pid, artifact_type="glossary_term",
                artifact_item_id="payment",
                source_context_id=story.id, visible_in_context_id=story.id,
                lifecycle_status="draft",
            ))
            db.add(ArtifactVisibility(
                project_id=pid, artifact_type="glossary_term",
                artifact_item_id="payment",
                source_context_id=story.id, visible_in_context_id=epic.id,
                lifecycle_status="promoted",
            ))
            # Item only in story
            db.add(ArtifactVisibility(
                project_id=pid, artifact_type="glossary_term",
                artifact_item_id="refund",
                source_context_id=story.id, visible_in_context_id=story.id,
                lifecycle_status="draft",
            ))
            await db.commit()

        async with AsyncSessionLocal() as db:
            # Epic should see only "payment"
            stmt = select(ArtifactVisibility).where(
                ArtifactVisibility.project_id == pid,
                ArtifactVisibility.visible_in_context_id == epic.id,
            )
            epic_items = (await db.execute(stmt)).scalars().all()
            assert len(epic_items) == 1
            assert epic_items[0].artifact_item_id == "payment"

            # Story should see both
            stmt = select(ArtifactVisibility).where(
                ArtifactVisibility.project_id == pid,
                ArtifactVisibility.visible_in_context_id == story.id,
            )
            story_items = (await db.execute(stmt)).scalars().all()
            assert len(story_items) == 2

    _run(_run_test())


# ─── Unique constraint ───────────────────────────────────────────────────────

def test_unique_constraint_same_item_same_context(app_client):
    """Cannot insert duplicate (project, type, item_id, visible_in_context) pairs."""
    from sqlalchemy.exc import IntegrityError

    pid = _project_id(app_client)

    async def _run_test():
        async with AsyncSessionLocal() as db:
            ctx = WorkContext(project_id=pid, level="story", name="S1", status="draft")
            db.add(ctx)
            await db.flush()

            db.add(ArtifactVisibility(
                project_id=pid, artifact_type="graph_edge",
                artifact_item_id="a→b",
                source_context_id=ctx.id, visible_in_context_id=ctx.id,
                lifecycle_status="draft",
            ))
            await db.commit()

        with pytest.raises(IntegrityError):
            async with AsyncSessionLocal() as db:
                db.add(ArtifactVisibility(
                    project_id=pid, artifact_type="graph_edge",
                    artifact_item_id="a→b",
                    source_context_id=ctx.id, visible_in_context_id=ctx.id,
                    lifecycle_status="draft",
                ))
                await db.commit()

    _run(_run_test())


# ─── Source origin queryable ─────────────────────────────────────────────────

def test_source_origin_queryable(app_client):
    """Can find all items from a specific source file/URL."""
    pid = _project_id(app_client)

    async def _run_test():
        async with AsyncSessionLocal() as db:
            ctx = WorkContext(project_id=pid, level="domain", name="D", status="promoted")
            db.add(ctx)
            await db.flush()

            db.add(ArtifactVisibility(
                project_id=pid, artifact_type="graph_node",
                artifact_item_id="node_1",
                source_context_id=ctx.id, visible_in_context_id=ctx.id,
                source_origin="srs_v2.docx", source_origin_type="file",
                lifecycle_status="promoted",
            ))
            db.add(ArtifactVisibility(
                project_id=pid, artifact_type="glossary_term",
                artifact_item_id="term_1",
                source_context_id=ctx.id, visible_in_context_id=ctx.id,
                source_origin="srs_v2.docx", source_origin_type="file",
                lifecycle_status="promoted",
            ))
            db.add(ArtifactVisibility(
                project_id=pid, artifact_type="graph_node",
                artifact_item_id="node_2",
                source_context_id=ctx.id, visible_in_context_id=ctx.id,
                source_origin="https://jira.example.com/PROJ-1234",
                source_origin_type="url",
                lifecycle_status="promoted",
            ))
            await db.commit()

        async with AsyncSessionLocal() as db:
            # Find all items from srs_v2.docx
            stmt = select(ArtifactVisibility).where(
                ArtifactVisibility.project_id == pid,
                ArtifactVisibility.source_origin == "srs_v2.docx",
            )
            rows = (await db.execute(stmt)).scalars().all()
            assert len(rows) == 2
            item_ids = {r.artifact_item_id for r in rows}
            assert item_ids == {"node_1", "term_1"}

    _run(_run_test())


# ─── Sibling_of field ────────────────────────────────────────────────────────

def test_sibling_of_for_edit_merge(app_client):
    """sibling_of tracks items created by Edit & Merge conflict resolution."""
    pid = _project_id(app_client)

    async def _run_test():
        async with AsyncSessionLocal() as db:
            ctx = WorkContext(project_id=pid, level="epic", name="E1", status="active")
            db.add(ctx)
            await db.flush()

            original_item_id = "original_node"
            merged_item_id = "merged_node_v2"

            # Original item
            db.add(ArtifactVisibility(
                project_id=pid, artifact_type="graph_node",
                artifact_item_id=original_item_id,
                source_context_id=ctx.id, visible_in_context_id=ctx.id,
                lifecycle_status="draft",
            ))
            # Merged item (created from conflict resolution)
            db.add(ArtifactVisibility(
                project_id=pid, artifact_type="graph_node",
                artifact_item_id=merged_item_id,
                source_context_id=ctx.id, visible_in_context_id=ctx.id,
                lifecycle_status="draft",
                sibling_of=original_item_id,
            ))
            await db.commit()

        async with AsyncSessionLocal() as db:
            stmt = select(ArtifactVisibility).where(
                ArtifactVisibility.project_id == pid,
                ArtifactVisibility.sibling_of == original_item_id,
            )
            siblings = (await db.execute(stmt)).scalars().all()
            assert len(siblings) == 1
            assert siblings[0].artifact_item_id == merged_item_id

    _run(_run_test())


# ─── Requirement source_origin columns ───────────────────────────────────────

def test_requirement_source_origin_fields(app_client):
    """Requirement model supports source_origin and source_origin_type."""
    pid = _project_id(app_client)

    async def _run_test():
        async with AsyncSessionLocal() as db:
            req = Requirement(
                project_id=pid,
                title="FR-001 Payment Processing",
                level="functional_req",
                source_type="formal",
                source_origin="srs_payment_module.docx",
                source_origin_type="file",
            )
            db.add(req)
            await db.commit()
            req_id = req.id

        async with AsyncSessionLocal() as db:
            fetched = await db.get(Requirement, req_id)
            assert fetched is not None
            assert fetched.source_origin == "srs_payment_module.docx"
            assert fetched.source_origin_type == "file"

    _run(_run_test())


# ─── Cascade delete ──────────────────────────────────────────────────────────

def test_visibility_cascade_delete_on_project(app_client):
    """Deleting a project cascades to its ArtifactVisibility rows."""
    pid = _project_id(app_client)

    async def _run_test():
        async with AsyncSessionLocal() as db:
            db.add(ArtifactVisibility(
                project_id=pid, artifact_type="graph_node",
                artifact_item_id="node_to_delete",
                lifecycle_status="draft",
            ))
            await db.commit()

        # Delete project
        r = app_client.delete(f"/api/projects/{pid}")
        assert r.status_code in (200, 204)

        async with AsyncSessionLocal() as db:
            stmt = select(ArtifactVisibility).where(
                ArtifactVisibility.project_id == pid,
            )
            rows = (await db.execute(stmt)).scalars().all()
            assert len(rows) == 0

    _run(_run_test())
