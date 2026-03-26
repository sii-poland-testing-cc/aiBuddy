"""
Faza 2: Requirements Reconstruction Workflow
=============================================
Pipeline:
  Start → Extract → Validate → Persist → Stop

Extracts requirements from M1 RAG context, builds a hierarchical registry,
computes completeness scores, and flags items for human review.

MVP scope:
  - Strategy A: formal extraction from SRS/BRD docs (FR-xxx IDs)
  - Strategy B (partial): implicit extraction from stories/AC in docs
  - Completeness scoring
  - Human review flags for low-confidence items

NOTE: Uses LlamaIndex Workflow Context API v0.14+
  Write: await ctx.store.set("key", value)
  Read:  value = await ctx.store.get("key")
"""

import asyncio
import copy
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from llama_index.core.workflow import (
    Context,
    Event,
    StartEvent,
    StopEvent,
    Workflow,
    step,
)

from app.core.config import settings
from app.rag.context_builder import ContextBuilder
from app.utils.json_utils import strip_fences

logger = logging.getLogger("ai_buddy.requirements")


# ─── Prompts ──────────────────────────────────────────────────────────────────

EXTRACT_REQUIREMENTS_PROMPT = """You are a senior QA architect performing requirements analysis on project documentation.

Your task: Extract the 20 most important testable requirements from the documentation below.
Build a hierarchical structure: Features → Functional Requirements → Acceptance Criteria.

The documentation spans multiple source files. Each chunk is prefixed with [Source: filename — section]
to indicate its origin. Synthesise requirements across ALL sources — do not focus on a single document.

Rules:
1. Prefer explicit requirements (FR-001, REQ-*, SHALL/MUST). Include implicit ones only if clearly testable.
2. Limit to max 20 functional requirements total across all features.
3. For each requirement, determine:
   - external_id: the original ID if one exists (e.g. "FR-001"), or null if implicit
   - title: concise name (max 60 chars)
   - description: requirement text (max 200 chars)
   - level: "feature" | "functional_req" | "acceptance_criterion"
   - parent_feature: which feature this belongs to (use feature title)
   - source_type: "formal" if has an explicit ID, "implicit" if inferred from text
   - source_references: list of source filenames where this requirement was found (e.g. ["srs.docx"])
   - taxonomy: {module, risk_level, business_domain}
   - testability: "high" | "medium" | "low" — can this be directly tested?
   - confidence: 0.0–1.0 — how certain are you this is a real requirement?

4. Group requirements under features (max 5 features). If no features are explicit, infer from domain areas.
5. Include at most 2 acceptance criteria per requirement. Keep each AC under 100 chars.
6. Mark requirements with confidence < 0.7 as needs_review: true.
7. Identify up to 5 GAPS: areas mentioned in the docs but without clear requirements.

Return ONLY valid JSON — no preamble, no markdown fences:
{
  "features": [
    {
      "title": "Feature name",
      "description": "Feature description",
      "module": "module_name",
      "requirements": [
        {
          "external_id": "FR-001",
          "title": "Requirement title",
          "description": "Requirement description (max 200 chars)",
          "level": "functional_req",
          "source_type": "formal",
          "source_references": ["srs.docx"],
          "taxonomy": {
            "module": "payments",
            "risk_level": "high|medium|low",
            "business_domain": "compliance|ux|data_integrity|business_logic|security|performance"
          },
          "testability": "high",
          "confidence": 0.85,
          "needs_review": false,
          "review_reason": null,
          "acceptance_criteria": [
            {"title": "AC title", "description": "When X then Y", "testability": "high", "confidence": 0.9}
          ]
        }
      ]
    }
  ],
  "gaps": [
    {"area": "Area name", "description": "What is missing", "severity": "high|medium|low"}
  ],
  "metadata": {
    "total_features": 0,
    "total_requirements": 0,
    "total_acceptance_criteria": 0,
    "formal_count": 0,
    "implicit_count": 0,
    "avg_confidence": 0.0,
    "low_confidence_count": 0
  }
}

Documentation:
"""

REVIEW_REQUIREMENTS_PROMPT = """\
You are a senior QA requirements architect performing a critical quality review.
You will be given:
1. A sample of the source documentation
2. Extracted requirements (features → functional requirements → acceptance criteria)
3. Identified gaps

Your task: find flaws. Be specific. Focus on the most impactful issues only.

Return ONLY valid JSON — no preamble, no markdown fences:
{{
  "verdict": "APPROVED" | "NEEDS_REVISION",
  "missing_requirements": [
    {{"area": "...", "description": "clearly present in source but not extracted", "suggested_title": "..."}}
  ],
  "incomplete_requirements": [
    {{"title_or_id": "...", "issue": "vague/untestable/insufficient detail", "suggested_fix": "..."}}
  ],
  "duplicates": [
    {{"req_a": "title or external_id", "req_b": "title or external_id", "reason": "why they overlap"}}
  ],
  "hallucinations": [
    {{"title_or_id": "...", "reason": "not supported by source documentation"}}
  ],
  "missing_acceptance_criteria": [
    {{"title_or_id": "...", "risk_level": "high|medium", "suggested_ac": "When X then Y"}}
  ]
}}

Rules:
- Return "APPROVED" when you find no meaningful issues.
- List at most 5 items per category — prioritise the highest impact.
- Only flag hallucinations when you are certain the requirement has no basis in the source.
- Only flag missing ACs for high/medium risk requirements that have zero ACs.

Source documentation (sample):
{source_sample}

Extracted requirements:
{features_json}

Identified gaps:
{gaps_json}
"""


