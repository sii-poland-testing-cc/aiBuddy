"""
Phase 2 tests — WorkContext API (Domain / Epic / Story).
=========================================================
Tests the full HTTP layer: POST, GET, PATCH, DELETE on /api/work-contexts/.
Also verifies that Default Domain is auto-created on project creation.
"""

import pytest


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_project(app_client, name: str = "wc-test") -> str:
    r = app_client.post("/api/projects/", json={"name": name})
    assert r.status_code in (200, 201)
    return r.json()["project_id"]


def _list_contexts(app_client, project_id: str) -> list[dict]:
    """Return the flat list of all contexts, extracted from the tree."""
    r = app_client.get(f"/api/work-contexts/{project_id}")
    assert r.status_code == 200
    return r.json()["contexts"]


def _get_domain(app_client, project_id: str) -> dict:
    """Return the first (and normally only) domain from the hierarchy tree."""
    contexts = _list_contexts(app_client, project_id)
    domains = [c for c in contexts if c["level"] == "domain"]
    assert len(domains) >= 1, "Expected at least one Domain"
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


# ─── Default Domain auto-creation ────────────────────────────────────────────

def test_create_project_has_default_domain(app_client):
    """Creating a project should auto-create a 'Default Domain' work context."""
    project_id = _make_project(app_client, "auto-domain")
    contexts = _list_contexts(app_client, project_id)

    domains = [c for c in contexts if c["level"] == "domain"]
    assert len(domains) == 1
    assert domains[0]["name"] == "Default Domain"
    assert domains[0]["project_id"] == project_id
    assert domains[0]["parent_id"] is None


def test_default_domain_idempotent(app_client):
    """Calling project creation twice (or get_or_create_default_domain twice) yields one Domain."""
    project_id = _make_project(app_client, "idem-domain")
    # Simulate a second call to the domain service via the list endpoint
    contexts1 = _list_contexts(app_client, project_id)
    contexts2 = _list_contexts(app_client, project_id)
    domains1 = [c for c in contexts1 if c["level"] == "domain"]
    domains2 = [c for c in contexts2 if c["level"] == "domain"]
    assert len(domains1) == 1
    assert len(domains2) == 1
    assert domains1[0]["id"] == domains2[0]["id"]


# ─── Create Epic / Story ──────────────────────────────────────────────────────

def test_create_epic_under_domain(app_client):
    """POST epic with domain parent_id → 201, parent_id set correctly."""
    project_id = _make_project(app_client, "epic-under-domain")
    domain = _get_domain(app_client, project_id)

    epic = _create_epic(app_client, project_id, domain["id"], "Payment Epic")

    assert epic["level"] == "epic"
    assert epic["parent_id"] == domain["id"]
    assert epic["project_id"] == project_id
    assert epic["name"] == "Payment Epic"
    assert epic["status"] == "draft"


def test_create_story_under_epic(app_client):
    """POST story with epic parent_id → 201, parent_id set correctly."""
    project_id = _make_project(app_client, "story-under-epic")
    domain = _get_domain(app_client, project_id)
    epic = _create_epic(app_client, project_id, domain["id"])

    story = _create_story(app_client, project_id, epic["id"], "Login Story")

    assert story["level"] == "story"
    assert story["parent_id"] == epic["id"]
    assert story["name"] == "Login Story"
    assert story["status"] == "draft"


def test_cannot_create_domain_via_api(app_client):
    """Attempting to create a context with level='domain' → 422."""
    project_id = _make_project(app_client, "no-domain-create")
    domain = _get_domain(app_client, project_id)

    r = app_client.post(f"/api/work-contexts/{project_id}", json={
        "level": "domain",
        "name": "Second Domain",
        "parent_id": domain["id"],
    })
    assert r.status_code == 422


def test_invalid_story_under_domain(app_client):
    """Story with a Domain parent (not an Epic) → 422."""
    project_id = _make_project(app_client, "invalid-story-domain")
    domain = _get_domain(app_client, project_id)

    r = app_client.post(f"/api/work-contexts/{project_id}", json={
        "level": "story",
        "name": "Bad Story",
        "parent_id": domain["id"],  # must be epic, not domain
    })
    assert r.status_code == 422
    assert "epic" in r.json()["detail"].lower()


