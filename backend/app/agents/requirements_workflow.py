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

import json
import logging
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

from app.rag.context_builder import ContextBuilder

logger = logging.getLogger("ai_buddy.requirements")


def _strip_fences(text: str) -> str:
    """Remove markdown code fences and find the first valid JSON value."""
    import re
    text = re.sub(r"^```[a-z]*\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)
    for i, ch in enumerate(text):
        if ch in ("{", "["):
            return text[i:]
    return text


# ─── Prompts ──────────────────────────────────────────────────────────────────

EXTRACT_REQUIREMENTS_PROMPT = """You are a senior QA architect performing requirements analysis on project documentation.

Your task: Extract ALL testable requirements from the documentation below.
Build a hierarchical structure: Features → Functional Requirements → Acceptance Criteria.

Rules:
1. Extract EVERY testable requirement — explicit (FR-001, REQ-*, SHALL/MUST) AND implicit (described behaviors, business rules, constraints).
2. For each requirement, determine:
   - external_id: the original ID if one exists (e.g. "FR-001"), or null if implicit
   - title: concise name (max 80 chars)
   - description: full requirement text
   - level: "feature" | "functional_req" | "acceptance_criterion"
   - parent_feature: which feature this belongs to (use feature title)
   - source_type: "formal" if has an explicit ID, "implicit" if inferred from text
   - taxonomy: {module, risk_level, business_domain}
   - testability: "high" | "medium" | "low" — can this be directly tested?
   - confidence: 0.0–1.0 — how certain are you this is a real requirement?

3. Group requirements under features. If no features are explicit, infer them from domain areas.
4. Mark requirements with confidence < 0.7 as needs_review: true.
5. Identify GAPS: areas mentioned in the docs but without clear requirements.

Return ONLY valid JSON — no preamble, no markdown fences:
{
  "features": [
    {
      "title": "Feature name",
      "description": "Feature description",
      "module": "module_name",
      "requirements": [
        {
          "external_id": "FR-001" or null,
          "title": "Requirement title",
          "description": "Full requirement description",
          "level": "functional_req",
          "source_type": "formal" or "implicit",
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
            {
              "title": "AC title",
              "description": "When X then Y",
              "testability": "high",
              "confidence": 0.9
            }
          ]
        }
      ]
    }
  ],
  "gaps": [
    {
      "area": "Area name",
      "description": "What seems to be missing",
      "severity": "high|medium|low"
    }
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

VALIDATE_REQUIREMENTS_PROMPT = """You are a QA requirements reviewer. Review the extracted requirements below for quality and completeness.

For each requirement, check:
1. Is it testable? (has clear expected behavior)
2. Is it unambiguous? (single interpretation)
3. Is it complete? (sufficient detail to write test cases)
4. Are there duplicates or overlaps?
5. Are there obvious gaps — areas of the system not covered?

Return ONLY valid JSON:
{
  "validated_requirements": [
    {
      "external_id_or_title": "identifier",
      "is_valid": true,
      "issues": [],
      "adjusted_confidence": 0.85,
      "completeness_score": 0.8,
      "review_notes": "optional notes"
    }
  ],
  "duplicates": [
    {
      "req_a": "identifier",
      "req_b": "identifier",
      "reason": "why they overlap"
    }
  ],
  "additional_gaps": [
    {
      "area": "area name",
      "description": "what's missing",
      "severity": "high|medium|low"
    }
  ],
  "overall_assessment": {
    "completeness_rating": "high|medium|low",
    "testability_rating": "high|medium|low",
    "recommendation": "summary recommendation"
  }
}

Requirements to validate:
"""


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


class ValidatedRequirementsEvent(Event):
    """Emitted after validation pass."""
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

    # ── Step 1: Extract ──────────────────────────────────────────────────────

    @step
    async def extract(self, ctx: Context, ev: StartEvent) -> ExtractedRequirementsEvent:
        project_id: str = ev.get("project_id", "default")
        user_message: str = ev.get("user_message", "")

        await ctx.store.set("project_id", project_id)

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

        # Multiple RAG queries to get comprehensive coverage
        queries = [
            "functional requirements specifications features",
            "business rules constraints validations",
            "acceptance criteria user stories scenarios",
            "non-functional requirements performance security",
            f"{user_message} requirements" if user_message else "",
        ]
        queries = [q for q in queries if q.strip()]

        all_context_parts: List[str] = []
        all_sources: List[Dict] = []
        seen_filenames: set = set()

        for i, query in enumerate(queries):
            ctx.write_event_to_stream(RequirementsProgressEvent(
                message=f"Querying knowledge base ({i+1}/{len(queries)})…",
                progress=0.05 + 0.15 * ((i + 1) / len(queries)),
                stage="extract"
            ))
            context_text, sources = await self.context_builder.build_with_sources(
                project_id, query=query, top_k=8
            )
            all_context_parts.append(context_text)
            for s in sources:
                if s["filename"] not in seen_filenames:
                    seen_filenames.add(s["filename"])
                    all_sources.append(s)

        combined_context = "\n\n---\n\n".join(all_context_parts)
        # Deduplicate chunks that appear in multiple queries
        combined_context = self._deduplicate_context(combined_context, max_chars=60000)

        ctx.write_event_to_stream(RequirementsProgressEvent(
            message=f"Extracting requirements from {len(seen_filenames)} source document(s)…",
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

    # ── Step 2: Validate ─────────────────────────────────────────────────────

    @step
    async def validate(self, ctx: Context, ev: ExtractedRequirementsEvent) -> ValidatedRequirementsEvent:
        features = ev.raw_result.get("features", [])
        gaps = ev.raw_result.get("gaps", [])
        metadata = ev.raw_result.get("metadata", {})

        if not features:
            return ValidatedRequirementsEvent(
                features=features, gaps=gaps,
                validation={"overall_assessment": {
                    "completeness_rating": "low",
                    "testability_rating": "low",
                    "recommendation": "No requirements found. Run M1 Context Builder with project documentation first."
                }},
                metadata=metadata, rag_sources=ev.rag_sources,
            )

        ctx.write_event_to_stream(RequirementsProgressEvent(
            message="Validating extracted requirements…",
            progress=0.55, stage="validate"
        ))

        # Build flat list for validation
        flat_reqs = self._flatten_requirements(features)

        validation = await self._validate_with_llm(flat_reqs)

        # Apply validation results back to features
        features = self._apply_validation(features, validation)

        # Merge gaps from extraction + validation
        additional_gaps = validation.get("additional_gaps", [])
        all_gaps = gaps + additional_gaps

        # Recompute metadata after validation
        metadata = self._compute_metadata(features)

        n_review = sum(
            1 for f in features
            for r in f.get("requirements", [])
            if r.get("needs_review")
        )

        ctx.write_event_to_stream(RequirementsProgressEvent(
            message=f"✓ Validation complete — {n_review} requirement(s) flagged for review",
            progress=0.75, stage="validate"
        ))

        return ValidatedRequirementsEvent(
            features=features,
            gaps=all_gaps,
            validation=validation,
            metadata=metadata,
            rag_sources=ev.rag_sources,
        )

    # ── Step 3: Persist & Assemble ───────────────────────────────────────────

    @step
    async def persist(self, ctx: Context, ev: ValidatedRequirementsEvent) -> StopEvent:
        project_id = await ctx.store.get("project_id")

        ctx.write_event_to_stream(RequirementsProgressEvent(
            message="Persisting requirements registry…",
            progress=0.80, stage="persist"
        ))

        # Build flat list with hierarchy IDs for DB persistence
        flat_reqs = self._flatten_for_persistence(ev.features, project_id)

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

        prompt = EXTRACT_REQUIREMENTS_PROMPT + context[:60000]

        try:
            response = await self.llm.acomplete(prompt)
            raw = _strip_fences(str(response).strip())
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

    async def _validate_with_llm(self, flat_reqs: List[Dict]) -> Dict:
        """Validate extracted requirements using a second LLM pass."""
        if not self.llm:
            return {"validated_requirements": [], "duplicates": [],
                    "additional_gaps": [], "overall_assessment": {
                        "completeness_rating": "unknown",
                        "testability_rating": "unknown",
                        "recommendation": "Enable LLM for validation."
                    }}

        # Limit context size for validation
        reqs_summary = json.dumps(flat_reqs[:50], ensure_ascii=False, indent=1)
        prompt = VALIDATE_REQUIREMENTS_PROMPT + reqs_summary

        try:
            response = await self.llm.acomplete(prompt)
            raw = _strip_fences(str(response).strip())
            return json.loads(raw)
        except Exception as e:
            logger.warning("Requirements validation failed: %s", e)
            return {"validated_requirements": [], "duplicates": [],
                    "additional_gaps": [], "overall_assessment": {
                        "completeness_rating": "unknown",
                        "testability_rating": "unknown",
                        "recommendation": f"Validation error: {e}"
                    }}

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _flatten_requirements(self, features: List[Dict]) -> List[Dict]:
        """Flatten hierarchical features into a list for validation."""
        flat = []
        for feature in features:
            for req in feature.get("requirements", []):
                flat.append({
                    "external_id": req.get("external_id"),
                    "title": req.get("title", ""),
                    "description": req.get("description", ""),
                    "level": req.get("level", "functional_req"),
                    "source_type": req.get("source_type", "implicit"),
                    "feature": feature.get("title", ""),
                    "confidence": req.get("confidence", 0.5),
                })
        return flat

    def _flatten_for_persistence(self, features: List[Dict], project_id: str) -> List[Dict]:
        """Build flat requirement list with UUIDs and parent references for DB."""
        import uuid
        flat = []

        for feature in features:
            feature_id = str(uuid.uuid4())
            flat.append({
                "id": feature_id,
                "project_id": project_id,
                "parent_id": None,
                "level": "feature",
                "external_id": None,
                "title": feature.get("title", "Unknown Feature"),
                "description": feature.get("description", ""),
                "source_type": "implicit",
                "taxonomy": json.dumps({"module": feature.get("module", "unknown")}),
                "confidence": 0.9,
                "completeness_score": None,
                "needs_review": False,
                "review_reason": None,
            })

            for req in feature.get("requirements", []):
                req_id = str(uuid.uuid4())
                confidence = req.get("confidence", 0.5)
                needs_review = req.get("needs_review", confidence < 0.7)

                flat.append({
                    "id": req_id,
                    "project_id": project_id,
                    "parent_id": feature_id,
                    "level": req.get("level", "functional_req"),
                    "external_id": req.get("external_id"),
                    "title": req.get("title", ""),
                    "description": req.get("description", ""),
                    "source_type": req.get("source_type", "implicit"),
                    "taxonomy": json.dumps(req.get("taxonomy", {})),
                    "confidence": confidence,
                    "completeness_score": req.get("completeness_score"),
                    "needs_review": needs_review,
                    "review_reason": req.get("review_reason") or (
                        f"Low confidence ({confidence:.2f})" if needs_review else None
                    ),
                })

                for ac in req.get("acceptance_criteria", []):
                    ac_confidence = ac.get("confidence", confidence * 0.9)
                    flat.append({
                        "id": str(uuid.uuid4()),
                        "project_id": project_id,
                        "parent_id": req_id,
                        "level": "acceptance_criterion",
                        "external_id": None,
                        "title": ac.get("title", ""),
                        "description": ac.get("description", ""),
                        "source_type": req.get("source_type", "implicit"),
                        "taxonomy": json.dumps(req.get("taxonomy", {})),
                        "confidence": ac_confidence,
                        "completeness_score": None,
                        "needs_review": ac_confidence < 0.7,
                        "review_reason": None,
                    })

        return flat

    def _apply_validation(self, features: List[Dict], validation: Dict) -> List[Dict]:
        """Apply validation results back to the feature tree."""
        validated = {
            v.get("external_id_or_title", ""): v
            for v in validation.get("validated_requirements", [])
        }

        for feature in features:
            for req in feature.get("requirements", []):
                key = req.get("external_id") or req.get("title", "")
                v = validated.get(key)
                if v:
                    if v.get("adjusted_confidence") is not None:
                        req["confidence"] = v["adjusted_confidence"]
                    if v.get("completeness_score") is not None:
                        req["completeness_score"] = v["completeness_score"]
                    if v.get("issues"):
                        req["needs_review"] = True
                        req["review_reason"] = "; ".join(v["issues"])
                    elif not v.get("is_valid", True):
                        req["needs_review"] = True
                        req["review_reason"] = v.get("review_notes", "Flagged during validation")

                # Auto-flag low confidence
                if req.get("confidence", 0) < 0.7 and not req.get("needs_review"):
                    req["needs_review"] = True
                    req["review_reason"] = f"Low confidence ({req['confidence']:.2f})"

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