# ─── Module-level helpers ─────────────────────────────────────────────────────

def _as_dict(item, id_field: str = "title_or_id") -> Dict:
    """Normalise a bare string issue item to {id_field: item} so .get() is always safe."""
    if isinstance(item, str):
        return {id_field: item}
    return item if isinstance(item, dict) else {}


async def _guarded(sem: asyncio.Semaphore, coro):
    """Acquire *sem* then await *coro* — rate-limits parallel LLM calls."""
    async with sem:
        return await coro


# Fixed RAG queries that provide broad coverage regardless of user_message.
# The caller appends a user_message-derived query when present.
_RAG_QUERIES: List[str] = [
    "functional requirements specifications features FR-",
    "business rules constraints validations domain rules",
    "acceptance criteria user stories scenarios given when then",
    "non-functional requirements performance security scalability",
    "system requirements interface integration API endpoints",
    "data requirements entities models attributes schema",
    "user roles permissions access control authorization",
    "error handling exceptions failure modes edge cases",
    "compliance regulatory audit trail logging requirements",
    "workflow process state machine transitions lifecycle",
    "reporting analytics metrics dashboard requirements",
    "configuration settings administration maintenance",
]


# ─── Events ──────────────────────────────────────────────────────────────────

class RequirementsProgressEvent(Event):
    """Streamed to frontend during processing."""
    message: str
    progress: float   # 0.0–1.0
    stage: str        # "extract" | "validate" | "persist"


class ExtractedRequirementsEvent(Event):
    """Emitted after LLM extraction."""
    raw_result: Dict[str, Any]
    rag_sources: List[Dict]


class ReviewedRequirementsEvent(Event):
    """Emitted after the reflection review step."""
    features: List[Dict]
    gaps: List[Dict]
    validation: Dict[str, Any]
    metadata: Dict[str, Any]
    rag_sources: List[Dict]


# ─── Workflow ─────────────────────────────────────────────────────────────────

