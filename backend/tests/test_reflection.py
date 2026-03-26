"""
Reflection pattern tests — M1 Context Builder + Faza 2 Requirements
=====================================================================
Covers:
  - Pass-through when REFLECTION_MAX_ITERATIONS=0 or llm=None
  - Critic returns APPROVED → no refine call made
  - Critic returns NEEDS_REVISION → refine runs, result improved
  - Max iterations respected (critic+refine loop stops at cap)
  - Graceful fallback when critic or refine LLM call raises an exception
  - combined_context stored in ctx.store during requirements extraction
"""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── Shared fixtures ──────────────────────────────────────────────────────────

_APPROVED_RESPONSE = json.dumps({"verdict": "APPROVED"})

_NEEDS_REVISION_RESPONSE = json.dumps({
    "verdict": "NEEDS_REVISION",
    "missing_entities": [{"name": "Payment Gateway", "type": "system"}],
    "duplicate_entities": [],
    "orphan_nodes": [],
    "missing_terms": ["idempotency key"],
    "vague_definitions": [],
})

_ENTITIES_RESPONSE = json.dumps({
    "entities": [
        {"id": "e1", "name": "Test Case", "type": "data", "description": "A test scenario"},
        {"id": "e2", "name": "Defect",    "type": "data", "description": "A software defect"},
    ],
    "relations": [
        {"source": "e1", "target": "e2", "label": "reveals"},
    ],
})

_TERM_NAMES_RESPONSE = json.dumps(["Test Case", "Regression"])

_GLOSSARY_RESPONSE = json.dumps([
    {"term": "Test Case",  "definition": "A set of conditions to verify behaviour.", "related_terms": [], "source": "docs"},
    {"term": "Regression", "definition": "Re-execution of tests after changes.",     "related_terms": [], "source": "docs"},
])

_REFINED_ENTITIES_RESPONSE = json.dumps({
    "entities": [
        {"id": "e1", "name": "Test Case",        "type": "data",   "description": "A test scenario"},
        {"id": "e2", "name": "Defect",           "type": "data",   "description": "A software defect"},
        {"id": "e3", "name": "Payment Gateway",  "type": "system", "description": "External payment processor"},
    ],
    "relations": [
        {"source": "e1", "target": "e2", "label": "reveals"},
        {"source": "e1", "target": "e3", "label": "validates"},
    ],
    "terms": [
        {"term": "Test Case",        "definition": "A set of conditions to verify behaviour.", "related_terms": [], "source": "docs"},
        {"term": "Regression",       "definition": "Re-execution of tests after changes.",     "related_terms": [], "source": "docs"},
        {"term": "idempotency key",  "definition": "A unique key preventing duplicate ops.",   "related_terms": [], "source": "docs"},
    ],
})


def _make_context_builder_workflow(llm=None):
    """Return a ContextBuilderWorkflow with mocked parser + Chroma."""
    from app.agents.context_builder_workflow import ContextBuilderWorkflow

    mock_cb = MagicMock()
    mock_cb.index_from_docs = AsyncMock(return_value=5)

    mock_parser = MagicMock()
    fixed_doc = {
        "filename": "srs.docx",
        "text": "Payment system requirements. Test cases validate defects.",
        "headings": [],
        "tables": [],
        "metadata": {"source": "docx"},
    }
    mock_parser.parse = AsyncMock(return_value=fixed_doc)

    with patch("app.agents.context_builder_workflow.ContextBuilder", return_value=mock_cb), \
         patch("app.agents.context_builder_workflow.DocumentParser", return_value=mock_parser):
        wf = ContextBuilderWorkflow(llm=llm, timeout=60)

    wf.context_builder = mock_cb
    wf.parser = mock_parser
    return wf


def _make_requirements_workflow(llm=None):
    from app.agents.requirements_workflow import RequirementsWorkflow
    wf = RequirementsWorkflow(llm=llm, timeout=60)
    wf.context_builder = MagicMock()
    wf.context_builder.is_indexed = AsyncMock(return_value=True)
    wf.context_builder.build_with_sources = AsyncMock(
        return_value=("FR-001 bank transfer. FR-002 history.", [])
    )
    wf.context_builder.retrieve_nodes = AsyncMock(return_value=[])
    wf.context_builder.get_indexed_filenames = MagicMock(return_value=[])
    return wf


