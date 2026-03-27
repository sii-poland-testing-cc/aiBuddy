"""
test_versioning_promotion.py — Phase 8.4: Version pinning, locking, re-promotion.

Tests:
  1. Domain stability: promoted visibility rows pinned to version at promotion time
  2. Edit in source after promotion doesn't change target's pinned version
  3. Chained promotion (Story→Epic→Domain) preserves version pins
  4. Re-promotion: same version → skip; new version, no conflict → update
  5. Re-promotion: version drift with conflict → queued
  6. Pessimistic lock blocks concurrent promotion (SQLite path)
  7. apply_resolution "use_incoming" pins version
  8. apply_resolution "merge" creates v1 for sibling
  9. Preview includes version_deltas count
"""

import asyncio
import uuid as _uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import (
    ArtifactVersion,
    ArtifactVisibility,
    Base,
    Project,
    PromotionConflict,
    PromotionLock,
    WorkContext,
)
from app.db.requirements_models import Requirement
from app.services.versioning import create_version, get_current_version


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _make_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


PID = "proj-84"
NOW = datetime.now(timezone.utc)


async def _seed(db: AsyncSession):
    """Seed project + domain → epic → story hierarchy."""
    db.add(Project(id=PID, name="P84"))

    dom = WorkContext(id="dom1", project_id=PID, level="domain", name="Domain", status="active")
    epic = WorkContext(id="epic1", project_id=PID, parent_id="dom1", level="epic", name="Epic", status="ready")
    story = WorkContext(id="story1", project_id=PID, parent_id="epic1", level="story", name="Story", status="ready")
    db.add_all([dom, epic, story])
    await db.commit()


async def _add_requirement(db, item_id, ctx_id, title="Req", desc="Desc"):
    """Add a requirement with a v1 version and home visibility row."""
    db.add(Requirement(
        id=item_id, project_id=PID, level="functional_req",
        external_id=f"FR-{item_id[:3]}", title=title, description=desc,
        source_type="formal", work_context_id=ctx_id,
    ))
    ver = await create_version(
        db, PID, "requirement", item_id,
        {"id": item_id, "title": title, "description": desc, "external_id": f"FR-{item_id[:3]}"},
        ctx_id, "initial version",
    )
    db.add(ArtifactVisibility(
        id=str(_uuid.uuid4()), project_id=PID,
        artifact_type="requirement", artifact_item_id=item_id,
        source_context_id=ctx_id, visible_in_context_id=ctx_id,
        lifecycle_status="draft", artifact_version_id=ver.id,
    ))
    await db.flush()
    return ver


