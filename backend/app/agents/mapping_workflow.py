"""
Faza 5+6: Semantic Mapping & Coverage Scoring Workflow
=======================================================
Pipeline:
  Start → LoadData → CoarseMatch → FineMatch → Score → Assemble → Stop

Connects Faza 2 (Requirements Registry) with parsed test cases.
Produces:
  - RequirementTCMapping rows with confidence per pair
  - CoverageScore rows with multi-dimensional scoring per requirement

Prerequisites:
  - Faza 2 run (requirements in DB)
  - Test files uploaded to project (M2 file upload)

NOTE: Uses LlamaIndex Workflow Context API v0.14+
"""

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from llama_index.core.workflow import (
    Context,
    Event,
    StartEvent,
    StopEvent,
    Workflow,
    step,
)

from app.core.config import settings
from app.db.engine import AsyncSessionLocal
from app.db.models import ProjectFile
from app.db.requirements_models import Requirement
from app.rag.context_builder import ContextBuilder
from app.utils.json_utils import strip_fences
from app.parsers.test_case_parser import build_tc_text, parse_test_file
from sqlalchemy import select

logger = logging.getLogger("ai_buddy.mapping")

# ─── Module-level helpers ────────────────────────────────────────────────────

def _total_from_components(score: Dict) -> float:
    """Compute total coverage score from individual components (capped 0–100)."""
    return min(100, max(0, round(
        score["base_coverage"]
        + score["depth_coverage"]
        + score["quality_weight"]
        + score["confidence_penalty"]
        + score["crossref_bonus"],
        1,
    )))


# ─── Constants ────────────────────────────────────────────────────────────────

_MATCH_PATTERN_CONFIDENCE = 0.95
_MATCH_CONFIDENT_THRESHOLD = 0.78
_MATCH_AMBIGUOUS_THRESHOLD = 0.65
_LLM_FINE_MATCH_BATCH_SIZE = 10

# Scoring weight caps (must match CLAUDE.md scoring model)
_SCORE_BASE_MAX = 40.0
_SCORE_DEPTH_MAX = 30.0
_SCORE_QUALITY_MAX = 20.0
_SCORE_PENALTY_MAX = -10.0
_SCORE_CROSSREF_MAX = 10.0


# ─── Prompts ──────────────────────────────────────────────────────────────────

FINE_MATCH_PROMPT = """You are a senior QA analyst matching test cases to requirements.

For each (requirement, test case) pair below, determine:
1. Does this test case actually verify this requirement? (COVERS / PARTIAL / NO)
2. Which aspects does it cover? (happy_path, negative, boundary, integration, edge_case, performance, security)
3. What aspects of the requirement are NOT covered by this test case?

Return ONLY valid JSON — no preamble, no markdown fences:
[
  {{
    "pair_id": "pair_0",
    "verdict": "COVERS|PARTIAL|NO",
    "confidence": 0.85,
    "aspects_covered": ["happy_path", "negative"],
    "aspects_missing": ["boundary", "edge_case"],
    "reason": "TC tests the main flow and error case, but not boundary values"
  }}
]

Pairs to evaluate:
{pairs}
"""

COVERAGE_ASPECTS_PROMPT = """You are a QA coverage analyst. Given a requirement and ALL its matched test cases,
assess the overall coverage depth.

Requirement:
  ID: {req_id}
  Title: {req_title}
  Description: {req_desc}

Matched test cases:
{tc_list}

Evaluate which testing dimensions are covered and which are missing.
Return ONLY valid JSON:
{{
  "aspects_present": ["happy_path", "negative", ...],
  "aspects_missing": ["boundary", "edge_case", ...],
  "depth_rating": "high|medium|low",
  "recommendation": "one sentence about what tests to add"
}}
"""


# ─── Events ──────────────────────────────────────────────────────────────────

class MappingProgressEvent(Event):
    message: str
    progress: float   # 0.0–1.0
    stage: str        # "load" | "coarse" | "fine" | "score" | "assemble"


class DataLoadedEvent(Event):
    test_cases: List[Dict]
    source_files: List[str]


class CoarseMatchedEvent(Event):
    """After embedding-based coarse matching."""
    matches: List[Dict]        # high-confidence matches (auto-accept)
    ambiguous: List[Dict]      # need LLM fine matching (0.4–0.8 similarity)
    test_cases: List[Dict]