_EXTRACTION_JSON = json.dumps({
    "features": [{
        "title": "Payments", "description": "Payment module", "module": "payments",
        "requirements": [
            {"external_id": "FR-001", "title": "Bank transfer",
             "description": "Initiate transfers.",
             "level": "functional_req", "source_type": "formal",
             "taxonomy": {"module": "payments", "risk_level": "high", "business_domain": "business_logic"},
             "testability": "high", "confidence": 0.95, "needs_review": False,
             "review_reason": None, "acceptance_criteria": []},
        ],
    }],
    "gaps": [],
    "metadata": {"total_features": 1, "total_requirements": 1,
                 "total_acceptance_criteria": 0, "formal_count": 1, "implicit_count": 0,
                 "avg_confidence": 0.95, "low_confidence_count": 0},
})

_REQ_NEEDS_REVISION_RESPONSE = json.dumps({
    "verdict": "NEEDS_REVISION",
    "missing_requirements": [
        {"area": "Auth", "description": "Login flow not covered", "suggested_title": "User login"},
    ],
    "incomplete_requirements": [],
    "duplicates": [],
    "hallucinations": [],
    "missing_acceptance_criteria": [],
})

_REFINED_FEATURES_RESPONSE = json.dumps({
    "features": [
        {
            "title": "Payments", "description": "Payment module", "module": "payments",
            "requirements": [
                {"external_id": "FR-001", "title": "Bank transfer",
                 "description": "Initiate transfers.",
                 "level": "functional_req", "source_type": "formal",
                 "taxonomy": {"module": "payments", "risk_level": "high", "business_domain": "business_logic"},
                 "testability": "high", "confidence": 0.95, "needs_review": False,
                 "review_reason": None, "acceptance_criteria": []},
            ],
        },
        {
            "title": "Auth", "description": "Authentication", "module": "auth",
            "requirements": [
                {"external_id": None, "title": "User login",
                 "description": "Users can log in with credentials.",
                 "level": "functional_req", "source_type": "implicit",
                 "taxonomy": {"module": "auth", "risk_level": "high", "business_domain": "security"},
                 "testability": "high", "confidence": 0.80, "needs_review": False,
                 "review_reason": None, "acceptance_criteria": []},
            ],
        },
    ],
    "gaps": [],
})


# ═══════════════════════════════════════════════════════════════════════════════
# M1 Context Builder — Reflection Tests
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_m1_reflection_no_llm_passthrough():
    """With llm=None the review step passes through without LLM calls."""
    wf = _make_context_builder_workflow(llm=None)
    with patch("app.agents.context_builder_workflow.ContextBuilder", return_value=wf.context_builder), \
         patch("app.agents.context_builder_workflow.DocumentParser", return_value=wf.parser):
        handler = wf.run(project_id="refl-no-llm", file_paths=["/fake/srs.docx"])
        async for _ in handler.stream_events():
            pass
        result = await handler

    assert result["rag_ready"] is True
    assert len(result["mind_map"]["nodes"]) > 0
    assert len(result["glossary"]) > 0