def test_invalid_epic_under_epic(app_client):
    """Epic with an Epic parent (not a Domain) → 422."""
    project_id = _make_project(app_client, "invalid-epic-epic")
    domain = _get_domain(app_client, project_id)
    epic = _create_epic(app_client, project_id, domain["id"])

    r = app_client.post(f"/api/work-contexts/{project_id}", json={
        "level": "epic",
        "name": "Nested Epic",
        "parent_id": epic["id"],  # must be domain, not epic
    })
    assert r.status_code == 422
    assert "domain" in r.json()["detail"].lower()


def test_invalid_parent_not_found(app_client):
    """parent_id that doesn't exist → 422."""
    project_id = _make_project(app_client, "invalid-parent")
    r = app_client.post(f"/api/work-contexts/{project_id}", json={
        "level": "epic",
        "name": "Orphan Epic",
        "parent_id": "non-existent-id",
    })
    assert r.status_code == 422


def test_invalid_parent_wrong_project(app_client):
    """parent_id belonging to a different project → 422."""
    pid_a = _make_project(app_client, "project-a")
    pid_b = _make_project(app_client, "project-b")
    domain_a = _get_domain(app_client, pid_a)

    r = app_client.post(f"/api/work-contexts/{pid_b}", json={
        "level": "epic",
        "name": "Cross-project Epic",
        "parent_id": domain_a["id"],  # belongs to project A, not B
    })
    assert r.status_code == 422


# ─── GET endpoints ────────────────────────────────────────────────────────────

def test_get_single_context(app_client):
    """GET /api/work-contexts/{project_id}/{ctx_id} returns the correct context."""
    project_id = _make_project(app_client, "get-single")
    domain = _get_domain(app_client, project_id)

    r = app_client.get(f"/api/work-contexts/{project_id}/{domain['id']}")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == domain["id"]
    assert data["level"] == "domain"


def test_get_context_wrong_project_404(app_client):
    """GET with context id belonging to a different project → 404."""
    pid_a = _make_project(app_client, "get-404-a")
    pid_b = _make_project(app_client, "get-404-b")
    domain_a = _get_domain(app_client, pid_a)

    r = app_client.get(f"/api/work-contexts/{pid_b}/{domain_a['id']}")
    assert r.status_code == 404


def test_list_hierarchy_has_children(app_client):
    """GET list returns tree with children nested under their parent."""
    project_id = _make_project(app_client, "tree-test")
    domain = _get_domain(app_client, project_id)
    epic = _create_epic(app_client, project_id, domain["id"], "Tree Epic")
    _create_story(app_client, project_id, epic["id"], "Tree Story")

    tree = _list_contexts(app_client, project_id)

    # Find our domain in the tree
    domain_node = next(c for c in tree if c["id"] == domain["id"])
    assert len(domain_node["children"]) >= 1
    epic_node = next(c for c in domain_node["children"] if c["id"] == epic["id"])
    assert len(epic_node["children"]) >= 1
    assert epic_node["children"][0]["level"] == "story"


def test_list_total_count(app_client):
    """GET list returns correct total count."""
    project_id = _make_project(app_client, "total-count")
    domain = _get_domain(app_client, project_id)
    _create_epic(app_client, project_id, domain["id"], "E1")
    _create_epic(app_client, project_id, domain["id"], "E2")

    r = app_client.get(f"/api/work-contexts/{project_id}")
    assert r.status_code == 200
    # 1 domain + 2 epics = 3
    assert r.json()["total"] == 3


# ─── Status transitions ───────────────────────────────────────────────────────

def test_status_draft_to_active(app_client):
    """draft → active via PATCH is valid."""
    project_id = _make_project(app_client, "status-draft-active")
    domain = _get_domain(app_client, project_id)
    epic = _create_epic(app_client, project_id, domain["id"])

    r = app_client.patch(f"/api/work-contexts/{project_id}/{epic['id']}", json={"status": "active"})
    assert r.status_code == 200
    assert r.json()["status"] == "active"


def test_status_active_to_ready(app_client):
    """active → ready via PATCH is valid."""
    project_id = _make_project(app_client, "status-active-ready")
    domain = _get_domain(app_client, project_id)
    epic = _create_epic(app_client, project_id, domain["id"])

    app_client.patch(f"/api/work-contexts/{project_id}/{epic['id']}", json={"status": "active"})
    r = app_client.patch(f"/api/work-contexts/{project_id}/{epic['id']}", json={"status": "ready"})
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