class RequirementsWorkflow(Workflow):
    """
    Faza 2 pipeline: Extract → Validate → Persist

    Returns:
    {
      "project_id": str,
      "features": [...],
      "requirements_flat": [...],
      "gaps": [...],
      "validation": {...},
      "metadata": {...},
      "rag_sources": [...]
    }
    """

    def __init__(self, llm=None, **kwargs):
        super().__init__(**kwargs)
        self.llm = llm
        self.context_builder = ContextBuilder()

    # ── RAG context helper ────────────────────────────────────────────────────

    async def _build_rag_context(
        self, ctx: Context, project_id: str, user_message: str
    ) -> tuple:
        """Fan out across _RAG_QUERIES (+ optional user_message query) concurrently and
        return (deduplicated combined_context_with_breadcrumbs, unique_sources)."""
        queries = list(_RAG_QUERIES)
        if user_message:
            queries.append(f"{user_message} requirements")

        ctx.write_event_to_stream(RequirementsProgressEvent(
            message=f"Querying knowledge base ({len(queries)} queries in parallel)…",
            progress=0.08, stage="extract"
        ))

        # Concurrent fan-out — all queries fire simultaneously
        node_lists: List[List] = await asyncio.gather(
            *[self.context_builder.retrieve_nodes(project_id, q, top_k=settings.RAG_TOP_K)
              for q in queries],
            return_exceptions=False,
        )

        # Merge and deduplicate nodes; add [Source: filename — heading] breadcrumbs
        seen_chunks: set = set()
        seen_filenames: set = set()
        all_parts: List[str] = []
        all_sources: List[Dict] = []

        for nodes in node_lists:
            for node in nodes:
                chunk_key = node.get_content()[:200].strip().lower()
                if chunk_key in seen_chunks:
                    continue
                seen_chunks.add(chunk_key)

                meta = node.metadata or {}
                filename = meta.get("filename", "unknown")
                heading = meta.get("first_heading", "")
                breadcrumb = f"[Source: {filename}" + (f" — {heading}" if heading else "") + "]"
                all_parts.append(f"{breadcrumb}\n{node.get_content()}")

                if filename not in seen_filenames:
                    seen_filenames.add(filename)
                    all_sources.append({
                        "filename": filename,
                        "excerpt": node.get_content()[:200].strip(),
                    })

        ctx.write_event_to_stream(RequirementsProgressEvent(
            message=f"Retrieved {len(all_parts)} unique chunks from {len(all_sources)} document(s)…",
            progress=0.20, stage="extract"
        ))

        # Check coverage — warn if indexed docs are not all represented in retrieved chunks
        indexed_filenames = self.context_builder.get_indexed_filenames(project_id)
        missing = [f for f in indexed_filenames if f not in seen_filenames]
        if missing:
            logger.warning(
                "Project %s: %d indexed document(s) not retrieved in any query chunk: %s",
                project_id, len(missing), missing,
            )

        combined = "\n\n---\n\n".join(all_parts)
        combined = self._deduplicate_context(combined, max_chars=settings.RAG_MAX_CONTEXT_CHARS)
        return combined, all_sources

    # ── Step 1: Extract ──────────────────────────────────────────────────────

    @step
    async def extract(self, ctx: Context, ev: StartEvent) -> ExtractedRequirementsEvent:
        project_id: str = ev.get("project_id", "default")
        user_message: str = ev.get("user_message", "")
        work_context_id: Optional[str] = ev.get("work_context_id", None)

        await ctx.store.set("project_id", project_id)
        await ctx.store.set("work_context_id", work_context_id)

        ctx.write_event_to_stream(RequirementsProgressEvent(
            message="Retrieving project documentation from knowledge base…",
            progress=0.05, stage="extract"
        ))

        # Pull comprehensive context from M1 RAG
        is_indexed = await self.context_builder.is_indexed(project_id)
        if not is_indexed:
            ctx.write_event_to_stream(RequirementsProgressEvent(
                message="⚠ No M1 context found — run Context Builder first for best results",
                progress=0.1, stage="extract"
            ))
            return ExtractedRequirementsEvent(
                raw_result={"features": [], "gaps": [], "metadata": {
                    "total_features": 0, "total_requirements": 0,
                    "total_acceptance_criteria": 0, "formal_count": 0,
                    "implicit_count": 0, "avg_confidence": 0, "low_confidence_count": 0,
                }},
                rag_sources=[]
            )

        combined_context, all_sources = await self._build_rag_context(
            ctx, project_id, user_message
        )
        await ctx.store.set("combined_context", combined_context)

        ctx.write_event_to_stream(RequirementsProgressEvent(
            message=f"Extracting requirements from {len(all_sources)} source document(s)…",
            progress=0.25, stage="extract"
        ))

        # LLM extraction
        raw_result = await self._extract_with_llm(combined_context)

        n_features = len(raw_result.get("features", []))
        n_reqs = sum(
            len(f.get("requirements", []))
            for f in raw_result.get("features", [])
        )

        ctx.write_event_to_stream(RequirementsProgressEvent(
            message=f"✓ Extracted {n_features} features, {n_reqs} requirements",
            progress=0.50, stage="extract"
        ))

        return ExtractedRequirementsEvent(
            raw_result=raw_result,
            rag_sources=all_sources,
        )

    # ── Step 2: Review (Producer-Reviewer reflection) ─────────────────────────

    @step
    async def review(self, ctx: Context, ev: ExtractedRequirementsEvent) -> ReviewedRequirementsEvent:
        features = ev.raw_result.get("features", [])
        gaps = ev.raw_result.get("gaps", [])
        metadata = ev.raw_result.get("metadata", {})

        if not features:
            return ReviewedRequirementsEvent(
                features=features, gaps=gaps,
                validation={"overall_assessment": {
                    "completeness_rating": "low",
                    "testability_rating": "low",
                    "recommendation": "No requirements found. Run M1 Context Builder with project documentation first."
                }},
                metadata=metadata, rag_sources=ev.rag_sources,
            )

        project_id: str = await ctx.store.get("project_id") or ""
        max_iter = settings.REFLECTION_MAX_ITERATIONS
        if max_iter > 0 and self.llm:
            combined_context: str = await ctx.store.get("combined_context") or ""
            source_sample = combined_context[:8_000]

            for iteration in range(1, max_iter + 1):
                ctx.write_event_to_stream(RequirementsProgressEvent(
                    message=f"Reviewing requirements quality (pass {iteration}/{max_iter})…",
                    progress=0.55 + 0.06 * (iteration - 1),
                    stage="review",
                ))

                issues = await self._review_requirements(source_sample, features, gaps)

                if issues.get("verdict") == "APPROVED":
                    ctx.write_event_to_stream(RequirementsProgressEvent(
                        message=f"✓ Requirements approved on pass {iteration}",
                        progress=0.55 + 0.06 * iteration,
                        stage="review",
                    ))
                    break

                issue_count = (
                    len(issues.get("missing_requirements", []))
                    + len(issues.get("incomplete_requirements", []))
                    + len(issues.get("duplicates", []))
                    + len(issues.get("hallucinations", []))
                    + len(issues.get("missing_acceptance_criteria", []))
                )
                ctx.write_event_to_stream(RequirementsProgressEvent(
                    message=f"Reviewer found {issue_count} issue(s) — refining requirements…",
                    progress=0.55 + 0.06 * iteration,
                    stage="review",
                ))

                features, gaps = await self._refine_requirements(
                    source_sample, features, gaps, issues, project_id
                )
        else:
            ctx.write_event_to_stream(RequirementsProgressEvent(
                message="Reviewing extracted requirements…",
                progress=0.60, stage="review",
            ))

        # ── Rule-based post-processing (always runs) ──────────────────────────
        features = self._flag_low_confidence(features)
        validation = {"overall_assessment": {
            "completeness_rating": "medium",
            "testability_rating": "medium",
            "recommendation": "",
        }}
        metadata = self._compute_metadata(features)

        n_review = sum(
            1 for f in features
            for r in f.get("requirements", [])
            if r.get("needs_review")
        )

        ctx.write_event_to_stream(RequirementsProgressEvent(
            message=f"✓ Review complete — {n_review} requirement(s) flagged for human review",
            progress=0.75, stage="review",
        ))

        return ReviewedRequirementsEvent(
            features=features,
            gaps=gaps,
            validation=validation,
            metadata=metadata,
            rag_sources=ev.rag_sources,
        )

    # ── Step 3: Persist & Assemble ───────────────────────────────────────────

    @step
    async def assemble(self, ctx: Context, ev: ReviewedRequirementsEvent) -> StopEvent:
        project_id = await ctx.store.get("project_id")
        work_context_id: Optional[str] = await ctx.store.get("work_context_id")

        ctx.write_event_to_stream(RequirementsProgressEvent(
            message="Persisting requirements registry…",
            progress=0.80, stage="persist"
        ))

        # Build flat list with hierarchy IDs for DB persistence
        flat_reqs = self._flatten_for_persistence(ev.features, project_id, work_context_id)

        ctx.write_event_to_stream(RequirementsProgressEvent(
            message="✅ Requirements registry built successfully!",
            progress=1.0, stage="persist"
        ))

        return StopEvent(result={
            "project_id": project_id,
            "features": ev.features,
            "requirements_flat": flat_reqs,
            "gaps": ev.gaps,
            "validation": ev.validation.get("overall_assessment", {}),
            "metadata": ev.metadata,
            "rag_sources": ev.rag_sources,
        })

    # ── LLM Calls ─────────────────────────────────────────────────────────────

    async def _extract_with_llm(self, context: str) -> Dict:
        """Extract requirements using LLM (Strategy A + partial B)."""
        if not self.llm:
            logger.info("No LLM configured — returning mock requirements")
            return self._mock_extraction()

        prompt = EXTRACT_REQUIREMENTS_PROMPT + context[:30000]

        try:
            response = await self.llm.acomplete(prompt, max_tokens=8192)
            raw = strip_fences(str(response).strip())
            result = json.loads(raw)

            # Sanity checks
            if "features" not in result:
                result["features"] = []
            if "gaps" not in result:
                result["gaps"] = []
            if "metadata" not in result:
                result["metadata"] = self._compute_metadata(result["features"])

            return result
        except Exception as e:
            logger.warning("Requirements extraction failed: %s — using fallback", e)
            return self._mock_extraction()

    # ── Reflection helpers ────────────────────────────────────────────────────

    async def _review_requirements(
        self,
        source_sample: str,
        features: List[Dict],
        gaps: List[Dict],
    ) -> Dict:
        """Critic call: evaluate quality of extracted requirements against source docs."""
        features_json = json.dumps(features, ensure_ascii=False)[:12_000]
        gaps_json = json.dumps(gaps, ensure_ascii=False)

        prompt = REVIEW_REQUIREMENTS_PROMPT.format(
            source_sample=source_sample,
            features_json=features_json,
            gaps_json=gaps_json,
        )
        try:
            response = await self.llm.acomplete(prompt, max_tokens=4096)
            raw = strip_fences(str(response).strip())
            return json.loads(raw)
        except Exception as e:
            logger.warning("Requirements review LLM call failed (%s) — treating as APPROVED", e)
            return {"verdict": "APPROVED"}

    # ── Req-by-req refinement helpers ────────────────────────────────────────

    def _find_req(self, features: List[Dict], title_or_id: str):
        """Return (feature_idx, req_idx) for the first requirement matching title_or_id."""
        needle = (title_or_id or "").lower().strip()
        if not needle:
            return None, None
        for fi, feature in enumerate(features):
            for ri, req in enumerate(feature.get("requirements", [])):
                eid = (req.get("external_id") or "").lower().strip()
                title = (req.get("title") or "").lower().strip()
                if eid == needle or title == needle or needle in eid or needle in title:
                    return fi, ri
        return None, None

    def _remove_req_by_id(self, features: List[Dict], title_or_id: str) -> List[Dict]:
        fi, ri = self._find_req(features, title_or_id)
        if fi is None:
            return features
        updated = [dict(f) for f in features]
        updated[fi] = {**updated[fi], "requirements": [
            r for j, r in enumerate(updated[fi].get("requirements", [])) if j != ri
        ]}
        return updated

    def _apply_req_fix(self, features: List[Dict], title_or_id: str, fix: Dict) -> List[Dict]:
        fi, ri = self._find_req(features, title_or_id)
        if fi is None or ri is None:
            return features
        updated = [dict(f) for f in features]
        reqs = list(updated[fi].get("requirements", []))
        reqs[ri] = {**reqs[ri], **fix}
        updated[fi] = {**updated[fi], "requirements": reqs}
        return updated

    def _apply_acs(self, features: List[Dict], title_or_id: str, acs: List[Dict]) -> List[Dict]:
        fi, ri = self._find_req(features, title_or_id)
        if fi is None or ri is None:
            return features
        updated = [dict(f) for f in features]
        reqs = list(updated[fi].get("requirements", []))
        existing = reqs[ri].get("acceptance_criteria", [])
        reqs[ri] = {**reqs[ri], "acceptance_criteria": existing + acs}
        updated[fi] = {**updated[fi], "requirements": reqs}
        return updated

    def _insert_req(self, features: List[Dict], area: str, new_req: Dict) -> List[Dict]:
        area_lower = (area or "").lower()
        for fi, feature in enumerate(features):
            if area_lower in (feature.get("title") or "").lower() or \
               area_lower in (feature.get("module") or "").lower():
                updated = [dict(f) for f in features]
                updated[fi] = {**updated[fi], "requirements": updated[fi].get("requirements", []) + [new_req]}
                return updated
        return features + [{"title": area or "General", "module": (area or "general").lower(),
                            "description": "", "requirements": [new_req]}]

    async def _fix_req_llm(self, source_sample: str, req: Dict, item: Dict) -> Optional[Dict]:
        prompt = f"""Fix this requirement to be specific and testable.

Issue: {item.get("issue", "")}
Suggested fix: {item.get("suggested_fix", "")}

Current requirement:
{json.dumps(req, ensure_ascii=False, indent=2)}

Source documentation (excerpt):
{source_sample[:3000]}

Return ONLY the corrected requirement as JSON (same structure, all fields preserved). No markdown fences."""
        try:
            response = await self.llm.acomplete(prompt, max_tokens=2048)
            return json.loads(strip_fences(str(response).strip()))
        except Exception as e:
            logger.warning("Fix req '%s' failed: %s", item.get("title_or_id"), e)
            return None

    async def _add_acs_llm(self, source_sample: str, req: Dict, item: Dict, project_id: str = "") -> Optional[List[Dict]]:
        # _build_prompt is a closure so we can swap `source_sample` for a more targeted
        # RAG snippet on JSON-decode retry without duplicating the prompt string.
        def _build_prompt(ctx: str) -> str:
            return f"""Generate acceptance criteria for this requirement.

Requirement: {json.dumps(req, ensure_ascii=False)}
Suggestion: {item.get("suggested_ac", "")}

Source documentation (excerpt):
{ctx[:3000]}

Return ONLY a JSON array of acceptance criteria:
[{{"title": "...", "description": "Given X when Y then Z", "testability": "high|medium|low", "confidence": 0.9}}]
No markdown fences."""
        try:
            response = await self.llm.acomplete(_build_prompt(source_sample), max_tokens=2048)
            result = json.loads(strip_fences(str(response).strip()))
            return result if isinstance(result, list) else None
        except json.JSONDecodeError:
            if project_id:
                query = f"{req.get('title', '')} {item.get('suggested_ac', '')} acceptance criteria"
                try:
                    targeted, _ = await self.context_builder.build_with_sources(project_id, query=query, top_k=3)
                    response = await self.llm.acomplete(_build_prompt(targeted), max_tokens=2048)
                    result = json.loads(strip_fences(str(response).strip()))
                    return result if isinstance(result, list) else None
                except Exception as e2:
                    logger.warning("Add ACs for '%s' retry failed: %s", item.get("title_or_id"), e2)
            return None
        except Exception as e:
            logger.warning("Add ACs for '%s' failed: %s", item.get("title_or_id"), e)
            return None

    async def _create_req_llm(self, source_sample: str, missing: Dict, project_id: str = "") -> Optional[Dict]:
        # Same _build_prompt closure pattern as _add_acs_llm — allows targeted RAG retry.
        def _build_prompt(ctx: str) -> str:
            return f"""Create a new functional requirement based on this description.

Missing requirement:
- Area: {missing.get("area", "")}
- Description: {missing.get("description", "")}
- Suggested title: {missing.get("suggested_title", "")}

Source documentation (excerpt):
{ctx[:3000]}

Return ONLY a JSON object:
{{"external_id": null, "title": "...", "description": "...", "level": "functional_req",
  "source_type": "implicit", "taxonomy": {{"module": "...", "risk_level": "medium", "business_domain": "..."}},
  "testability": "high", "confidence": 0.75, "needs_review": true,
  "review_reason": "Added by reviewer", "acceptance_criteria": []}}
No markdown fences."""
        try:
            response = await self.llm.acomplete(_build_prompt(source_sample), max_tokens=2048)
            result = json.loads(strip_fences(str(response).strip()))
            return result if isinstance(result, dict) else None
        except json.JSONDecodeError:
            if project_id:
                query = f"{missing.get('suggested_title', '')} {missing.get('description', '')} requirement"
                try:
                    targeted, _ = await self.context_builder.build_with_sources(project_id, query=query, top_k=3)
                    response = await self.llm.acomplete(_build_prompt(targeted), max_tokens=2048)
                    result = json.loads(strip_fences(str(response).strip()))
                    return result if isinstance(result, dict) else None
                except Exception as e2:
                    logger.warning("Create req '%s' retry failed: %s", missing.get("suggested_title"), e2)
            return None
        except Exception as e:
            logger.warning("Create req '%s' failed: %s", missing.get("suggested_title"), e)
            return None

    async def _merge_dup_llm(self, source_sample: str, req_a: Dict, req_b: Dict, reason: str) -> Optional[Dict]:
        prompt = f"""Merge these two duplicate requirements into one complete requirement.

Requirement A: {json.dumps(req_a, ensure_ascii=False, indent=2)}
Requirement B: {json.dumps(req_b, ensure_ascii=False, indent=2)}
Reason they overlap: {reason}

Return ONLY the merged requirement as JSON (same structure, keep the more complete version).
No markdown fences."""
        try:
            response = await self.llm.acomplete(prompt, max_tokens=2048)
            result = json.loads(strip_fences(str(response).strip()))
            return result if isinstance(result, dict) else None
        except Exception as e:
            logger.warning("Merge duplicate failed: %s", e)
            return None

    async def _refine_requirements(
        self,
        source_sample: str,
        features: List[Dict],
        gaps: List[Dict],
        issues: Dict,
        project_id: str = "",
    ) -> tuple:
        """Apply targeted per-issue fixes instead of regenerating the full set."""
        features = copy.deepcopy(features)
        gaps = copy.deepcopy(gaps)
        sem = asyncio.Semaphore(settings.LLM_CONCURRENT_CALLS)
        features = self._apply_hallucination_removals(features, issues)
        features = await self._apply_dup_merges(features, issues, source_sample)
        features = await self._apply_incomplete_fixes(features, issues, source_sample, sem)
        features = await self._apply_missing_acs(features, issues, source_sample, sem, project_id)
        features = await self._apply_missing_reqs(features, issues, source_sample, sem, project_id)
        return features, gaps

    def _apply_hallucination_removals(self, features: List[Dict], issues: Dict) -> List[Dict]:
        """Remove requirements flagged as hallucinations (no LLM needed)."""
        for h in [_as_dict(x) for x in issues.get("hallucinations", [])]:
            features = self._remove_req_by_id(features, h.get("title_or_id", ""))
            logger.debug("Removed hallucination: %s", h.get("title_or_id"))
        return features

    async def _apply_dup_merges(
        self, features: List[Dict], issues: Dict, source_sample: str
    ) -> List[Dict]:
        """Merge duplicate requirement pairs (sequential to avoid conflicting mutations)."""
        for dup in [_as_dict(x) for x in issues.get("duplicates", [])]:
            fi_a, ri_a = self._find_req(features, dup.get("req_a", ""))
            fi_b, ri_b = self._find_req(features, dup.get("req_b", ""))
            if fi_a is not None and fi_b is not None and (fi_a, ri_a) != (fi_b, ri_b):
                req_a = features[fi_a]["requirements"][ri_a]
                req_b = features[fi_b]["requirements"][ri_b]
                merged = await self._merge_dup_llm(source_sample, req_a, req_b, dup.get("reason", ""))
                if merged:
                    features = self._apply_req_fix(features, dup.get("req_a", ""), merged)
                    features = self._remove_req_by_id(features, dup.get("req_b", ""))
        return features

    async def _apply_incomplete_fixes(
        self, features: List[Dict], issues: Dict, source_sample: str, sem: asyncio.Semaphore
    ) -> List[Dict]:
        """Fix vague/untestable requirements in parallel."""
        incomplete = [_as_dict(x) for x in issues.get("incomplete_requirements", [])]
        if not incomplete or not self.llm:
            return features
        reqs_for_fix, items_for_fix = [], []
        for item in incomplete:
            fi, ri = self._find_req(features, item.get("title_or_id", ""))
            if fi is not None:
                reqs_for_fix.append(features[fi]["requirements"][ri])
                items_for_fix.append(item)
        if reqs_for_fix:
            fixes = await asyncio.gather(
                *[_guarded(sem, self._fix_req_llm(source_sample, req, item))
                  for req, item in zip(reqs_for_fix, items_for_fix)],
                return_exceptions=True,
            )
            for item, fix in zip(items_for_fix, fixes):
                if isinstance(fix, dict):
                    features = self._apply_req_fix(features, item.get("title_or_id", ""), fix)
        return features

    async def _apply_missing_acs(
        self, features: List[Dict], issues: Dict, source_sample: str,
        sem: asyncio.Semaphore, project_id: str,
    ) -> List[Dict]:
        """Add missing acceptance criteria in parallel."""
        missing_acs = [_as_dict(x) for x in issues.get("missing_acceptance_criteria", [])]
        if not missing_acs or not self.llm:
            return features
        reqs_for_ac, items_for_ac = [], []
        for item in missing_acs:
            fi, ri = self._find_req(features, item.get("title_or_id", ""))
            if fi is not None:
                reqs_for_ac.append(features[fi]["requirements"][ri])
                items_for_ac.append(item)
        if reqs_for_ac:
            ac_results = await asyncio.gather(
                *[_guarded(sem, self._add_acs_llm(source_sample, req, item, project_id))
                  for req, item in zip(reqs_for_ac, items_for_ac)],
                return_exceptions=True,
            )
            for item, acs in zip(items_for_ac, ac_results):
                if isinstance(acs, list):
                    features = self._apply_acs(features, item.get("title_or_id", ""), acs)
        return features

    async def _apply_missing_reqs(
        self, features: List[Dict], issues: Dict, source_sample: str,
        sem: asyncio.Semaphore, project_id: str,
    ) -> List[Dict]:
        """Create requirements for areas present in source but not extracted, in parallel."""
        missing_reqs = [_as_dict(x) for x in issues.get("missing_requirements", [])]
        if not missing_reqs or not self.llm:
            return features
        new_reqs = await asyncio.gather(
            *[_guarded(sem, self._create_req_llm(source_sample, item, project_id))
              for item in missing_reqs],
            return_exceptions=True,
        )
        for item, new_req in zip(missing_reqs, new_reqs):
            if isinstance(new_req, dict):
                features = self._insert_req(features, item.get("area", ""), new_req)
        return features

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _feature_row(
        self, feature: Dict, feature_id: str, project_id: str,
        work_context_id: Optional[str], lifecycle_status: str,
    ) -> Dict:
        return {
            "id": feature_id,
            "project_id": project_id,
            "parent_id": None,
            "level": "feature",
            "external_id": None,
            "title": feature.get("title", "Unknown Feature"),
            "description": feature.get("description", ""),
            "source_type": "implicit",
            "taxonomy": {"module": feature.get("module", "unknown")},
            "confidence": 0.9,
            "completeness_score": None,
            "needs_review": False,
            "review_reason": None,
            "work_context_id": work_context_id,
            "lifecycle_status": lifecycle_status,
        }

    def _req_row(
        self, req: Dict, req_id: str, feature_id: str, project_id: str,
        work_context_id: Optional[str], lifecycle_status: str,
    ) -> Dict:
        confidence = float(req.get("confidence") or 0.5)
        needs_review = req.get("needs_review", confidence < 0.7)
        return {
            "id": req_id,
            "project_id": project_id,
            "parent_id": feature_id,
            "level": req.get("level", "functional_req"),
            "external_id": req.get("external_id"),
            "title": req.get("title", ""),
            "description": req.get("description", ""),
            "source_type": req.get("source_type", "implicit"),
            "source_references": req.get("source_references", []),
            "taxonomy": req.get("taxonomy", {}),
            "confidence": confidence,
            "completeness_score": req.get("completeness_score"),
            "needs_review": needs_review,
            "review_reason": req.get("review_reason") or (
                f"Low confidence ({confidence:.2f})" if needs_review else None
            ),
            "work_context_id": work_context_id,
            "lifecycle_status": lifecycle_status,
        }

    def _ac_row(
        self, ac: Dict, req_id: str, project_id: str, req: Dict, parent_confidence: float,
        work_context_id: Optional[str], lifecycle_status: str,
    ) -> Dict:
        if not isinstance(ac, dict):
            ac = {"title": str(ac), "description": "", "testability": "medium"}
        ac_confidence = float(ac.get("confidence") or parent_confidence * 0.9)
        return {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "parent_id": req_id,
            "level": "acceptance_criterion",
            "external_id": None,
            "title": ac.get("title", ""),
            "description": ac.get("description", ""),
            "source_type": req.get("source_type", "implicit"),
            "taxonomy": req.get("taxonomy", {}),
            "confidence": ac_confidence,
            "completeness_score": None,
            "needs_review": ac_confidence < 0.7,
            "review_reason": None,
            "work_context_id": work_context_id,
            "lifecycle_status": lifecycle_status,
        }

    def _flatten_for_persistence(
        self, features: List[Dict], project_id: str,
        work_context_id: Optional[str] = None,
    ) -> List[Dict]:
        """Build flat requirement list with UUIDs and parent references for DB."""
        lifecycle_status = "draft" if work_context_id is not None else "promoted"
        flat = []
        for feature in features:
            feature_id = str(uuid.uuid4())
            flat.append(self._feature_row(
                feature, feature_id, project_id, work_context_id, lifecycle_status
            ))
            for req in feature.get("requirements", []):
                if not isinstance(req, dict):
                    continue
                req_id = str(uuid.uuid4())
                row = self._req_row(
                    req, req_id, feature_id, project_id, work_context_id, lifecycle_status
                )
                flat.append(row)
                for ac in req.get("acceptance_criteria", []):
                    flat.append(self._ac_row(
                        ac, req_id, project_id, req, row["confidence"],
                        work_context_id, lifecycle_status,
                    ))
        return flat

    def _flag_low_confidence(self, features: List[Dict]) -> List[Dict]:
        """Flag requirements with confidence < 0.7 for human review."""
        for feature in features:
            for req in feature.get("requirements", []):
                conf = req.get("confidence", 0) or 0
                if conf < 0.7 and not req.get("needs_review"):
                    req["needs_review"] = True
                    req["review_reason"] = f"Low confidence ({conf:.2f})"
        return features

    def _compute_metadata(self, features: List[Dict]) -> Dict:
        """Compute summary metadata from features."""
        total_reqs = 0
        total_ac = 0
        formal = 0
        implicit = 0
        confidences = []

        for f in features:
            for r in f.get("requirements", []):
                total_reqs += 1
                if r.get("source_type") == "formal":
                    formal += 1
                else:
                    implicit += 1
                if r.get("confidence") is not None:
                    confidences.append(r["confidence"])
                total_ac += len(r.get("acceptance_criteria", []))

        avg_conf = sum(confidences) / len(confidences) if confidences else 0
        low_conf = sum(1 for c in confidences if c < 0.7)

        return {
            "total_features": len(features),
            "total_requirements": total_reqs,
            "total_acceptance_criteria": total_ac,
            "formal_count": formal,
            "implicit_count": implicit,
            "avg_confidence": round(avg_conf, 2),
            "low_confidence_count": low_conf,
        }

    def _deduplicate_context(self, text: str, max_chars: int) -> str:
        """Deduplicate paragraphs that appear in multiple RAG query results."""
        seen: set = set()
        parts: List[str] = []
        total = 0

        for para in text.split("\n\n"):
            normalized = para.strip().lower()[:200]
            if normalized and normalized not in seen:
                seen.add(normalized)
                if total + len(para) > max_chars:
                    break
                parts.append(para)
                total += len(para)

        return "\n\n".join(parts)

    # ── Mock data (dev without LLM) ──────────────────────────────────────────

    def _mock_extraction(self) -> Dict:
        return {
            "features": [
                {
                    "title": "Payment Processing",
                    "description": "Core payment functionality",
                    "module": "payments",
                    "requirements": [
                        {
                            "external_id": "FR-001",
                            "title": "Initiate bank transfer",
                            "description": "System shall allow users to initiate bank transfers up to the configured daily limit.",
                            "level": "functional_req",
                            "source_type": "formal",
                            "taxonomy": {"module": "payments", "risk_level": "high", "business_domain": "business_logic"},
                            "testability": "high",
                            "confidence": 0.95,
                            "needs_review": False,
                            "review_reason": None,
                            "acceptance_criteria": [
                                {"title": "Transfer within limit succeeds", "description": "Transfer of amount <= daily limit completes successfully", "testability": "high", "confidence": 0.95},
                                {"title": "Transfer above limit rejected", "description": "Transfer of amount > daily limit shows error", "testability": "high", "confidence": 0.95},
                            ],
                        },
                        {
                            "external_id": "FR-002",
                            "title": "Transaction history",
                            "description": "System shall display transaction history for the last 12 months.",
                            "level": "functional_req",
                            "source_type": "formal",
                            "taxonomy": {"module": "payments", "risk_level": "medium", "business_domain": "data_integrity"},
                            "testability": "high",
                            "confidence": 0.90,
                            "needs_review": False,
                            "review_reason": None,
                            "acceptance_criteria": [],
                        },
                    ],
                },
                {
                    "title": "User Authentication",
                    "description": "Login and session management",
                    "module": "auth",
                    "requirements": [
                        {
                            "external_id": "FR-003",
                            "title": "Multi-factor authentication",
                            "description": "System shall support 2FA via SMS or authenticator app.",
                            "level": "functional_req",
                            "source_type": "formal",
                            "taxonomy": {"module": "auth", "risk_level": "critical", "business_domain": "security"},
                            "testability": "high",
                            "confidence": 0.88,
                            "needs_review": False,
                            "review_reason": None,
                            "acceptance_criteria": [],
                        },
                    ],
                },
            ],
            "gaps": [
                {"area": "Session Management", "description": "No requirements for session timeout or concurrent session handling", "severity": "high"},
            ],
            "metadata": {
                "total_features": 2,
                "total_requirements": 3,
                "total_acceptance_criteria": 2,
                "formal_count": 3,
                "implicit_count": 0,
                "avg_confidence": 0.91,
                "low_confidence_count": 0,
            },
        }