@pytest.mark.asyncio
async def test_m1_reflection_disabled_max_iter_zero():
    """REFLECTION_MAX_ITERATIONS=0 skips LLM review calls entirely."""
    calls = []

    async def _side(prompt, **kwargs):
        calls.append(prompt[:30])
        if "entities and their relationships" in prompt:
            return _ENTITIES_RESPONSE
        if "domain-specific term" in prompt:
            return _TERM_NAMES_RESPONSE
        return _GLOSSARY_RESPONSE  # "Write glossary definitions"

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(side_effect=_side)

    wf = _make_context_builder_workflow(llm=mock_llm)

    with patch("app.agents.context_builder_workflow.ContextBuilder", return_value=wf.context_builder), \
         patch("app.agents.context_builder_workflow.DocumentParser", return_value=wf.parser), \
         patch("app.agents.context_builder_workflow.settings") as mock_settings:
        mock_settings.REFLECTION_MAX_ITERATIONS = 0
        mock_settings.LLM_CONCURRENT_CALLS = 4
        mock_settings.M1_BATCH_CHARS = 12_000
        mock_settings.M1_BATCH_OVERLAP = 1_800
        mock_settings.M1_GLOSSARY_TERMS_PER_GROUP = 15
        handler = wf.run(project_id="refl-zero", file_paths=["/fake/srs.docx"])
        async for _ in handler.stream_events():
            pass
        result = await handler

    # Only 3 calls: entities + enumerate terms + define group — no critic or refine
    assert len(calls) == 3
    assert result["rag_ready"] is True


@pytest.mark.asyncio
async def test_m1_reflection_approved_first_pass():
    """Critic returns APPROVED → refine is never called; workflow completes normally."""
    calls = []

    async def _side(prompt, **kwargs):
        calls.append("call")
        if "entities and their relationships" in prompt:
            return _ENTITIES_RESPONSE
        if "domain-specific term" in prompt:
            return _TERM_NAMES_RESPONSE
        if "Write glossary definitions" in prompt:
            return _GLOSSARY_RESPONSE
        # calls 4+ = critic
        return _APPROVED_RESPONSE

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(side_effect=_side)

    wf = _make_context_builder_workflow(llm=mock_llm)

    with patch("app.agents.context_builder_workflow.ContextBuilder", return_value=wf.context_builder), \
         patch("app.agents.context_builder_workflow.DocumentParser", return_value=wf.parser), \
         patch("app.agents.context_builder_workflow.settings") as mock_settings:
        mock_settings.REFLECTION_MAX_ITERATIONS = 2
        mock_settings.LLM_CONCURRENT_CALLS = 4
        mock_settings.M1_BATCH_CHARS = 12_000
        mock_settings.M1_BATCH_OVERLAP = 1_800
        mock_settings.M1_GLOSSARY_TERMS_PER_GROUP = 15
        handler = wf.run(project_id="refl-approved", file_paths=["/fake/srs.docx"])
        async for _ in handler.stream_events():
            pass
        result = await handler

    # Exactly 4 calls: entities + enumerate terms + define group + critic (approved, no refine)
    assert len(calls) == 4
    assert result["rag_ready"] is True


@pytest.mark.asyncio
async def test_m1_reflection_refines_on_issues():
    """Critic returns NEEDS_REVISION → per-issue refine calls run → critic approves → result has refined data."""
    calls = []

    _NEW_ENTITY = json.dumps({"name": "Payment Gateway", "type": "system", "description": "External payment processor"})
    _NEW_TERM = json.dumps({"term": "idempotency key", "definition": "A unique key preventing duplicate ops.", "related_terms": [], "source": "uploaded documentation"})

    critic_calls = []

    async def _side(prompt, **kwargs):
        calls.append("call")
        if "entities and their relationships" in prompt:
            return _ENTITIES_RESPONSE         # entity extraction
        if "domain-specific term" in prompt:
            return _TERM_NAMES_RESPONSE       # enumerate term names
        if "Write glossary definitions" in prompt:
            return _GLOSSARY_RESPONSE         # define term group
        if "quality review" in prompt:
            critic_calls.append("critic")
            # First critic pass → needs revision; second → approved
            return _NEEDS_REVISION_RESPONSE if len(critic_calls) == 1 else _APPROVED_RESPONSE
        if "Create a domain entity entry for" in prompt:
            return _NEW_ENTITY                # per-issue refine: missing entity
        if "Write a glossary entry for the term" in prompt:
            return _NEW_TERM                  # per-issue refine: missing term
        return _APPROVED_RESPONSE

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(side_effect=_side)

    wf = _make_context_builder_workflow(llm=mock_llm)

    with patch("app.agents.context_builder_workflow.ContextBuilder", return_value=wf.context_builder), \
         patch("app.agents.context_builder_workflow.DocumentParser", return_value=wf.parser), \
         patch("app.agents.context_builder_workflow.settings") as mock_settings:
        mock_settings.REFLECTION_MAX_ITERATIONS = 2
        mock_settings.LLM_CONCURRENT_CALLS = 4
        mock_settings.M1_BATCH_CHARS = 12_000
        mock_settings.M1_BATCH_OVERLAP = 1_800
        mock_settings.M1_GLOSSARY_TERMS_PER_GROUP = 15
        handler = wf.run(project_id="refl-refine", file_paths=["/fake/srs.docx"])
        async for _ in handler.stream_events():
            pass
        result = await handler

    # 7 calls: entities + enumerate terms + define group + critic1 + create_entity + create_term + critic2
    assert len(calls) == 7
    node_names = [n["label"] for n in result["mind_map"]["nodes"]]
    assert "Payment Gateway" in node_names, "Refined entity should be in mind map"
    term_names = [t["term"] for t in result["glossary"]]
    assert "idempotency key" in term_names, "Refined term should be in glossary"


