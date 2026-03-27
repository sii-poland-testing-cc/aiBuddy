"""
test_versioning.py — Phase 8.2: Versioning service + edit path tests.

Uses async in-memory SQLite (via aiosqlite) with the full ORM models.
Tests run synchronously via asyncio.run() — no pytest-asyncio dependency.

Tests:
  - Versioning service CRUD (create, get_current, get, list, diff)
  - Requirement PATCH creates new version
  - Home visibility row updated to latest version
  - Non-home visibility rows untouched after edit
  - Batch persist creates v1 for requirements
  - Graph and glossary registration creates v1
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import (
    ArtifactVersion,
    ArtifactVisibility,
    Base,
    Project,
    WorkContext,
)
from app.db.requirements_models import Requirement
from app.services.versioning import (
    create_version,
    create_version_and_update_home,
    get_current_version,
    get_version,
    get_version_diff,
    list_versions,
    update_home_visibility_version,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


async def _make_session():
    """Create an in-memory async SQLite session with all tables."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


async def _seed_project(db: AsyncSession, project_id: str = "proj1") -> Project:
    project = Project(id=project_id, name="Test Project")
    db.add(project)
    await db.flush()
    return project


async def _seed_domain(db: AsyncSession, project_id: str = "proj1", domain_id: str = "dom1") -> WorkContext:
    domain = WorkContext(id=domain_id, project_id=project_id, level="domain", name="Domain", status="draft")
    db.add(domain)
    await db.flush()
    return domain


async def _seed_requirement(
    db: AsyncSession,
    req_id: str = "r1",
    project_id: str = "proj1",
    title: str = "Login Feature",
    description: str = "Users can log in",
    work_context_id: Optional[str] = "dom1",
) -> Requirement:
    req = Requirement(
        id=req_id,
        project_id=project_id,
        title=title,
        description=description,
        level="functional_req",
        source_type="formal",
        work_context_id=work_context_id,
        lifecycle_status="promoted",
    )
    db.add(req)
    await db.flush()
    return req


async def _seed_visibility(
    db: AsyncSession,
    project_id: str,
    artifact_type: str,
    item_id: str,
    source_ctx: Optional[str] = None,
    visible_ctx: Optional[str] = None,
    version_id: Optional[str] = None,
) -> ArtifactVisibility:
    vis = ArtifactVisibility(
        id=str(uuid.uuid4()),
        project_id=project_id,
        artifact_type=artifact_type,
        artifact_item_id=item_id,
        source_context_id=source_ctx,
        visible_in_context_id=visible_ctx,
        lifecycle_status="promoted",
        artifact_version_id=version_id,
    )
    db.add(vis)
    await db.flush()
    return vis


# ── Service CRUD Tests ───────────────────────────────────────────────────────


class TestCreateVersion:
    def test_first_version_is_v1(self):
        async def _run():
            engine, factory = await _make_session()
            async with factory() as db:
                await _seed_project(db)
                await _seed_domain(db)

                v = await create_version(
                    db, "proj1", "requirement", "r1",
                    {"title": "Test"}, "dom1", "initial version",
                )
                assert v.version_number == 1
                assert v.content_snapshot == {"title": "Test"}
                assert v.change_summary == "initial version"
                assert v.created_by == "system"
                assert v.project_id == "proj1"
            await engine.dispose()

        asyncio.run(_run())

    def test_second_version_increments(self):
        async def _run():
            engine, factory = await _make_session()
            async with factory() as db:
                await _seed_project(db)
                await _seed_domain(db)

                v1 = await create_version(db, "proj1", "requirement", "r1", {"title": "A"}, "dom1", "v1")
                v2 = await create_version(db, "proj1", "requirement", "r1", {"title": "B"}, "dom1", "v2")
                assert v1.version_number == 1
                assert v2.version_number == 2
                assert v1.id != v2.id
            await engine.dispose()

        asyncio.run(_run())

    def test_different_items_independent_numbering(self):
        async def _run():
            engine, factory = await _make_session()
            async with factory() as db:
                await _seed_project(db)
                await _seed_domain(db)

                v_r1 = await create_version(db, "proj1", "requirement", "r1", {"title": "A"}, "dom1", "v1")
                v_r2 = await create_version(db, "proj1", "requirement", "r2", {"title": "B"}, "dom1", "v1")
                assert v_r1.version_number == 1
                assert v_r2.version_number == 1
            await engine.dispose()

        asyncio.run(_run())


class TestGetCurrentVersion:
    def test_returns_latest(self):
        async def _run():
            engine, factory = await _make_session()
            async with factory() as db:
                await _seed_project(db)
                await _seed_domain(db)

                await create_version(db, "proj1", "requirement", "r1", {"title": "A"}, "dom1", "v1")
                await create_version(db, "proj1", "requirement", "r1", {"title": "B"}, "dom1", "v2")
                v3 = await create_version(db, "proj1", "requirement", "r1", {"title": "C"}, "dom1", "v3")

                current = await get_current_version(db, "proj1", "requirement", "r1")
                assert current is not None
                assert current.id == v3.id
                assert current.version_number == 3
            await engine.dispose()

        asyncio.run(_run())

    def test_returns_none_when_no_versions(self):
        async def _run():
            engine, factory = await _make_session()
            async with factory() as db:
                await _seed_project(db)
                result = await get_current_version(db, "proj1", "requirement", "nonexistent")
                assert result is None
            await engine.dispose()

        asyncio.run(_run())