class FineMatchedEvent(Event):
    """After LLM-confirmed fine matching."""
    all_mappings: List[Dict]   # final mappings with confidence + aspects


class ScoredEvent(Event):
    """After multi-dimensional scoring."""
    scores: List[Dict]         # per-requirement CoverageScore data
    mappings: List[Dict]


# ─── Workflow ─────────────────────────────────────────────────────────────────

class MappingWorkflow(Workflow):
    """
    Faza 5+6 pipeline.

    Returns:
    {
      "project_id": str,
      "mappings": [...],
      "scores": [...],
      "summary": {coverage_pct, avg_score, ...},
      "review_needed": [...]
    }
    """

    def __init__(self, llm=None, **kwargs):
        super().__init__(**kwargs)
        self.llm = llm
        self.context_builder = ContextBuilder()
        self._embed_model = self.context_builder._embed_model

    # ── Step 1: Load Data ────────────────────────────────────────────────────

    @step
    async def load_data(self, ctx: Context, ev: StartEvent) -> DataLoadedEvent:
        project_id: str = ev.get("project_id", "default")
        file_paths: List[str] = ev.get("file_paths", [])

        await ctx.store.set("project_id", project_id)

        ctx.write_event_to_stream(MappingProgressEvent(
            message="Loading requirements from registry…",
            progress=0.05, stage="load"
        ))

        # Load requirements from Faza 2 registry
        requirements = await self._load_requirements(project_id)
        await ctx.store.set("requirements", requirements)
        if not requirements:
            ctx.write_event_to_stream(MappingProgressEvent(
                message="⚠ No requirements found — run Faza 2 (Extract Requirements) first",
                progress=0.1, stage="load"
            ))
            return DataLoadedEvent(test_cases=[], source_files=[])

        ctx.write_event_to_stream(MappingProgressEvent(
            message=f"✓ Loaded {len(requirements)} requirements",
            progress=0.10, stage="load"
        ))

        # Load and parse test cases from files
        if not file_paths:
            file_paths = await self._auto_load_files(project_id)

        ctx.write_event_to_stream(MappingProgressEvent(
            message=f"Parsing {len(file_paths)} test file(s)…",
            progress=0.12, stage="load"
        ))

        test_cases = []
        for path in file_paths:
            cases = await parse_test_file(path)
            source = Path(path).name
            for tc in cases:
                tc["_source_file"] = source
                tc["_identifier"] = tc.get("name") or tc.get("title") or tc.get("test_id") or f"TC-{len(test_cases)}"
            test_cases.extend(cases)

        ctx.write_event_to_stream(MappingProgressEvent(
            message=f"✓ Loaded {len(test_cases)} test cases from {len(file_paths)} file(s)",
            progress=0.18, stage="load"
        ))

        return DataLoadedEvent(
            test_cases=test_cases,
            source_files=file_paths,
        )

    # ── Step 2: Coarse Matching ──────────────────────────────────────────────

    @step
    async def coarse_match(self, ctx: Context, ev: DataLoadedEvent) -> CoarseMatchedEvent:
        reqs: List[Dict] = await ctx.store.get("requirements")
        cases = ev.test_cases

        if not reqs or not cases:
            return CoarseMatchedEvent(
                matches=[], ambiguous=[], test_cases=cases
            )

        ctx.write_event_to_stream(MappingProgressEvent(
            message="Embedding requirements and test cases…",
            progress=0.20, stage="coarse"
        ))

        # Step A: Pattern matching (explicit ID references)
        pattern_matches = self._pattern_match(reqs, cases)
        pattern_req_ids = {m["requirement_id"] for m in pattern_matches}

        ctx.write_event_to_stream(MappingProgressEvent(
            message=f"✓ Pattern matching: {len(pattern_matches)} direct ID references found",
            progress=0.28, stage="coarse"
        ))

        # Step B: Embedding similarity for remaining requirements
        unmatched_reqs = [r for r in reqs if r["id"] not in pattern_req_ids]

        if unmatched_reqs:
            ctx.write_event_to_stream(MappingProgressEvent(
                message=f"Computing semantic similarity for {len(unmatched_reqs)} remaining requirements…",
                progress=0.30, stage="coarse"
            ))

            req_embeddings = await self._embed_items(
                [self._req_to_text(r) for r in unmatched_reqs]
            )
            tc_embeddings = await self._embed_items(
                [build_tc_text(tc) or "" for tc in cases]
            )

            embedding_matches, embedding_ambiguous = self._similarity_match(
                unmatched_reqs, req_embeddings, cases, tc_embeddings
            )
        else:
            embedding_matches, embedding_ambiguous = [], []

        all_matches = pattern_matches + embedding_matches

        ctx.write_event_to_stream(MappingProgressEvent(
            message=f"✓ Coarse matching: {len(all_matches)} confident, {len(embedding_ambiguous)} ambiguous",
            progress=0.45, stage="coarse"
        ))

        return CoarseMatchedEvent(
            matches=all_matches,
            ambiguous=embedding_ambiguous,
            test_cases=cases,
        )

    # ── Step 3: Fine Matching (LLM) ─────────────────────────────────────────

    @step
    async def fine_match(self, ctx: Context, ev: CoarseMatchedEvent) -> FineMatchedEvent:
        reqs: List[Dict] = await ctx.store.get("requirements")
        confirmed = list(ev.matches)
        ambiguous = ev.ambiguous

        if not ambiguous or not self.llm:
            if ambiguous and not self.llm:
                # No LLM — accept ambiguous pairs with reduced confidence
                for m in ambiguous:
                    m["mapping_confidence"] = max(0.4, m.get("mapping_confidence", 0.5) - 0.1)
                    m["mapping_method"] = "embedding"
                confirmed.extend(ambiguous)
            return FineMatchedEvent(all_mappings=confirmed)

        ctx.write_event_to_stream(MappingProgressEvent(
            message=f"LLM evaluating {len(ambiguous)} ambiguous mapping(s)…",
            progress=0.50, stage="fine"
        ))

        for i in range(0, len(ambiguous), _LLM_FINE_MATCH_BATCH_SIZE):
            batch = ambiguous[i:i + _LLM_FINE_MATCH_BATCH_SIZE]
            results = await self._llm_fine_match(batch, reqs)

            for pair, result in zip(batch, results):
                verdict = result.get("verdict", "NO")
                if verdict in ("COVERS", "PARTIAL"):
                    pair["mapping_confidence"] = result.get("confidence", 0.7)
                    pair["mapping_method"] = "llm"
                    pair["coverage_aspects"] = result.get("aspects_covered", [])
                    pair["aspects_missing"] = result.get("aspects_missing", [])
                    pair["llm_reason"] = result.get("reason", "")
                    confirmed.append(pair)
                # NO verdict → pair is dropped (not a real mapping)

            progress = 0.50 + 0.20 * ((i + _LLM_FINE_MATCH_BATCH_SIZE) / max(len(ambiguous), 1))
            ctx.write_event_to_stream(MappingProgressEvent(
                message=f"LLM evaluated {min(i + _LLM_FINE_MATCH_BATCH_SIZE, len(ambiguous))}/{len(ambiguous)} pairs…",
                progress=min(progress, 0.70), stage="fine"
            ))

        ctx.write_event_to_stream(MappingProgressEvent(
            message=f"✓ Fine matching complete: {len(confirmed)} total mappings",
            progress=0.72, stage="fine"
        ))

        return FineMatchedEvent(all_mappings=confirmed)

    # ── Step 4: Coverage Scoring ─────────────────────────────────────────────

    @step
    async def score(self, ctx: Context, ev: FineMatchedEvent) -> ScoredEvent:
        reqs: List[Dict] = await ctx.store.get("requirements")
        mappings = ev.all_mappings

        if not reqs:
            return ScoredEvent(scores=[], mappings=mappings)

        ctx.write_event_to_stream(MappingProgressEvent(
            message="Computing multi-dimensional coverage scores…",
            progress=0.75, stage="score"
        ))

        # Group mappings by requirement
        mappings_by_req: Dict[str, List[Dict]] = {}
        for m in mappings:
            rid = m["requirement_id"]
            mappings_by_req.setdefault(rid, []).append(m)

        scores = []
        reqs_needing_depth = []

        for req in reqs:
            req_mappings = mappings_by_req.get(req["id"], [])
            score = self._compute_score(req, req_mappings)
            scores.append(score)

            # Collect requirements that have mappings but need depth assessment
            if req_mappings and self.llm and not score.get("_has_aspects"):
                reqs_needing_depth.append((req, req_mappings))

        # LLM depth assessment for mapped requirements (batch)
        if reqs_needing_depth:
            ctx.write_event_to_stream(MappingProgressEvent(
                message=f"LLM assessing coverage depth for {len(reqs_needing_depth)} requirement(s)…",
                progress=0.82, stage="score"
            ))
            depth_results = await self._llm_depth_assessment(reqs_needing_depth)
            # Merge depth results into scores
            depth_by_req = {d["requirement_id"]: d for d in depth_results}
            for score in scores:
                depth = depth_by_req.get(score["requirement_id"])
                if depth:
                    score["depth_coverage"] = depth.get("depth_score", 0)
                    score["coverage_aspects_present"] = depth.get("aspects_present", [])
                    score["coverage_aspects_missing"] = depth.get("aspects_missing", [])
                    # Recompute total
                    score["total_score"] = _total_from_components(score)

        ctx.write_event_to_stream(MappingProgressEvent(
            message="✓ Scoring complete",
            progress=0.88, stage="score"
        ))

        return ScoredEvent(scores=scores, mappings=mappings)

    # ── Step 5: Assemble & Persist ───────────────────────────────────────────

    @step
    async def assemble(self, ctx: Context, ev: ScoredEvent) -> StopEvent:
        project_id = await ctx.store.get("project_id")

        ctx.write_event_to_stream(MappingProgressEvent(
            message="Persisting mappings and scores…",
            progress=0.90, stage="assemble"
        ))

        # Build summary
        scores = ev.scores
        mappings = ev.mappings

        covered_count = sum(1 for s in scores if s["total_score"] > 0)
        total_count = len(scores)
        avg_score = (
            round(sum(s["total_score"] for s in scores) / total_count, 1)
            if total_count else 0
        )
        coverage_pct = round(covered_count / total_count * 100, 1) if total_count else 0

        # Items needing human review
        review_needed = [
            {
                "requirement_id": s["requirement_id"],
                "external_id": s.get("external_id"),
                "title": s.get("title"),
                "reason": s.get("review_reason", "Low confidence mapping"),
                "score": s["total_score"],
            }
            for s in scores
            if s.get("needs_review")
        ]

        # Score distribution
        distribution = {
            "green_80_100": sum(1 for s in scores if s["total_score"] >= 80),
            "yellow_60_79": sum(1 for s in scores if 60 <= s["total_score"] < 80),
            "orange_30_59": sum(1 for s in scores if 30 <= s["total_score"] < 60),
            "red_0_29": sum(1 for s in scores if s["total_score"] < 30),
        }

        ctx.write_event_to_stream(MappingProgressEvent(
            message="✅ Mapping & scoring complete!",
            progress=1.0, stage="assemble"
        ))

        clean_scores = [{k: v for k, v in s.items() if k != "_has_aspects"} for s in scores]

        return StopEvent(result={
            "project_id": project_id,
            "mappings": [self._clean_mapping(m) for m in mappings],
            "scores": clean_scores,
            "summary": {
                "total_requirements": total_count,
                "covered_requirements": covered_count,
                "uncovered_requirements": total_count - covered_count,
                "coverage_pct": coverage_pct,
                "avg_score": avg_score,
                "total_mappings": len(mappings),
                "distribution": distribution,
            },
            "review_needed": review_needed,
        })

    # ── Pattern Matching ─────────────────────────────────────────────────────

    def _pattern_match(
        self, reqs: List[Dict], cases: List[Dict]
    ) -> List[Dict]:
        """
        Level 0: Find explicit requirement ID references in test cases.
        E.g., TC title contains "FR-017" → direct match, confidence 0.95.
        """
        matches = []
        reqs_with_ids = [(r, r["external_id"]) for r in reqs if r.get("external_id")]

        for req, ext_id in reqs_with_ids:
            for tc in cases:
                tc_text = " ".join(
                    str(v) for v in tc.values()
                    if isinstance(v, str) and not v.startswith("_")
                )
                if ext_id.lower() in tc_text.lower():
                    matches.append({
                        "requirement_id": req["id"],
                        "requirement_ext_id": ext_id,
                        "requirement_title": req["title"],
                        "tc_identifier": tc["_identifier"],
                        "tc_source_file": tc["_source_file"],
                        "mapping_confidence": _MATCH_PATTERN_CONFIDENCE,
                        "mapping_method": "pattern",
                        "coverage_aspects": ["happy_path"],  # assume at least happy path
                        "aspects_missing": [],
                    })
        return matches

    # ── Embedding Similarity ─────────────────────────────────────────────────

    def _similarity_match(
        self,
        reqs: List[Dict],
        req_embeddings: List[List[float]],
        cases: List[Dict],
        tc_embeddings: List[List[float]],
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Level 1: Cosine similarity between requirement and TC embeddings.
        Returns (confident_matches, ambiguous_matches).
        O(n²) — warn when the pair count is large.
        """
        import numpy as np

        pair_count = len(reqs) * len(cases)
        if pair_count > 5000:
            logger.warning(
                "Similarity matching: %d req × %d TC = %d pairs — may be slow",
                len(reqs), len(cases), pair_count,
            )

        confident = []
        ambiguous = []

        for req, req_emb in zip(reqs, req_embeddings):
            if not req_emb:
                continue
            req_vec = np.array(req_emb)
            req_norm = np.linalg.norm(req_vec)
            if req_norm == 0:
                continue

            for tc, tc_emb in zip(cases, tc_embeddings):
                if not tc_emb:
                    continue
                tc_vec = np.array(tc_emb)
                tc_norm = np.linalg.norm(tc_vec)
                if tc_norm == 0:
                    continue

                sim = float(np.dot(req_vec, tc_vec) / (req_norm * tc_norm))

                if sim >= _MATCH_CONFIDENT_THRESHOLD:
                    confident.append({
                        "requirement_id": req["id"],
                        "requirement_ext_id": req.get("external_id"),
                        "requirement_title": req["title"],
                        "tc_identifier": tc["_identifier"],
                        "tc_source_file": tc["_source_file"],
                        "mapping_confidence": round(min(sim * 1.1, 0.92), 2),
                        "mapping_method": "embedding",
                        "similarity": round(sim, 4),
                        "coverage_aspects": [],
                        "aspects_missing": [],
                    })
                elif sim >= _MATCH_AMBIGUOUS_THRESHOLD:
                    ambiguous.append({
                        "requirement_id": req["id"],
                        "requirement_ext_id": req.get("external_id"),
                        "requirement_title": req["title"],
                        "requirement_description": req.get("description", "")[:200],
                        "tc_identifier": tc["_identifier"],
                        "tc_source_file": tc["_source_file"],
                        "tc_text": (build_tc_text(tc) or "")[:300],
                        "mapping_confidence": round(sim, 2),
                        "mapping_method": "embedding",
                        "similarity": round(sim, 4),
                        "coverage_aspects": [],
                        "aspects_missing": [],
                    })

        logger.info(
            "Embedding similarity: %d confident (>%.2f), %d ambiguous (%.2f–%.2f)",
            len(confident), _MATCH_CONFIDENT_THRESHOLD,
            len(ambiguous), _MATCH_AMBIGUOUS_THRESHOLD, _MATCH_CONFIDENT_THRESHOLD,
        )
        return confident, ambiguous

    # ── LLM Fine Matching ────────────────────────────────────────────────────

    async def _llm_fine_match(
        self, pairs: List[Dict], reqs: List[Dict]
    ) -> List[Dict]:
        """LLM-evaluate ambiguous (requirement, TC) pairs."""
        if not self.llm:
            return [{"verdict": "NO"}] * len(pairs)

        req_by_id = {r["id"]: r for r in reqs}
        pairs_text = []
        for i, pair in enumerate(pairs):
            req = req_by_id.get(pair["requirement_id"], {})
            pairs_text.append(
                f"pair_{i}:\n"
                f"  Requirement: [{req.get('external_id', 'N/A')}] {req.get('title', '')}\n"
                f"    Description: {req.get('description', '')[:200]}\n"
                f"  Test Case: {pair['tc_identifier']}\n"
                f"    Content: {pair.get('tc_text', '')[:200]}\n"
                f"  Embedding similarity: {pair.get('similarity', 'N/A')}"
            )

        prompt = FINE_MATCH_PROMPT.format(pairs="\n\n".join(pairs_text))

        try:
            response = await self.llm.acomplete(prompt)
            raw = strip_fences(str(response).strip())
            results = json.loads(raw)
            if isinstance(results, list) and len(results) == len(pairs):
                return results
            # Fallback: if count mismatch, return conservative NO
            logger.warning("LLM returned %d results for %d pairs", len(results), len(pairs))
            padded = results + [{"verdict": "NO"}] * (len(pairs) - len(results))
            return padded[:len(pairs)]
        except Exception as e:
            logger.warning("LLM fine matching failed: %s", e)
            return [{"verdict": "NO"}] * len(pairs)

    # ── Coverage Scoring ─────────────────────────────────────────────────────

    def _compute_score(self, req: Dict, mappings: List[Dict]) -> Dict:
        """
        Compute multi-dimensional score for a single requirement.

        Scoring model (0–100):
          base_coverage      (0–40)  — are there any matches at all?
          depth_coverage     (0–30)  — LLM-assessed later if needed
          quality_weight     (0–20)  — avg confidence of mappings
          confidence_penalty (-10–0) — penalty for low req confidence
          crossref_bonus     (0–10)  — multiple source files = broader coverage
        """
        n_mappings = len(mappings)
        has_mappings = n_mappings > 0

        # ── Base Coverage (0–_SCORE_BASE_MAX) ──
        if not has_mappings:
            base = 0.0
        elif n_mappings == 1:
            base = 25.0
        elif n_mappings <= 3:
            base = 35.0
        else:
            base = _SCORE_BASE_MAX

        # Check if any mapping has known coverage_aspects
        all_aspects = set()
        has_aspects = False
        for m in mappings:
            aspects = m.get("coverage_aspects", [])
            if aspects:
                has_aspects = True
                all_aspects.update(aspects)

        # If we have aspects from fine matching, refine base score
        if has_aspects:
            if "happy_path" in all_aspects:
                base = max(base, 30.0)
            if "negative" in all_aspects:
                base = min(base + 5, _SCORE_BASE_MAX)

        # ── Depth Coverage (0–_SCORE_DEPTH_MAX) — set later by LLM, estimate for now ──
        if has_aspects:
            depth_points = {
                "negative": 8, "boundary": 8,
                "integration": 5, "edge_case": 5,
                "performance": 2, "security": 2,
            }
            depth = sum(depth_points.get(a, 0) for a in all_aspects)
            depth = min(depth, _SCORE_DEPTH_MAX)
        else:
            # No aspect info — rough estimate from mapping count
            depth = min(n_mappings * 5, 15.0) if has_mappings else 0.0

        # ── Quality Weight (0–_SCORE_QUALITY_MAX) ──
        if has_mappings:
            avg_confidence = sum(m.get("mapping_confidence", 0.5) for m in mappings) / n_mappings
            quality = round(avg_confidence * _SCORE_QUALITY_MAX, 1)
        else:
            quality = 0.0
            avg_confidence = 0.0

        # ── Confidence Penalty (_SCORE_PENALTY_MAX–0) ──
        req_confidence = req.get("confidence", 0.5)
        if req_confidence < 0.7:
            penalty = round(_SCORE_PENALTY_MAX * (0.7 - req_confidence) / 0.7, 1)
        else:
            penalty = 0.0

        # ── Cross-reference Bonus (0–_SCORE_CROSSREF_MAX) ──
        source_files = {m.get("tc_source_file", "") for m in mappings}
        if len(source_files) >= 3:
            crossref = _SCORE_CROSSREF_MAX
        elif len(source_files) == 2:
            crossref = 7.0
        elif len(source_files) == 1 and has_mappings:
            crossref = 3.0
        else:
            crossref = 0.0

        total = _total_from_components({
            "base_coverage": round(base, 1),
            "depth_coverage": round(depth, 1),
            "quality_weight": round(quality, 1),
            "confidence_penalty": round(penalty, 1),
            "crossref_bonus": round(crossref, 1),
        })

        # Determine review needs
        needs_review = False
        review_reason = None
        if has_mappings and avg_confidence < 0.6:
            needs_review = True
            review_reason = f"Low avg mapping confidence ({avg_confidence:.2f})"
        elif req.get("needs_review"):
            needs_review = True
            review_reason = "Requirement flagged for review in Faza 2"

        return {
            "requirement_id": req["id"],
            "external_id": req.get("external_id"),
            "title": req["title"],
            "level": req.get("level", "functional_req"),
            "taxonomy": req.get("taxonomy", {}),
            "total_score": total,
            "base_coverage": round(base, 1),
            "depth_coverage": round(depth, 1),
            "quality_weight": round(quality, 1),
            "confidence_penalty": round(penalty, 1),
            "crossref_bonus": round(crossref, 1),
            "matched_tc_count": n_mappings,
            "coverage_aspects_present": list(all_aspects),
            "coverage_aspects_missing": [],  # filled by LLM depth assessment
            "needs_review": needs_review,
            "review_reason": review_reason,
            "_has_aspects": has_aspects,  # internal flag, stripped in output
        }

    async def _llm_depth_assessment(
        self, reqs_with_mappings: List[Tuple[Dict, List[Dict]]]
    ) -> List[Dict]:
        """LLM assesses coverage depth for requirements that have mappings (concurrent)."""
        if not self.llm:
            return []

        sem = asyncio.Semaphore(settings.LLM_CONCURRENT_CALLS)

        async def _assess_one(req: Dict, mappings: List[Dict]) -> Optional[Dict]:
            tc_list = "\n".join(
                f"  - {m.get('tc_identifier', '?')} (confidence: {m.get('mapping_confidence', 0):.2f})"
                for m in mappings[:10]
            )
            prompt = COVERAGE_ASPECTS_PROMPT.format(
                req_id=req.get("external_id", req["id"][:8]),
                req_title=req["title"],
                req_desc=req.get("description", "")[:300],
                tc_list=tc_list,
            )
            try:
                async with sem:
                    response = await self.llm.acomplete(prompt)
                raw = strip_fences(str(response).strip())
                data = json.loads(raw)
                depth_map = {"high": 25, "medium": 15, "low": 8}
                return {
                    "requirement_id": req["id"],
                    "aspects_present": data.get("aspects_present", []),
                    "aspects_missing": data.get("aspects_missing", []),
                    "depth_score": depth_map.get(data.get("depth_rating", "low"), 8),
                    "recommendation": data.get("recommendation", ""),
                }
            except Exception as e:
                logger.warning("Depth assessment failed for %s: %s", req["id"][:8], e)
                return None

        raw_results = await asyncio.gather(*[
            _assess_one(req, mappings)
            for req, mappings in reqs_with_mappings[:20]  # cap at 20
        ])
        return [r for r in raw_results if r is not None]

    # ── Data Loading ─────────────────────────────────────────────────────────

    async def _load_requirements(self, project_id: str) -> List[Dict]:
        """Load requirements from Faza 2 DB registry."""
        try:
            async with AsyncSessionLocal() as db:
                stmt = (
                    select(Requirement)
                    .where(Requirement.project_id == project_id)
                    .where(Requirement.level.in_(["functional_req", "acceptance_criterion"]))
                    .order_by(Requirement.created_at)
                )
                rows = (await db.execute(stmt)).scalars().all()
                return [
                    {
                        "id": r.id,
                        "external_id": r.external_id,
                        "title": r.title,
                        "description": r.description or "",
                        "level": r.level,
                        "confidence": r.confidence or 0.5,
                        "taxonomy": r.taxonomy or {},
                        "needs_review": r.needs_review,
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.warning("Failed to load requirements: %s", e)
            return []

    async def _auto_load_files(self, project_id: str) -> List[str]:
        """Auto-load all uploaded test files for this project from DB.
        Loads ALL files (not filtered by last_used_in_audit_id) — mapping needs full coverage."""
        try:
            async with AsyncSessionLocal() as db:
                stmt = select(ProjectFile.file_path).where(
                    ProjectFile.project_id == project_id
                )
                rows = (await db.execute(stmt)).scalars().all()
                return list(rows)
        except Exception:
            return []

    # ── Embedding ─────────────────────────────────────────────────────────────

    async def _embed_items(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of texts using the app embed model."""
        if self._embed_model is None:
            logger.warning("Embed model not available — returning empty embeddings")
            return [[] for _ in texts]
        results = []
        for i in range(0, len(texts), 50):
            batch = texts[i:i + 50]
            for text in batch:
                if text.strip():
                    emb = await self._embed_model.aget_text_embedding(text)
                    results.append(emb)
                else:
                    results.append([])
            if i + 50 < len(texts):
                await asyncio.sleep(0.3)
        return results

    # ── Text builders ─────────────────────────────────────────────────────────

    @staticmethod
    def _req_to_text(req: Dict) -> str:
        """Build searchable text from a requirement."""
        parts = []
        if req.get("external_id"):
            parts.append(req["external_id"])
        parts.append(req.get("title", ""))
        if req.get("description"):
            parts.append(req["description"][:300])
        return ". ".join(p for p in parts if p)

    @staticmethod
    def _clean_mapping(m: Dict) -> Dict:
        """Remove internal fields before returning to API."""
        return {k: v for k, v in m.items() if not k.startswith("_") and k not in (
            "requirement_description", "tc_text", "similarity"
        )}