@pytest.mark.asyncio
async def test_m1_reflection_max_iterations_respected():
    """Critic always returns NEEDS_REVISION (empty issues) but loop stops at REFLECTION_MAX_ITERATIONS=2."""
    # Use an empty-issues NEEDS_REVISION so refine makes zero per-issue LLM calls.
    # This lets us count exactly: 3 extract + 2 critic = 5 calls, regardless of refine internals.
    _needs_revision_empty = json.dumps({
        "verdict": "NEEDS_REVISION",
        "missing_entities": [],
        "duplicate_entities": [],
        "orphan_nodes": [],
        "missing_terms": [],
        "vague_definitions": [],
    })
    calls = []

    async def _side(prompt, **kwargs):
        calls.append("call")
        if "entities and their relationships" in prompt:
            return _ENTITIES_RESPONSE
        if "domain-specific term" in prompt:
            return _TERM_NAMES_RESPONSE
        if "Write glossary definitions" in prompt:
            return _GLOSSARY_RESPONSE
        return _needs_revision_empty  # critic always NEEDS_REVISION, no items to fix

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(side_effect=_side)

    wf = _make_context_builder_workflow(llm=mock_llm)

    with patch("app.agents.context_builder_workflow.ContextBuilder", return_value=wf.context_builder), \
         patch("app.agents.context_builder_workflow.DocumentParser", return_value=wf.parser), \
         patch("app.agents.context_builder_workflow.settings") as mock_settings:
        mock_settings.REFLECTION_MAX_ITERATIONS = 2
        mock_settings.LLM_CONCURRENT_CALLS = 4
        mock_settings.M1_BATCH_CHARS = 12_000
        mock_settings.M1_BATCH_OVERLAP = 1_800
        mock_settings.M1_GLOSSARY_TERMS_PER_GROUP = 15
        handler = wf.run(project_id="refl-max-iter", file_paths=["/fake/srs.docx"])
        async for _ in handler.stream_events():
            pass
        result = await handler

    # 3 extract calls + 2 critic calls (no per-issue refine calls since issues are empty)
    assert len(calls) == 5
    assert result["rag_ready"] is True


@pytest.mark.asyncio
async def test_m1_reflection_critic_failure_graceful():
    """If the critic LLM call raises an exception, workflow still returns original extraction."""
    calls = []

    async def _side(prompt, **kwargs):
        calls.append("call")
        if "entities and their relationships" in prompt:
            return _ENTITIES_RESPONSE
        if "domain-specific term" in prompt:
            return _TERM_NAMES_RESPONSE
        if "Write glossary definitions" in prompt:
            return _GLOSSARY_RESPONSE
        raise RuntimeError("LLM service unavailable")  # critic fails (call 4)

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(side_effect=_side)

    wf = _make_context_builder_workflow(llm=mock_llm)

    with patch("app.agents.context_builder_workflow.ContextBuilder", return_value=wf.context_builder), \
         patch("app.agents.context_builder_workflow.DocumentParser", return_value=wf.parser), \
         patch("app.agents.context_builder_workflow.settings") as mock_settings:
        mock_settings.REFLECTION_MAX_ITERATIONS = 2
        mock_settings.LLM_CONCURRENT_CALLS = 4
        mock_settings.M1_BATCH_CHARS = 12_000
        mock_settings.M1_BATCH_OVERLAP = 1_800
        mock_settings.M1_GLOSSARY_TERMS_PER_GROUP = 15
        handler = wf.run(project_id="refl-critic-fail", file_paths=["/fake/srs.docx"])
        async for _ in handler.stream_events():
            pass
        result = await handler

    assert result["rag_ready"] is True
    assert len(result["mind_map"]["nodes"]) > 0