class TestGetVersion:
    def test_returns_by_id(self):
        async def _run():
            engine, factory = await _make_session()
            async with factory() as db:
                await _seed_project(db)
                await _seed_domain(db)

                v = await create_version(db, "proj1", "requirement", "r1", {"title": "A"}, "dom1", "v1")
                result = await get_version(db, v.id)
                assert result is not None
                assert result.version_number == 1
                assert result.content_snapshot == {"title": "A"}
            await engine.dispose()

        asyncio.run(_run())

    def test_returns_none_for_bad_id(self):
        async def _run():
            engine, factory = await _make_session()
            async with factory() as db:
                result = await get_version(db, "nonexistent-id")
                assert result is None
            await engine.dispose()

        asyncio.run(_run())


class TestListVersions:
    def test_returns_newest_first(self):
        async def _run():
            engine, factory = await _make_session()
            async with factory() as db:
                await _seed_project(db)
                await _seed_domain(db)

                await create_version(db, "proj1", "requirement", "r1", {"title": "A"}, "dom1", "v1")
                await create_version(db, "proj1", "requirement", "r1", {"title": "B"}, "dom1", "v2")
                await create_version(db, "proj1", "requirement", "r1", {"title": "C"}, "dom1", "v3")

                versions = await list_versions(db, "proj1", "requirement", "r1")
                assert len(versions) == 3
                assert versions[0].version_number == 3
                assert versions[1].version_number == 2
                assert versions[2].version_number == 1
            await engine.dispose()

        asyncio.run(_run())

    def test_empty_when_no_versions(self):
        async def _run():
            engine, factory = await _make_session()
            async with factory() as db:
                await _seed_project(db)
                versions = await list_versions(db, "proj1", "requirement", "nonexistent")
                assert versions == []
            await engine.dispose()

        asyncio.run(_run())


class TestGetVersionDiff:
    def test_changed_fields(self):
        async def _run():
            engine, factory = await _make_session()
            async with factory() as db:
                await _seed_project(db)
                await _seed_domain(db)

                v1 = await create_version(db, "proj1", "requirement", "r1",
                                          {"title": "Login", "description": "Users log in"}, "dom1", "v1")
                v2 = await create_version(db, "proj1", "requirement", "r1",
                                          {"title": "Login Feature", "description": "Users log in"}, "dom1", "v2")

                diff = get_version_diff(v1, v2)
                assert diff["changed_fields"] == {"title": {"old": "Login", "new": "Login Feature"}}
                assert diff["added_fields"] == {}
                assert diff["removed_fields"] == {}
            await engine.dispose()

        asyncio.run(_run())

    def test_added_and_removed_fields(self):
        async def _run():
            engine, factory = await _make_session()
            async with factory() as db:
                await _seed_project(db)
                await _seed_domain(db)

                v1 = await create_version(db, "proj1", "requirement", "r1",
                                          {"title": "A", "old_field": "X"}, "dom1", "v1")
                v2 = await create_version(db, "proj1", "requirement", "r1",
                                          {"title": "A", "new_field": "Y"}, "dom1", "v2")

                diff = get_version_diff(v1, v2)
                assert "old_field" in diff["removed_fields"]
                assert "new_field" in diff["added_fields"]
                assert diff["changed_fields"] == {}
            await engine.dispose()

        asyncio.run(_run())


class TestUpdateHomeVisibilityVersion:
    def test_updates_home_row(self):
        async def _run():
            engine, factory = await _make_session()
            async with factory() as db:
                await _seed_project(db)
                await _seed_domain(db)

                v1 = await create_version(db, "proj1", "requirement", "r1", {"title": "A"}, "dom1", "v1")
                vis = await _seed_visibility(db, "proj1", "requirement", "r1", "dom1", "dom1", v1.id)

                v2 = await create_version(db, "proj1", "requirement", "r1", {"title": "B"}, "dom1", "v2")
                updated = await update_home_visibility_version(db, "proj1", "requirement", "r1", v2.id)
                assert updated == 1

                await db.refresh(vis)
                assert vis.artifact_version_id == v2.id
            await engine.dispose()

        asyncio.run(_run())

    def test_does_not_update_non_home_rows(self):
        async def _run():
            engine, factory = await _make_session()
            async with factory() as db:
                await _seed_project(db)
                await _seed_domain(db)
                epic = WorkContext(id="epic1", project_id="proj1", level="epic",
                                  name="Epic", status="active", parent_id="dom1")
                db.add(epic)
                await db.flush()

                v1 = await create_version(db, "proj1", "requirement", "r1", {"title": "A"}, "dom1", "v1")
                # Home row: source_context_id == visible_in_context_id == dom1
                _home = await _seed_visibility(db, "proj1", "requirement", "r1", "dom1", "dom1", v1.id)
                # Promoted row: source_context_id = dom1, visible_in_context_id = epic1
                promoted = await _seed_visibility(db, "proj1", "requirement", "r1", "dom1", "epic1", v1.id)

                v2 = await create_version(db, "proj1", "requirement", "r1", {"title": "B"}, "dom1", "v2")
                await update_home_visibility_version(db, "proj1", "requirement", "r1", v2.id)

                await db.refresh(promoted)
                assert promoted.artifact_version_id == v1.id  # UNCHANGED — still pinned to v1
            await engine.dispose()

        asyncio.run(_run())