def test_status_invalid_ready_to_draft(app_client):
    """ready → draft is not a valid transition → 422."""
    project_id = _make_project(app_client, "status-invalid")
    domain = _get_domain(app_client, project_id)
    epic = _create_epic(app_client, project_id, domain["id"])

    app_client.patch(f"/api/work-contexts/{project_id}/{epic['id']}", json={"status": "active"})
    app_client.patch(f"/api/work-contexts/{project_id}/{epic['id']}", json={"status": "ready"})

    r = app_client.patch(f"/api/work-contexts/{project_id}/{epic['id']}", json={"status": "draft"})
    assert r.status_code == 422


def test_status_cannot_patch_to_promoted(app_client):
    """Setting status='promoted' via PATCH → 422 (must use Phase 5 promotion endpoint)."""
    project_id = _make_project(app_client, "status-no-promoted")
    domain = _get_domain(app_client, project_id)
    epic = _create_epic(app_client, project_id, domain["id"])

    r = app_client.patch(f"/api/work-contexts/{project_id}/{epic['id']}", json={"status": "promoted"})
    assert r.status_code == 422
    assert "promoted" in r.json()["detail"].lower()


def test_status_any_to_archived(app_client):
    """Any status → archived is always valid."""
    project_id = _make_project(app_client, "status-archived")
    domain = _get_domain(app_client, project_id)
    epic = _create_epic(app_client, project_id, domain["id"])

    # draft → archived (skipping active/ready)
    r = app_client.patch(f"/api/work-contexts/{project_id}/{epic['id']}", json={"status": "archived"})
    assert r.status_code == 200
    assert r.json()["status"] == "archived"


def test_status_archived_is_terminal(app_client):
    """Once archived, no further transitions are allowed → 422."""
    project_id = _make_project(app_client, "status-terminal")
    domain = _get_domain(app_client, project_id)
    epic = _create_epic(app_client, project_id, domain["id"])

    app_client.patch(f"/api/work-contexts/{project_id}/{epic['id']}", json={"status": "archived"})
    r = app_client.patch(f"/api/work-contexts/{project_id}/{epic['id']}", json={"status": "draft"})
    assert r.status_code == 422


# ─── PATCH: name / description ────────────────────────────────────────────────

def test_patch_name(app_client):
    """PATCH updates the name field."""
    project_id = _make_project(app_client, "patch-name")
    domain = _get_domain(app_client, project_id)
    epic = _create_epic(app_client, project_id, domain["id"], "Original Name")

    r = app_client.patch(f"/api/work-contexts/{project_id}/{epic['id']}", json={"name": "Updated Name"})
    assert r.status_code == 200
    assert r.json()["name"] == "Updated Name"


def test_patch_description(app_client):
    """PATCH updates the description field."""
    project_id = _make_project(app_client, "patch-desc")
    domain = _get_domain(app_client, project_id)
    epic = _create_epic(app_client, project_id, domain["id"])

    r = app_client.patch(
        f"/api/work-contexts/{project_id}/{epic['id']}",
        json={"description": "An important epic about payments"},
    )
    assert r.status_code == 200
    assert r.json()["description"] == "An important epic about payments"


# ─── DELETE (soft delete / archive) ──────────────────────────────────────────

def test_delete_story_archives_it(app_client):
    """DELETE on a Story sets its status to 'archived'."""
    project_id = _make_project(app_client, "delete-story")
    domain = _get_domain(app_client, project_id)
    epic = _create_epic(app_client, project_id, domain["id"])
    story = _create_story(app_client, project_id, epic["id"])

    r = app_client.delete(f"/api/work-contexts/{project_id}/{story['id']}")
    assert r.status_code == 200
    assert r.json()["status"] == "archived"


def test_delete_epic_archives_it(app_client):
    """DELETE on an Epic sets its status to 'archived'."""
    project_id = _make_project(app_client, "delete-epic")
    domain = _get_domain(app_client, project_id)
    epic = _create_epic(app_client, project_id, domain["id"])

    r = app_client.delete(f"/api/work-contexts/{project_id}/{epic['id']}")
    assert r.status_code == 200
    assert r.json()["status"] == "archived"