@pytest.mark.asyncio
async def test_m1_reflection_refine_failure_graceful():
    """If the refine LLM call fails, the pre-refine extraction is kept."""
    calls = []

    async def _side(prompt, **kwargs):
        calls.append("call")
        if "entities and their relationships" in prompt:
            return _ENTITIES_RESPONSE
        if "domain-specific term" in prompt:
            return _TERM_NAMES_RESPONSE
        if "Write glossary definitions" in prompt:
            return _GLOSSARY_RESPONSE
        if "quality review" in prompt:
            return _NEEDS_REVISION_RESPONSE    # critic: needs revision
        raise RuntimeError("refine LLM failed")  # per-issue refine fails

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(side_effect=_side)

    wf = _make_context_builder_workflow(llm=mock_llm)

    with patch("app.agents.context_builder_workflow.ContextBuilder", return_value=wf.context_builder), \
         patch("app.agents.context_builder_workflow.DocumentParser", return_value=wf.parser), \
         patch("app.agents.context_builder_workflow.settings") as mock_settings:
        mock_settings.REFLECTION_MAX_ITERATIONS = 2
        mock_settings.LLM_CONCURRENT_CALLS = 4
        mock_settings.M1_BATCH_CHARS = 12_000
        mock_settings.M1_BATCH_OVERLAP = 1_800
        mock_settings.M1_GLOSSARY_TERMS_PER_GROUP = 15
        handler = wf.run(project_id="refl-refine-fail", file_paths=["/fake/srs.docx"])
        async for _ in handler.stream_events():
            pass
        result = await handler

    # Original entities from _ENTITIES_RESPONSE (2 nodes), no Payment Gateway added
    assert result["rag_ready"] is True
    node_names = [n["label"] for n in result["mind_map"]["nodes"]]
    assert "Payment Gateway" not in node_names


# ═══════════════════════════════════════════════════════════════════════════════
# Faza 2 Requirements — Reflection Tests
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_req_reflection_disabled_no_llm():
    """With llm=None, review step skips LLM calls and applies rule-based pass only."""
    wf = _make_requirements_workflow(llm=None)
    handler = wf.run(project_id="req-no-llm", user_message="")
    async for _ in handler.stream_events():
        pass
    result = await handler
    # Mock data from _mock_extraction() is returned
    assert "features" in result
    assert result["metadata"]["total_requirements"] > 0


@pytest.mark.asyncio
async def test_req_reflection_approved_first_pass():
    """Critic returns APPROVED → refine not called; extraction unchanged."""
    calls = []

    async def _side(prompt, **kwargs):
        calls.append("call")
        if len(calls) == 1:
            return _EXTRACTION_JSON
        return _APPROVED_RESPONSE  # critic: approved

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(side_effect=_side)

    wf = _make_requirements_workflow(llm=mock_llm)

    with patch("app.agents.requirements_workflow.settings") as mock_settings:
        mock_settings.REFLECTION_MAX_ITERATIONS = 2
        mock_settings.LLM_CONCURRENT_CALLS = 4
        handler = wf.run(project_id="req-approved", user_message="")
        async for _ in handler.stream_events():
            pass
        result = await handler

    # 2 calls: extract + critic (approved → no refine)
    assert len(calls) == 2
    assert len(result["features"]) == 1
    titles = [f["title"] for f in result["features"]]
    assert "Payments" in titles


