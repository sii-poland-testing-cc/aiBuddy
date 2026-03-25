"""
Audit Agent Workflow  (Tier 1 – Audit)
=======================================
Processes uploaded test-suite files and Confluence exports,
then returns a structured audit report with:
  - coverage gaps
  - duplicate detection
  - missing priority/tag assignments
  - recommended next steps (Optimize / Regenerate)

Events:
  StartAuditEvent  →  ParseEvent  →  AnalyseEvent  →  StopEvent

Faza 2 integration:
  When a Requirements Registry exists (from requirements_workflow.py),
  the analyse step uses it for richer coverage computation.
  Falls back to original LLM extraction when no registry is available.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from llama_index.core.workflow import (
    Context,
    Event,
    StartEvent,
    StopEvent,
    Workflow,
    step,
)

from app.agents.audit_workflow_integration import compute_registry_coverage
from app.core.config import settings
from app.utils.json_utils import parse_json_object, strip_fences
from app.rag.context_builder import ContextBuilder
from app.parsers.test_case_parser import build_tc_text, parse_test_file

logger = logging.getLogger("ai_buddy.audit")

# Cosine similarity thresholds for duplicate detection.
# Pairs above CERTAIN are flagged immediately; pairs in (CANDIDATE, CERTAIN) go to LLM.
_DUPE_CERTAIN_THRESHOLD    = 0.98
_DUPE_CANDIDATE_THRESHOLD  = 0.93


# ─── Events ──────────────────────────────────────────────────────────────────

class ParsedEvent(Event):
    """Emitted after raw files are parsed into structured test cases."""
    test_cases: List[Dict[str, Any]]
    source_files: List[str]


class AnalysisProgressEvent(Event):
    """Intermediate event streamed to the frontend (human-in-the-loop signal)."""
    message: str
    progress: float          # 0.0 – 1.0


class AuditResultEvent(Event):
    """Final audit data before formatting."""
    duplicates: List[Dict]          # certain + llm-confirmed pairs
    certain_duplicates: List[Dict]  # sim >= 0.98, no LLM needed
    candidate_duplicates: List[Dict]
    similar_pairs: List[Dict]       # candidates judged SIMILAR (not duplicates)
    untagged: List[Dict]
    coverage_pct: float
    recommendations: List[str]
    rag_sources: List[Dict]   # [{"filename": str, "excerpt": str}]
    requirements_total: int = 0
    requirements_covered_count: int = 0
    requirements_uncovered: List[str] = []


# ─── Workflow ─────────────────────────────────────────────────────────────────

class AuditWorkflow(Workflow):
    """
    Three-step workflow:
      1. parse  – extract test cases from uploaded files
      2. analyse – run LLM-powered gap analysis via RAG
      3. report  – format and return JSON audit report
    """

    def __init__(self, llm=None, **kwargs):
        super().__init__(**kwargs)
        self.llm = llm
        self.context_builder = ContextBuilder()
        # Reuse the embed model already loaded by ContextBuilder (avoids double load)
        self._embed_model = self.context_builder._embed_model

    # ── Step 1: Parse ────────────────────────────────────────────────────────

    @step
    async def parse(self, ctx: Context, ev: StartEvent) -> ParsedEvent:
        file_paths: List[str] = ev.get("file_paths", [])
        project_id: str = ev.get("project_id", "unknown")
        user_message: str = ev.get("user_message", "")

        await ctx.store.set("project_id", project_id)
        await ctx.store.set("user_message", user_message)

        test_cases: List[Dict] = []
        for path in file_paths:
            cases = await parse_test_file(path)
            test_cases.extend(cases)

        ctx.write_event_to_stream(
            AnalysisProgressEvent(message=f"Parsed {len(test_cases)} test cases from {len(file_paths)} file(s)", progress=0.2)
        )

        return ParsedEvent(test_cases=test_cases, source_files=file_paths)

    # ── Step 2: Analyse ───────────────────────────────────────────────────────

    @step
    async def analyse(self, ctx: Context, ev: ParsedEvent) -> AuditResultEvent:
        cases = ev.test_cases

        ctx.write_event_to_stream(
            AnalysisProgressEvent(message="Detecting duplicates…", progress=0.4)
        )
        certain, candidates, _, similar_pairs, duplicates = (
            await self._run_duplicate_detection(ctx, cases)
        )

        ctx.write_event_to_stream(
            AnalysisProgressEvent(message="Checking tag coverage…", progress=0.6)
        )
        untagged = [c for c in cases if not c.get("tags")]

        ctx.write_event_to_stream(
            AnalysisProgressEvent(message="Running LLM gap analysis…", progress=0.75)
        )

        # Build RAG context from M1 knowledge base
        project_id = await ctx.store.get("project_id")
        user_message = await ctx.store.get("user_message") or ""
        rag_query = f"{user_message} test coverage gaps requirements".strip()

        rag_context, rag_sources = await self.context_builder.build_with_sources(
            project_id, query=rag_query
        )

        if not rag_sources:
            logger.warning(
                "project=%s — no M1 context indexed; audit will run without domain knowledge",
                project_id,
            )
        else:
            logger.info("project=%s — retrieved %d RAG source(s)", project_id, len(rag_sources))

        # ── Faza 2: Use Requirements Registry when available ──────────────
        # compute_registry_coverage() checks the DB for a Faza 2 registry.
        # Priority: Faza 5+6 persisted scores → Faza 2 registry → legacy LLM extraction.
        coverage_result = await compute_registry_coverage(
            project_id, cases, rag_context, self.llm
        )

        requirements_from_docs = coverage_result["requirements_from_docs"]
        await ctx.store.set("requirements_from_docs", requirements_from_docs)
        logger.debug("requirements_from_docs: %s", requirements_from_docs)

        covered = coverage_result["requirements_covered"]
        await ctx.store.set("requirements_covered", covered)
        logger.debug("requirements_covered: %s", covered)

        # Store Faza 2 enrichment data for the report step
        await ctx.store.set(
            "per_requirement_scores",
            coverage_result.get("per_requirement_scores", []),
        )
        await ctx.store.set(
            "registry_available",
            coverage_result.get("registry_available", False),
        )
        # ── End Faza 2 block ──────────────────────────────────────────────

        recommendations = await self._llm_recommendations(cases, rag_context, user_message)

        # Requirement-based coverage
        total     = coverage_result["requirements_total"]
        n_covered = coverage_result["requirements_covered_count"]
        uncovered = coverage_result["requirements_uncovered"]
        coverage_pct = coverage_result["coverage_pct"]

        if total == 0:
            recommendations = list(recommendations) + [
                "No domain context available — run M1 Context Builder "
                "first for accurate requirement coverage analysis"
            ]

        logger.info(
            "project=%s — coverage=%s%% (%d/%d reqs covered); uncovered=%s; registry=%s",
            project_id, coverage_pct, n_covered, total, uncovered,
            coverage_result.get("registry_available", False),
        )

        ctx.write_event_to_stream(
            AnalysisProgressEvent(message="Generating report…", progress=0.9)
        )

        recommendations = list(recommendations)
        if similar_pairs:
            recommendations.append(
                f"SIMILAR TEST CASES ({len(similar_pairs)} pairs) — not duplicates but "
                "may indicate overlap. Review: "
                + "; ".join(
                    f"{p['tc_a'].get('title') or p['tc_a'].get('name', '?')} ↔ "
                    f"{p['tc_b'].get('title') or p['tc_b'].get('name', '?')}"
                    for p in similar_pairs[:5]
                )
            )

        return AuditResultEvent(
            duplicates=duplicates,
            certain_duplicates=certain,
            candidate_duplicates=candidates,
            similar_pairs=similar_pairs,
            untagged=untagged,
            coverage_pct=coverage_pct,
            recommendations=recommendations,
            rag_sources=rag_sources,
            requirements_total=total,
            requirements_covered_count=n_covered,
            requirements_uncovered=uncovered,
        )

    # ── Step 3: Report ────────────────────────────────────────────────────────

    @step
    async def report(self, ctx: Context, ev: AuditResultEvent) -> StopEvent:
        project_id = await ctx.store.get("project_id")

        llm_confirmed = [p for p in ev.duplicates if "reason" in p]
        formatted_duplicates = (
            [self._format_duplicate_pair(p, "certain") for p in ev.certain_duplicates]
            + [self._format_duplicate_pair(p, "llm_confirmed") for p in llm_confirmed]
        )

        report = {
            "project_id": project_id,
            "summary": {
                "duplicates_found": len(ev.duplicates),
                "similar_pairs_found": len(ev.similar_pairs),
                "untagged_cases": len(ev.untagged),
                "coverage_pct": ev.coverage_pct,
                "requirements_total":     ev.requirements_total,
                "requirements_covered":   ev.requirements_covered_count,
                "requirements_uncovered": ev.requirements_uncovered,
            },
            "duplicates": formatted_duplicates,
            "certain_duplicates": ev.certain_duplicates,
            "candidate_duplicates": ev.candidate_duplicates,
            "similar_pairs": ev.similar_pairs,
            "untagged": ev.untagged,
            "recommendations": ev.recommendations,
            "rag_sources": ev.rag_sources,
            "next_tier": "optimize" if ev.coverage_pct >= 50 else "regenerate",
        }

        # ── Faza 2: Append per-requirement scores when available ──────────
        per_req_scores = await ctx.store.get("per_requirement_scores") or []
        registry_available = await ctx.store.get("registry_available") or False

        report["per_requirement_scores"] = per_req_scores
        report["registry_available"] = registry_available
        # ── End Faza 2 block ──────────────────────────────────────────────

        return StopEvent(result=report)

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _format_duplicate_pair(pair: Dict, source: str) -> Dict:
        """Return a presentable duplicate entry (string labels, not raw dicts)."""
        tc_a = pair["tc_a"]
        tc_b = pair["tc_b"]
        return {
            "tc_a": tc_a.get("title") or tc_a.get("name") or tc_a.get("test_id", "?"),
            "tc_b": tc_b.get("title") or tc_b.get("name") or tc_b.get("test_id", "?"),
            "similarity": pair["similarity"],
            "source": source,
            "reason": pair.get("reason") or None,
        }

    async def _run_duplicate_detection(
        self, ctx: Context, cases: List[Dict]
    ) -> Tuple[List[Dict], List[Dict], List[Dict], List[Dict], List[Dict]]:
        """Embed test cases, find candidates, LLM-judge them.

        Returns (certain, candidates, llm_confirmed, similar_pairs, duplicates).
        """
        embedded = await self._embed_test_cases(cases)
        certain, candidates = self._find_duplicate_candidates(embedded)
        await ctx.store.set("certain_duplicates", certain)
        await ctx.store.set("llm_candidates", candidates)

        if candidates and self.llm:
            ctx.write_event_to_stream(
                AnalysisProgressEvent(
                    message=f"LLM judging {len(candidates)} candidate duplicate pair(s)…",
                    progress=0.42,
                )
            )
            llm_confirmed = await self._judge_candidates_with_llm(candidates)
        else:
            llm_confirmed = candidates  # no LLM — treat all candidates as duplicates

        # Track confirmed pairs by object identity — each confirmed entry is
        # {**pair, "reason": ...}, so dict equality would never match the original.
        confirmed_keys = {(id(r["tc_a"]), id(r["tc_b"])) for r in llm_confirmed}
        similar_pairs = [
            c for c in candidates
            if (id(c["tc_a"]), id(c["tc_b"])) not in confirmed_keys
        ]
        duplicates = certain + llm_confirmed
        await ctx.store.set("duplicates", duplicates)
        await ctx.store.set("similar_pairs", similar_pairs)
        return certain, candidates, llm_confirmed, similar_pairs, duplicates

    async def _embed_test_cases(
        self, cases: List[Dict]
    ) -> List[Tuple[Dict, List[float]]]:
        """Embed each test case using the app's configured embed model."""
        valid = [(c, build_tc_text(c)) for c in cases]
        valid = [(c, t) for c, t in valid if t is not None]

        results: List[Tuple[Dict, List[float]]] = []
        for i in range(0, len(valid), 50):
            batch = valid[i : i + 50]
            for case, text in batch:
                emb = await self._embed_model.aget_text_embedding(text)
                results.append((case, emb))
            if i + 50 < len(valid):
                await asyncio.sleep(0.5)  # rate-limit buffer for remote embed models

        logger.info("Embedded %d test cases", len(results))
        return results

    @staticmethod
    def _find_duplicate_candidates(
        embedded: List[Tuple[Dict, List[float]]],
    ) -> Tuple[List[Dict], List[Dict]]:
        """Return (certain_duplicates, candidates_for_llm) via cosine similarity.

        Pairs with sim >= _DUPE_CERTAIN_THRESHOLD are flagged without LLM review.
        Pairs in [_DUPE_CANDIDATE_THRESHOLD, _DUPE_CERTAIN_THRESHOLD) go to the LLM judge.
        """
        import numpy as np

        n = len(embedded)
        if n > 500:
            logger.warning(
                "_find_duplicate_candidates: %d test cases — O(n²) is slow; consider FAISS upgrade", n
            )

        def cosine(a: List[float], b: List[float]) -> float:
            va, vb = np.array(a), np.array(b)
            na, nb = np.linalg.norm(va), np.linalg.norm(vb)
            if na == 0 or nb == 0:
                return 0.0
            return float(np.dot(va, vb) / (na * nb))

        certain: List[Dict] = []
        candidates: List[Dict] = []

        for i in range(n):
            case_i, emb_i = embedded[i]
            for j in range(i + 1, n):
                case_j, emb_j = embedded[j]
                sim = cosine(emb_i, emb_j)
                if sim >= _DUPE_CERTAIN_THRESHOLD:
                    certain.append({"tc_a": case_i, "tc_b": case_j, "similarity": round(sim, 4)})
                elif sim >= _DUPE_CANDIDATE_THRESHOLD:
                    candidates.append({"tc_a": case_i, "tc_b": case_j, "similarity": round(sim, 4)})

        logger.info("Certain duplicates: %d, LLM candidates: %d", len(certain), len(candidates))
        return certain, candidates

    async def _judge_candidates_with_llm(
        self, candidates: List[Dict]
    ) -> List[Dict]:
        """LLM-judge embedding candidates; return only confirmed duplicates."""
        if not self.llm:
            return candidates

        batch = candidates
        if len(candidates) > 20:
            logger.warning(
                "_judge_candidates_with_llm: %d candidates — capping at 20 to control LLM costs",
                len(candidates),
            )
            batch = sorted(candidates, key=lambda p: p["similarity"], reverse=True)[:20]

        sem = asyncio.Semaphore(settings.LLM_CONCURRENT_CALLS)

        async def _judge_one(pair: Dict):
            tc_a, tc_b = pair["tc_a"], pair["tc_b"]
            prompt = f"""You are a QA expert. Determine if these two test cases are duplicates.

Test Case A:
  Title: {tc_a.get('title') or tc_a.get('name')}
  Steps: {tc_a.get('steps') or tc_a.get('test_steps')}
  Expected: {tc_a.get('expected_result') or tc_a.get('assertions')}

Test Case B:
  Title: {tc_b.get('title') or tc_b.get('name')}
  Steps: {tc_b.get('steps') or tc_b.get('test_steps')}
  Expected: {tc_b.get('expected_result') or tc_b.get('assertions')}

Embedding similarity: {pair['similarity']}

Rules:
- DUPLICATE: same scenario, same goal, same expected outcome (even if wording differs)
- SIMILAR: related but test different conditions, inputs, or edge cases
- DIFFERENT: clearly distinct test objectives

Respond with ONLY a JSON object, no markdown:
{{"verdict": "DUPLICATE|SIMILAR|DIFFERENT", "reason": "one sentence"}}"""

            async with sem:
                try:
                    response = await self.llm.acomplete(prompt, max_tokens=200)
                    data = parse_json_object(str(response).strip())
                    verdict = str(data.get("verdict", "")).upper()
                    reason  = data.get("reason", "")
                    logger.info("LLM verdict for pair (sim=%.4f): %s — %s", pair["similarity"], verdict, reason)
                    if verdict == "DUPLICATE":
                        return {**pair, "reason": reason}
                except Exception:
                    logger.exception("LLM judgment failed for candidate pair; treating as non-duplicate")
            return None

        results = await asyncio.gather(*[_judge_one(p) for p in batch])
        return [r for r in results if r is not None]

    async def _llm_recommendations(
        self, cases: List[Dict], context: str, user_question: str = ""
    ) -> List[str]:
        if not self.llm:
            return ["Enable LLM for AI-powered recommendations."]

        has_context = "(No indexed context" not in context
        context_section = (
            f"Domain knowledge from project documentation:\n{context}"
            if has_context
            else "No domain documentation indexed yet — base analysis on the test suite alone."
        )

        question_section = (
            f"\nUser's specific question: {user_question}" if user_question.strip() else ""
        )

        prompt = f"""You are a senior QA architect. Analyse the test suite and return
exactly 5 actionable, specific recommendations as a JSON array of strings.
Reference concepts from the domain documentation where relevant.{question_section}

{context_section}

Test suite summary:
- Total cases: {len(cases)}
- Cases without tags: {sum(1 for c in cases if not c.get('tags'))}
- Sample case names: {[c.get('name','') for c in cases[:5]]}

Respond ONLY with a valid JSON array of 5 strings. No preamble, no markdown."""

        try:
            response = await self.llm.acomplete(prompt, max_tokens=1024)
            raw = strip_fences(str(response).strip())
            return json.loads(raw)
        except Exception:
            return ["Enable LLM for AI-powered recommendations."]