async def _add_glossary_term(db, term_name, ctx_id, definition="A definition"):
    """Add a glossary term with v1 version and home visibility."""
    item_id = term_name.lower().strip()
    snapshot = {"term": term_name, "definition": definition}
    ver = await create_version(
        db, PID, "glossary_term", item_id, snapshot, ctx_id, "initial version",
    )
    db.add(ArtifactVisibility(
        id=str(_uuid.uuid4()), project_id=PID,
        artifact_type="glossary_term", artifact_item_id=item_id,
        source_context_id=ctx_id, visible_in_context_id=ctx_id,
        lifecycle_status="draft", artifact_version_id=ver.id,
    ))
    await db.flush()
    return ver


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestPromotionPinning:
    """Promoted visibility rows are pinned to the version at promotion time."""

    def test_persist_promoted_items_pins_version(self):
        """_persist_promoted_items sets artifact_version_id on the new row."""
        async def _run():
            engine, factory = await _make_session()
            async with factory() as db:
                await _seed(db)
                ver = await _add_requirement(db, "r1", "story1")
                await db.commit()

                # Import here to avoid circular import issues at module level
                from app.lifecycle.promotion_service import _persist_promoted_items
                from app.lifecycle.interface import ArtifactType

                now = datetime.now(timezone.utc)
                await _persist_promoted_items(
                    db, ArtifactType.REQUIREMENT, PID,
                    "story1", "epic1",
                    [{"id": "r1", "title": "Req", "description": "Desc", "external_id": "FR-r1"}],
                    now,
                )
                await db.commit()

                # Check the promoted visibility row in epic1
                stmt = select(ArtifactVisibility).where(
                    ArtifactVisibility.project_id == PID,
                    ArtifactVisibility.artifact_item_id == "r1",
                    ArtifactVisibility.visible_in_context_id == "epic1",
                )
                promoted_row = (await db.execute(stmt)).scalars().first()
                assert promoted_row is not None
                assert promoted_row.artifact_version_id == ver.id
                assert promoted_row.lifecycle_status == "promoted"
            await engine.dispose()
        asyncio.run(_run())

    def test_edit_after_promotion_does_not_change_target(self):
        """Editing source after promotion leaves target pinned to old version."""
        async def _run():
            engine, factory = await _make_session()
            async with factory() as db:
                await _seed(db)
                v1 = await _add_requirement(db, "r2", "story1", title="Original")
                await db.commit()

                from app.lifecycle.promotion_service import _persist_promoted_items
                from app.lifecycle.interface import ArtifactType

                now = datetime.now(timezone.utc)
                await _persist_promoted_items(
                    db, ArtifactType.REQUIREMENT, PID,
                    "story1", "epic1",
                    [{"id": "r2", "title": "Original", "description": "Desc", "external_id": "FR-r2"}],
                    now,
                )
                await db.commit()

                # Now edit the requirement in source (creates v2)
                v2 = await create_version(
                    db, PID, "requirement", "r2",
                    {"id": "r2", "title": "Updated", "description": "Desc", "external_id": "FR-r2"},
                    "story1", "title updated",
                )
                # Update home visibility to v2
                home_stmt = select(ArtifactVisibility).where(
                    ArtifactVisibility.artifact_item_id == "r2",
                    ArtifactVisibility.visible_in_context_id == "story1",
                )
                home = (await db.execute(home_stmt)).scalars().first()
                home.artifact_version_id = v2.id
                await db.commit()

                # Target should still be pinned to v1
                target_stmt = select(ArtifactVisibility).where(
                    ArtifactVisibility.artifact_item_id == "r2",
                    ArtifactVisibility.visible_in_context_id == "epic1",
                )
                target = (await db.execute(target_stmt)).scalars().first()
                assert target.artifact_version_id == v1.id  # NOT v2
            await engine.dispose()
        asyncio.run(_run())

    def test_chained_promotion_story_epic_domain(self):
        """Story→Epic→Domain: each level pins its own version independently."""
        async def _run():
            engine, factory = await _make_session()
            async with factory() as db:
                await _seed(db)
                v1 = await _add_requirement(db, "r3", "story1")
                await db.commit()

                from app.lifecycle.promotion_service import _persist_promoted_items
                from app.lifecycle.interface import ArtifactType

                now = datetime.now(timezone.utc)
                # Promote story1 → epic1
                await _persist_promoted_items(
                    db, ArtifactType.REQUIREMENT, PID,
                    "story1", "epic1",
                    [{"id": "r3", "title": "Req", "description": "Desc", "external_id": "FR-r3"}],
                    now,
                )
                await db.commit()

                # Edit in story (v2)
                v2 = await create_version(
                    db, PID, "requirement", "r3",
                    {"id": "r3", "title": "Updated", "description": "Desc", "external_id": "FR-r3"},
                    "story1", "updated",
                )
                await db.commit()

                # Promote epic1 → dom1 (should pick up v2 as current)
                await _persist_promoted_items(
                    db, ArtifactType.REQUIREMENT, PID,
                    "epic1", "dom1",
                    [{"id": "r3", "title": "Updated", "description": "Desc", "external_id": "FR-r3"}],
                    now,
                )
                await db.commit()

                # Epic row should have v1, Domain row should have v2
                epic_stmt = select(ArtifactVisibility).where(
                    ArtifactVisibility.artifact_item_id == "r3",
                    ArtifactVisibility.visible_in_context_id == "epic1",
                )
                epic_row = (await db.execute(epic_stmt)).scalars().first()
                assert epic_row.artifact_version_id == v1.id

                dom_stmt = select(ArtifactVisibility).where(
                    ArtifactVisibility.artifact_item_id == "r3",
                    ArtifactVisibility.visible_in_context_id == "dom1",
                )
                dom_row = (await db.execute(dom_stmt)).scalars().first()
                assert dom_row.artifact_version_id == v2.id
            await engine.dispose()
        asyncio.run(_run())