@pytest.mark.asyncio
async def test_req_reflection_adds_missing_requirements():
    """Critic flags missing requirement → refine adds it → result has 2 features."""
    calls = []

    async def _side(prompt, **kwargs):
        calls.append("call")
        if len(calls) == 1:
            return _EXTRACTION_JSON
        if len(calls) == 2:
            return _REQ_NEEDS_REVISION_RESPONSE   # critic: needs revision
        if len(calls) == 3:
            return _REFINED_FEATURES_RESPONSE      # refine: adds Auth feature
        return _APPROVED_RESPONSE                  # critic pass 2

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(side_effect=_side)

    wf = _make_requirements_workflow(llm=mock_llm)

    with patch("app.agents.requirements_workflow.settings") as mock_settings:
        mock_settings.REFLECTION_MAX_ITERATIONS = 2
        mock_settings.LLM_CONCURRENT_CALLS = 4
        handler = wf.run(project_id="req-refine", user_message="")
        async for _ in handler.stream_events():
            pass
        result = await handler

    # extract + critic1 + refine + critic2
    assert len(calls) == 4
    feature_titles = [f["title"] for f in result["features"]]
    assert "Auth" in feature_titles, "Refined Auth feature should be present"
    assert "Payments" in feature_titles


@pytest.mark.asyncio
async def test_req_reflection_max_iterations_respected():
    """Critic always returns NEEDS_REVISION — loop stops at REFLECTION_MAX_ITERATIONS=2."""
    calls = []

    async def _side(prompt, **kwargs):
        calls.append("call")
        if len(calls) == 1:
            return _EXTRACTION_JSON
        if len(calls) % 2 == 0:
            return _REQ_NEEDS_REVISION_RESPONSE  # critic — always needs revision
        return _REFINED_FEATURES_RESPONSE        # refine

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(side_effect=_side)

    wf = _make_requirements_workflow(llm=mock_llm)

    with patch("app.agents.requirements_workflow.settings") as mock_settings:
        mock_settings.REFLECTION_MAX_ITERATIONS = 2
        mock_settings.LLM_CONCURRENT_CALLS = 4
        handler = wf.run(project_id="req-max-iter", user_message="")
        async for _ in handler.stream_events():
            pass
        result = await handler

    # 1 extract + 2×(critic + refine) = 5 max
    assert len(calls) <= 5
    assert "features" in result


@pytest.mark.asyncio
async def test_req_reflection_critic_failure_graceful():
    """If critic LLM call raises an exception, original extraction is kept."""
    calls = []

    async def _side(prompt, **kwargs):
        calls.append("call")
        if len(calls) == 1:
            return _EXTRACTION_JSON
        raise RuntimeError("critic unavailable")

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(side_effect=_side)

    wf = _make_requirements_workflow(llm=mock_llm)

    with patch("app.agents.requirements_workflow.settings") as mock_settings:
        mock_settings.REFLECTION_MAX_ITERATIONS = 2
        mock_settings.LLM_CONCURRENT_CALLS = 4
        handler = wf.run(project_id="req-critic-fail", user_message="")
        async for _ in handler.stream_events():
            pass
        result = await handler

    assert len(result.get("features", [])) == 1  # original Payments feature intact


@pytest.mark.asyncio
async def test_req_reflection_refine_failure_graceful():
    """If refine LLM call fails, pre-refine extraction is preserved."""
    calls = []

    async def _side(prompt, **kwargs):
        calls.append("call")
        if len(calls) == 1:
            return _EXTRACTION_JSON
        if len(calls) == 2:
            return _REQ_NEEDS_REVISION_RESPONSE
        raise RuntimeError("refine unavailable")

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(side_effect=_side)

    wf = _make_requirements_workflow(llm=mock_llm)

    with patch("app.agents.requirements_workflow.settings") as mock_settings:
        mock_settings.REFLECTION_MAX_ITERATIONS = 2
        mock_settings.LLM_CONCURRENT_CALLS = 4
        handler = wf.run(project_id="req-refine-fail", user_message="")
        async for _ in handler.stream_events():
            pass
        result = await handler

    # Auth feature was NOT added because refine failed
    feature_titles = [f["title"] for f in result.get("features", [])]
    assert "Auth" not in feature_titles
    assert "Payments" in feature_titles