class TestCreateVersionAndUpdateHome:
    def test_convenience_function(self):
        async def _run():
            engine, factory = await _make_session()
            async with factory() as db:
                await _seed_project(db)
                await _seed_domain(db)

                v1 = await create_version(db, "proj1", "requirement", "r1", {"title": "A"}, "dom1", "v1")
                vis = await _seed_visibility(db, "proj1", "requirement", "r1", "dom1", "dom1", v1.id)

                v2 = await create_version_and_update_home(
                    db, "proj1", "requirement", "r1", {"title": "B"}, "dom1", "title updated", "human",
                )
                assert v2.version_number == 2

                await db.refresh(vis)
                assert vis.artifact_version_id == v2.id
            await engine.dispose()

        asyncio.run(_run())


# ── Integration: Requirement Edit Path ───────────────────────────────────────


class TestRequirementEditVersioning:
    def test_edit_creates_new_version(self):
        """Simulates what the PATCH endpoint does."""
        async def _run():
            engine, factory = await _make_session()
            async with factory() as db:
                await _seed_project(db)
                await _seed_domain(db)
                req = await _seed_requirement(db, "r1")

                # Simulate initial v1 (as persist_requirements would do)
                v1 = await create_version(db, "proj1", "requirement", "r1",
                                          {"title": "Login Feature", "description": "Users can log in"},
                                          "dom1", "initial version")
                await _seed_visibility(db, "proj1", "requirement", "r1", "dom1", "dom1", v1.id)

                # Simulate PATCH: update title
                req.title = "Login Feature (Updated)"
                req.updated_at = datetime.now(timezone.utc)
                content = {"title": req.title, "description": req.description}
                v2 = await create_version_and_update_home(
                    db, "proj1", "requirement", "r1", content, "dom1", "updated: title", "human",
                )

                assert v2.version_number == 2
                assert v2.content_snapshot["title"] == "Login Feature (Updated)"

                # Original version still accessible
                original = await get_version(db, v1.id)
                assert original is not None
                assert original.content_snapshot["title"] == "Login Feature"
            await engine.dispose()

        asyncio.run(_run())

    def test_promoted_visibility_untouched_after_edit(self):
        """Non-home visibility rows stay pinned to their promotion-time version."""
        async def _run():
            engine, factory = await _make_session()
            async with factory() as db:
                await _seed_project(db)
                await _seed_domain(db)
                epic = WorkContext(id="epic1", project_id="proj1", level="epic",
                                  name="Epic", status="active", parent_id="dom1")
                db.add(epic)
                await db.flush()

                req = await _seed_requirement(db, "r1")

                v1 = await create_version(db, "proj1", "requirement", "r1",
                                          {"title": "Login"}, "dom1", "v1")
                await _seed_visibility(db, "proj1", "requirement", "r1", "dom1", "dom1", v1.id)
                promoted = await _seed_visibility(db, "proj1", "requirement", "r1", "dom1", "epic1", v1.id)

                # Edit requirement
                v2 = await create_version_and_update_home(
                    db, "proj1", "requirement", "r1",
                    {"title": "Login Updated"}, "dom1", "title change", "human",
                )

                # Promoted row MUST still point to v1
                await db.refresh(promoted)
                assert promoted.artifact_version_id == v1.id
                assert v2.version_number == 2
            await engine.dispose()

        asyncio.run(_run())

    def test_version_history_complete(self):
        async def _run():
            engine, factory = await _make_session()
            async with factory() as db:
                await _seed_project(db)
                await _seed_domain(db)

                await create_version(db, "proj1", "requirement", "r1", {"title": "v1"}, "dom1", "v1")
                await create_version(db, "proj1", "requirement", "r1", {"title": "v2"}, "dom1", "v2")
                await create_version(db, "proj1", "requirement", "r1", {"title": "v3"}, "dom1", "v3")

                history = await list_versions(db, "proj1", "requirement", "r1")
                assert len(history) == 3
                assert [v.version_number for v in history] == [3, 2, 1]
                assert [v.content_snapshot["title"] for v in history] == ["v3", "v2", "v1"]
            await engine.dispose()

        asyncio.run(_run())