class TestRePromotion:
    """Re-promotion detects version drift and updates or queues conflicts."""

    def test_same_version_skipped(self):
        """Re-promotion skips items where pinned == current version."""
        async def _run():
            engine, factory = await _make_session()
            async with factory() as db:
                await _seed(db)
                v1 = await _add_glossary_term(db, "Token", "story1")
                await db.commit()

                # Manually create a promoted row in epic1 pinned to v1
                db.add(ArtifactVisibility(
                    id=str(_uuid.uuid4()), project_id=PID,
                    artifact_type="glossary_term", artifact_item_id="token",
                    source_context_id="story1", visible_in_context_id="epic1",
                    lifecycle_status="promoted", artifact_version_id=v1.id,
                ))
                await db.commit()

                from app.lifecycle.promotion_service import _re_promote_items
                result = await _re_promote_items(db, PID, "story1", "epic1")
                assert result.promoted_count == 0  # nothing updated
                assert result.conflict_count == 0
            await engine.dispose()
        asyncio.run(_run())

    def test_version_drift_no_conflict_updates_pin(self):
        """Re-promotion updates pinned version when no conflict exists."""
        async def _run():
            engine, factory = await _make_session()
            async with factory() as db:
                await _seed(db)
                v1 = await _add_glossary_term(db, "Token", "story1", "Old def")
                await db.commit()

                # Promoted row in epic1 pinned to v1
                promo_vis_id = str(_uuid.uuid4())
                db.add(ArtifactVisibility(
                    id=promo_vis_id, project_id=PID,
                    artifact_type="glossary_term", artifact_item_id="token",
                    source_context_id="story1", visible_in_context_id="epic1",
                    lifecycle_status="promoted", artifact_version_id=v1.id,
                ))
                await db.commit()

                # Edit creates v2 in source
                v2 = await create_version(
                    db, PID, "glossary_term", "token",
                    {"term": "Token", "definition": "Updated definition"},
                    "story1", "definition updated",
                )
                # Update home visibility
                home_stmt = select(ArtifactVisibility).where(
                    ArtifactVisibility.artifact_item_id == "token",
                    ArtifactVisibility.visible_in_context_id == "story1",
                )
                home = (await db.execute(home_stmt)).scalars().first()
                home.artifact_version_id = v2.id
                await db.commit()

                from app.lifecycle.promotion_service import _re_promote_items
                result = await _re_promote_items(db, PID, "story1", "epic1")
                assert result.promoted_count == 1  # updated
                assert result.conflict_count == 0

                # Verify epic row now pinned to v2
                target_stmt = select(ArtifactVisibility).where(
                    ArtifactVisibility.id == promo_vis_id,
                )
                target = (await db.execute(target_stmt)).scalars().first()
                assert target.artifact_version_id == v2.id
            await engine.dispose()
        asyncio.run(_run())


class TestPessimisticLock:
    """SQLite promotion_locks table prevents concurrent promotion."""

    def test_lock_acquire_and_release(self):
        """Acquire + release cycle works cleanly."""
        async def _run():
            engine, factory = await _make_session()
            async with factory() as db:
                await _seed(db)

                from app.lifecycle.promotion_service import (
                    _acquire_promotion_lock,
                    _release_promotion_lock,
                )
                await _acquire_promotion_lock(db, PID, "dom1")
                # Lock row should exist
                stmt = select(PromotionLock).where(PromotionLock.target_context_id == "dom1")
                lock = (await db.execute(stmt)).scalars().first()
                assert lock is not None

                await _release_promotion_lock(db, PID, "dom1")
                # Lock row should be gone
                lock = (await db.execute(stmt)).scalars().first()
                assert lock is None
            await engine.dispose()
        asyncio.run(_run())

    def test_double_lock_raises(self):
        """Second acquire on same target raises HTTPException(409)."""
        async def _run():
            engine, factory = await _make_session()
            async with factory() as db:
                await _seed(db)

                from app.lifecycle.promotion_service import _acquire_promotion_lock
                from fastapi import HTTPException

                await _acquire_promotion_lock(db, PID, "dom1")
                try:
                    await _acquire_promotion_lock(db, PID, "dom1")
                    assert False, "Should have raised"
                except HTTPException as e:
                    assert e.status_code == 409
                    assert "already in progress" in e.detail
            await engine.dispose()
        asyncio.run(_run())