@pytest.mark.asyncio
async def test_req_combined_context_passed_to_critic():
    """combined_context from RAG is included in the critic's prompt."""
    critic_prompts = []

    async def _side(prompt, **kwargs):
        if not critic_prompts:
            return _EXTRACTION_JSON   # first call = extraction
        critic_prompts.append(prompt)
        return _APPROVED_RESPONSE

    # Intercept: first non-extraction call is the critic
    call_count = 0

    async def _capturing_side(prompt, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _EXTRACTION_JSON
        critic_prompts.append(prompt)
        return _APPROVED_RESPONSE

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(side_effect=_capturing_side)

    wf = _make_requirements_workflow(llm=mock_llm)
    # retrieve_nodes returns a distinctive node so the marker ends up in combined_context
    # and subsequently in the critic's source_sample
    class _MockNode:
        def get_content(self): return "UNIQUE_SOURCE_MARKER payment transfer FR-001"
        metadata = {"filename": "srs.docx", "first_heading": "", "has_tables": False, "is_table_row": False}
    wf.context_builder.retrieve_nodes = AsyncMock(return_value=[_MockNode()])
    wf.context_builder.get_indexed_filenames = MagicMock(return_value=[])

    with patch("app.agents.requirements_workflow.settings") as mock_settings:
        mock_settings.REFLECTION_MAX_ITERATIONS = 1
        mock_settings.LLM_CONCURRENT_CALLS = 4
        mock_settings.RAG_TOP_K = 10
        mock_settings.RAG_MAX_CONTEXT_CHARS = 60_000
        handler = wf.run(project_id="req-ctx-store", user_message="")
        async for _ in handler.stream_events():
            pass
        await handler

    assert critic_prompts, "Critic should have been called"
    assert "UNIQUE_SOURCE_MARKER" in critic_prompts[0], \
        "Critic prompt should contain combined_context from RAG"


@pytest.mark.asyncio
async def test_req_reflection_rule_based_always_runs():
    """Rule-based _apply_validation runs after reflection — low-confidence reqs are flagged."""
    calls = []

    low_conf_extraction = json.dumps({
        "features": [{
            "title": "Feature A", "description": "desc", "module": "mod",
            "requirements": [
                {"external_id": None, "title": "Vague req",
                 "description": "Something happens somehow.",
                 "level": "functional_req", "source_type": "implicit",
                 "taxonomy": {}, "testability": "low",
                 "confidence": 0.50,   # < 0.7 threshold → should be flagged
                 "needs_review": False, "review_reason": None, "acceptance_criteria": []},
            ],
        }],
        "gaps": [],
        "metadata": {"total_features": 1, "total_requirements": 1,
                     "total_acceptance_criteria": 0, "formal_count": 0, "implicit_count": 1,
                     "avg_confidence": 0.50, "low_confidence_count": 1},
    })

    async def _side(prompt, **kwargs):
        calls.append("call")
        if len(calls) == 1:
            return low_conf_extraction
        return _APPROVED_RESPONSE

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(side_effect=_side)

    wf = _make_requirements_workflow(llm=mock_llm)

    with patch("app.agents.requirements_workflow.settings") as mock_settings:
        mock_settings.REFLECTION_MAX_ITERATIONS = 1
        mock_settings.LLM_CONCURRENT_CALLS = 4
        handler = wf.run(project_id="req-rule-based", user_message="")
        async for _ in handler.stream_events():
            pass
        result = await handler

    flat = result.get("requirements_flat", [])
    vague = [r for r in flat if r.get("title") == "Vague req"]
    assert vague, "Vague req should be in flat list"
    assert vague[0]["needs_review"] is True, "Low-confidence req should be flagged by rule-based pass"
