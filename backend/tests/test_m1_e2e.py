"""
M1 → M2 end-to-end test (extended)
====================================
Uses FastAPI TestClient — no live server required.

Run from backend/ with:
    pytest tests/test_m1_e2e.py -v -s
"""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

FIXTURES = Path(__file__).parent / "fixtures"
DOCX = FIXTURES / "sample_domain.docx"


def _parse_sse(text: str) -> list[dict]:
    """Extract parsed SSE event dicts from a raw SSE response body."""
    events = []
    for line in text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if payload == "[DONE]":
            break
        try:
            events.append(json.loads(payload))
        except Exception:
            pass
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Skip if ANTHROPIC_API_KEY is unset/placeholder (chat test needs real LLM)
# ─────────────────────────────────────────────────────────────────────────────

HAS_REAL_KEY = (
    os.getenv("ANTHROPIC_API_KEY", "").startswith("sk-ant")
)


# ─────────────────────────────────────────────────────────────────────────────
# Full e2e test suite
# ─────────────────────────────────────────────────────────────────────────────

class TestM1E2E:
    """
    End-to-end flow:
      a) Build context from sample_domain.docx
      b) Assert all 4 stages appear in SSE stream
      c) Assert final result shape
      d) GET /mindmap  — nodes + edges > 0
      e) GET /glossary — terms > 0
      f) POST /api/chat/stream — response is domain-aware (with real key)
    """

    @pytest.fixture(autouse=True)
    def client_and_project(self, tmp_path):
        from fastapi.testclient import TestClient
        from app.main import app

        with TestClient(app, raise_server_exceptions=True) as client:
            self.client = client
            # Create project to get a real UUID
            r = client.post("/api/projects/", json={"name": "e2e-test-project"})
            assert r.status_code in (200, 201), f"Project creation failed: {r.text}"
            self.project_id = r.json()["project_id"]
            yield

    # ── a + b + c: build ─────────────────────────────────────────────────────

    @staticmethod
    def _make_mock_llm():
        _entities = json.dumps({
            "entities": [
                {"id": "e1", "name": "Test Case",   "type": "data",    "description": "A test scenario"},
                {"id": "e2", "name": "Defect",      "type": "data",    "description": "A software defect"},
                {"id": "e3", "name": "QA Engineer", "type": "actor",   "description": "Quality assurance specialist"},
            ],
            "relations": [{"source": "e1", "target": "e2", "label": "reveals"}],
        })
        _glossary = json.dumps([
            {"term": "Test Case",  "definition": "A set of conditions to verify behaviour.", "related_terms": [], "source": "docs"},
            {"term": "Defect",     "definition": "Deviation from expected behaviour.",       "related_terms": [], "source": "docs"},
        ])
        _approved = json.dumps({"verdict": "APPROVED"})
        mock = MagicMock()

        async def _side(prompt, **kwargs):
            if "entities and their relationships" in prompt:
                return _entities
            if "domain-specific term" in prompt:  # _enumerate_term_names (phase 1)
                return json.dumps(["Test Case", "Defect", "QA Engineer", "Test Suite"])
            if "Write glossary definitions" in prompt:  # _define_term_group (phase 2)
                return _glossary
            return _approved

        mock.acomplete = AsyncMock(side_effect=_side)
        return mock

    def _run_build(self) -> tuple[list[dict], dict | None]:
        """POST /build with sample_domain.docx, return (all_events, result_event_data)."""
        assert DOCX.exists(), f"Fixture missing: {DOCX}"
        with patch("app.api.routes.context.get_llm", return_value=self._make_mock_llm()), \
             DOCX.open("rb") as fh:
            r = self.client.post(
                f"/api/context/{self.project_id}/build",
                files={"files": (DOCX.name, fh,
                       "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            )
        assert r.status_code == 200
        events = _parse_sse(r.text)
        result_data = next(
            (e["data"] for e in events if e.get("type") == "result"), None
        )
        return events, result_data

    def test_a_build_returns_200_and_sse(self):
        """Build endpoint responds 200 with SSE events."""
        with patch("app.api.routes.context.get_llm", return_value=self._make_mock_llm()), \
             DOCX.open("rb") as fh:
            r = self.client.post(
                f"/api/context/{self.project_id}/build",
                files={"files": (DOCX.name, fh,
                       "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            )
        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")

    def test_b_all_four_stages_appear(self):
        """Progress events must include all 4 pipeline stages."""
        events, _ = self._run_build()
        progress_events = [e for e in events if e.get("type") == "progress"]
        assert len(progress_events) > 0, "No progress events received"

        stages_seen = {e["data"]["stage"] for e in progress_events}
        for expected_stage in ("parse", "embed", "extract", "assemble"):
            assert expected_stage in stages_seen, (
                f"Stage '{expected_stage}' not found in SSE stream. "
                f"Stages seen: {stages_seen}"
            )

    def test_c_result_shape(self):
        """Final result event has rag_ready=True and non-empty mind_map + glossary."""
        _, result = self._run_build()
        assert result is not None, "No 'result' event in SSE stream"
        assert result["rag_ready"] is True

        mm = result["mind_map"]
        assert isinstance(mm["nodes"], list) and len(mm["nodes"]) > 0
        assert isinstance(mm["edges"], list) and len(mm["edges"]) > 0

        glossary = result["glossary"]
        assert isinstance(glossary, list) and len(glossary) > 0
        assert all("term" in t and "definition" in t for t in glossary)

        stats = result["stats"]
        assert stats["entity_count"] > 0
        assert stats["term_count"] > 0

    def test_d_mindmap_endpoint(self):
        """GET /mindmap returns nodes > 0 and edges > 0 after build."""
        self._run_build()
        r = self.client.get(f"/api/context/{self.project_id}/mindmap")
        assert r.status_code == 200
        mm = r.json()
        assert isinstance(mm["nodes"], list) and len(mm["nodes"]) > 0
        assert isinstance(mm["edges"], list) and len(mm["edges"]) > 0

    def test_e_glossary_endpoint(self):
        """GET /glossary returns at least one term after build."""
        self._run_build()
        r = self.client.get(f"/api/context/{self.project_id}/glossary")
        assert r.status_code == 200
        terms = r.json()
        assert isinstance(terms, list) and len(terms) > 0
        assert all("term" in t and "definition" in t for t in terms)

    @pytest.mark.skipif(not HAS_REAL_KEY, reason="Real ANTHROPIC_API_KEY required")
    def test_f_chat_references_domain_content(self):
        """
        After building M1 context, a chat query should produce a response
        that references domain content (not a generic fallback).
        """
        self._run_build()

        r = self.client.post(
            "/api/chat/stream",
            json={
                "project_id": self.project_id,
                "message": "jakie moduły są testowane?",
                "file_paths": [],
                "tier": "audit",
            },
        )
        assert r.status_code == 200
        events = _parse_sse(r.text)
        result_events = [e for e in events if e.get("type") == "result"]
        assert len(result_events) > 0, "No result event in chat stream"

        response_text = result_events[0]["data"].get("message", "").lower()
        assert response_text, "Empty chat response"

        # Should not be a raw error fallback
        assert "connection error" not in response_text
        # Should mention something QA-related
        qa_keywords = ["test", "qa", "quality", "proces", "moduł", "defect", "coverage",
                       "case", "suite", "regression"]
        hits = [kw for kw in qa_keywords if kw in response_text]
        assert len(hits) >= 1, (
            f"Chat response appears generic — no QA keywords found.\n"
            f"Response: {response_text[:300]}"
        )