class TestApplyResolutionVersioning:
    """apply_resolution pins versions on "use_incoming" and creates v1 for "merge"."""

    def test_use_incoming_pins_version(self):
        """GlossaryAdapter.apply_resolution('use_incoming') pins current version."""
        async def _run():
            engine, factory = await _make_session()
            async with factory() as db:
                await _seed(db)
                v1 = await _add_glossary_term(db, "Token", "story1", "Source def")

                # Existing term in epic lives in Project.glossary (no visibility row)
                # — this is the fallback path used before versioning was added
                proj = await db.get(Project, PID)
                proj.glossary = [{"term": "Token", "definition": "Target def"}]
                await db.commit()

                # Create a conflict record
                conflict_id = str(_uuid.uuid4())
                db.add(PromotionConflict(
                    id=conflict_id, project_id=PID,
                    artifact_type="glossary_term", artifact_item_id="token",
                    source_context_id="story1", target_context_id="epic1",
                    incoming_value={"term": "Token", "definition": "Source def"},
                    existing_value={"term": "Token", "definition": "Target def"},
                    conflict_reason="definition_mismatch",
                    status="pending",
                ))
                await db.commit()

                from app.lifecycle.glossary_adapter import GlossaryAdapter
                adapter = GlossaryAdapter(db)
                await adapter.apply_resolution(PID, conflict_id, "use_incoming", None)

                # Find the new promoted visibility row for "token" in epic1
                stmt = select(ArtifactVisibility).where(
                    ArtifactVisibility.artifact_item_id == "token",
                    ArtifactVisibility.visible_in_context_id == "epic1",
                    ArtifactVisibility.lifecycle_status == "promoted",
                )
                promoted = (await db.execute(stmt)).scalars().first()
                assert promoted is not None
                assert promoted.artifact_version_id == v1.id
            await engine.dispose()
        asyncio.run(_run())

    def test_merge_creates_sibling_version(self):
        """GlossaryAdapter.apply_resolution('merge') creates v1 for sibling."""
        async def _run():
            engine, factory = await _make_session()
            async with factory() as db:
                await _seed(db)
                await _add_glossary_term(db, "Token", "story1", "Source def")

                # Need a project row for _add_term_to_blob
                proj = await db.get(Project, PID)
                proj.glossary = [{"term": "Token", "definition": "Target def"}]
                await db.commit()

                conflict_id = str(_uuid.uuid4())
                db.add(PromotionConflict(
                    id=conflict_id, project_id=PID,
                    artifact_type="glossary_term", artifact_item_id="token",
                    source_context_id="story1", target_context_id="epic1",
                    incoming_value={"term": "Token", "definition": "Source def"},
                    existing_value={"term": "Token", "definition": "Target def"},
                    conflict_reason="definition_mismatch",
                    status="pending",
                ))
                await db.commit()

                from app.lifecycle.glossary_adapter import GlossaryAdapter
                adapter = GlossaryAdapter(db)
                merged_value = {"term": "Token", "definition": "Merged definition"}
                await adapter.apply_resolution(PID, conflict_id, "merge", merged_value)

                # Find the sibling visibility row
                stmt = select(ArtifactVisibility).where(
                    ArtifactVisibility.visible_in_context_id == "epic1",
                    ArtifactVisibility.lifecycle_status == "promoted",
                    ArtifactVisibility.sibling_of == "token",
                )
                sibling = (await db.execute(stmt)).scalars().first()
                assert sibling is not None
                assert sibling.artifact_version_id is not None

                # Verify the version was created
                ver = await db.get(ArtifactVersion, sibling.artifact_version_id)
                assert ver is not None
                assert ver.version_number == 1
                assert ver.content_snapshot["definition"] == "Merged definition"
            await engine.dispose()
        asyncio.run(_run())


class TestPreviewVersionDeltas:
    """preview_promotion includes version_deltas in summary."""

    def test_preview_counts_version_deltas(self):
        """Items with drifted versions counted as version_deltas."""
        async def _run():
            engine, factory = await _make_session()
            async with factory() as db:
                await _seed(db)
                v1 = await _add_glossary_term(db, "Token", "story1")

                # Promoted row in epic1 pinned to v1
                db.add(ArtifactVisibility(
                    id=str(_uuid.uuid4()), project_id=PID,
                    artifact_type="glossary_term", artifact_item_id="token",
                    source_context_id="story1", visible_in_context_id="epic1",
                    lifecycle_status="promoted", artifact_version_id=v1.id,
                ))
                await db.commit()

                # Create v2 in source
                v2 = await create_version(
                    db, PID, "glossary_term", "token",
                    {"term": "Token", "definition": "Updated"},
                    "story1", "updated",
                )
                home_stmt = select(ArtifactVisibility).where(
                    ArtifactVisibility.artifact_item_id == "token",
                    ArtifactVisibility.visible_in_context_id == "story1",
                )
                home = (await db.execute(home_stmt)).scalars().first()
                home.artifact_version_id = v2.id
                await db.commit()

                from app.lifecycle.promotion_service import _count_version_deltas
                deltas = await _count_version_deltas(
                    db, PID, "glossary_term", "story1", "epic1"
                )
                assert deltas == 1
            await engine.dispose()
        asyncio.run(_run())