def test_delete_domain_archives_it(app_client):
    """DELETE on a Domain is allowed (soft-deletes / archives it)."""
    project_id = _make_project(app_client, "delete-domain")
    domain = _get_domain(app_client, project_id)

    r = app_client.delete(f"/api/work-contexts/{project_id}/{domain['id']}")
    assert r.status_code == 200
    assert r.json()["status"] == "archived"


def test_delete_idempotent(app_client):
    """DELETE on an already-archived context returns 200 (idempotent)."""
    project_id = _make_project(app_client, "delete-idem")
    domain = _get_domain(app_client, project_id)
    epic = _create_epic(app_client, project_id, domain["id"])

    app_client.delete(f"/api/work-contexts/{project_id}/{epic['id']}")
    r = app_client.delete(f"/api/work-contexts/{project_id}/{epic['id']}")
    assert r.status_code == 200
    assert r.json()["status"] == "archived"


def test_delete_nonexistent_404(app_client):
    """DELETE on a non-existent context id → 404."""
    project_id = _make_project(app_client, "delete-404")
    r = app_client.delete(f"/api/work-contexts/{project_id}/does-not-exist")
    assert r.status_code == 404


# ─── ABC / interface import ───────────────────────────────────────────────────

def test_lifecycle_abc_imports():
    """The lifecycle module and all stubs can be imported without error."""
    from app.lifecycle.interface import (
        ArtifactLifecycleAdapter,
        ArtifactType,
        ConflictItem,
        LifecycleStatus,
    )
    from app.lifecycle.audit_adapter import AuditSnapshotAdapter
    from app.lifecycle.glossary_adapter import GlossaryAdapter
    from app.lifecycle.graph_adapter import GraphEdgeAdapter, GraphNodeAdapter
    from app.lifecycle.requirements_adapter import RequirementsAdapter

    # All adapters are subclasses of the ABC
    assert issubclass(GraphNodeAdapter, ArtifactLifecycleAdapter)
    assert issubclass(GraphEdgeAdapter, ArtifactLifecycleAdapter)
    assert issubclass(GlossaryAdapter, ArtifactLifecycleAdapter)
    assert issubclass(RequirementsAdapter, ArtifactLifecycleAdapter)
    assert issubclass(AuditSnapshotAdapter, ArtifactLifecycleAdapter)

    # All artifact types present
    assert ArtifactType.GRAPH_NODE == "graph_node"
    assert ArtifactType.AUDIT_SNAPSHOT == "audit_snapshot"

    # All lifecycle statuses present
    assert LifecycleStatus.PROMOTED == "promoted"
    assert LifecycleStatus.CONFLICT_PENDING == "conflict_pending"

    # ConflictItem is a dataclass
    ci = ConflictItem(
        artifact_item_id="e1",
        incoming_value={"label": "new"},
        existing_value={"label": "old"},
        conflict_reason="label differs",
    )
    assert ci.artifact_item_id == "e1"


def test_adapter_phase4_implemented():
    """Phase 4 adapters (GraphNode, GraphEdge, Glossary) are implemented — detect_conflict works."""
    from app.lifecycle.graph_adapter import GraphEdgeAdapter, GraphNodeAdapter
    from app.lifecycle.glossary_adapter import GlossaryAdapter

    # All require db in constructor (pass None for unit test of pure logic)
    node_adapter = GraphNodeAdapter(db=None)  # type: ignore[arg-type]
    edge_adapter = GraphEdgeAdapter(db=None)  # type: ignore[arg-type]
    gloss_adapter = GlossaryAdapter(db=None)  # type: ignore[arg-type]

    # detect_conflict is a sync method — works without DB
    has_conflict, reason = node_adapter.detect_conflict(
        {"id": "e1", "label": "A", "type": "system"},
        {"id": "e1", "label": "B", "type": "system"},
    )
    assert has_conflict is True
    assert "label_mismatch" in reason

    has_conflict, _ = edge_adapter.detect_conflict(
        {"source": "e1", "target": "e2", "label": "tests"},
        {"source": "e1", "target": "e2", "label": "verifies"},
    )
    assert has_conflict is True

    has_conflict, _ = gloss_adapter.detect_conflict(
        {"term": "T", "definition": "A financial instrument for payment."},
        {"term": "t", "definition": "A test condition for QA processes."},
    )
    assert has_conflict is True
