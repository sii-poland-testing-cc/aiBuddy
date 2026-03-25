"""
audit_workflow_integration.py
==============================
Bridge between the Audit workflow and Faza 2/5/6 data.

Priority chain:
  1. Faza 5 persisted mappings + Faza 6 scores -> best quality (pre-computed)
  2. Faza 2 registry -> requirements from DB + live matching
  3. Legacy LLM extraction -> original behavior (no Faza 2 data)
"""

import json
import logging
import re
from typing import Any, Dict, List, Tuple

from sqlalchemy import select

from app.db.engine import AsyncSessionLocal
from app.db.requirements_models import CoverageScore, Requirement
from app.utils.json_utils import strip_fences

logger = logging.getLogger("ai_buddy.audit_integration")


async def compute_registry_coverage(
    project_id: str,
    cases: List[Dict],
    rag_context: str,
    llm: Any = None,
) -> Dict[str, Any]:
    """
    Enhanced coverage computation. Priority:
      1. Faza 5+6 persisted scores -> return immediately (best quality)
      2. Faza 2 registry -> live matching against TCs
      3. Legacy LLM extraction -> original behavior (no Faza 2 data)

    NOTE on is_covered semantics:
      - Priority 1: is_covered = total_score > 0 (Faza 6 multi-dim score; even
        a single weak mapping gives ~35 points, so >0 is a reliable threshold)
      - Priority 2/3: is_covered = identifier appears in pattern/LLM matched set
        (binary; do not silently unify these two branches)
    """
    # Priority 1: Faza 5+6 persisted scores (best quality, no LLM calls needed)
    persisted = await _load_persisted_scores(project_id)
    if persisted:
        logger.info(
            "project=%s - using Faza 5+6 persisted scores (%d reqs)",
            project_id, persisted["requirements_total"],
        )
        return persisted

    # Priority 2: Faza 2 registry
    req_ids, req_details = await _load_faza2_requirements(project_id)
    if not req_ids:
        # Priority 3: legacy LLM extraction (no Faza 2 data)
        logger.info("project=%s - no Faza 2 registry, falling back to LLM extraction", project_id)
        req_ids = await _legacy_extract(rag_context, llm)
        req_details = []

    if not req_ids:
        return {
            "requirements_from_docs": [], "requirements_covered": [],
            "coverage_pct": 0.0, "requirements_total": 0,
            "requirements_covered_count": 0, "requirements_uncovered": [],
            "registry_available": False, "per_requirement_scores": [],
        }

    covered = await _match_requirements_to_tests(cases, req_ids, req_details, llm)
    return _build_live_coverage_result(req_ids, req_details, covered)


async def _load_faza2_requirements(
    project_id: str,
) -> Tuple[List[str], List[Dict]]:
    """Load functional requirements + acceptance criteria from the Faza 2 DB registry."""
    try:
        async with AsyncSessionLocal() as db:
            stmt = (
                select(Requirement)
                .where(Requirement.project_id == project_id)
                .where(Requirement.level.in_(["functional_req", "acceptance_criterion"]))
                .order_by(Requirement.created_at)
            )
            rows = (await db.execute(stmt)).scalars().all()
            if not rows:
                return [], []
            logger.info(
                "project=%s - loaded %d requirements from Faza 2 registry",
                project_id, len(rows),
            )
            req_ids, req_details = [], []
            for r in rows:
                identifier = r.external_id or r.title
                req_ids.append(identifier)
                req_details.append({
                    "id": r.id, "external_id": r.external_id, "title": r.title,
                    "description": r.description or "", "level": r.level,
                    "confidence": r.confidence or 0.5,
                    "taxonomy": json.loads(r.taxonomy) if r.taxonomy else {},
                    "needs_review": r.needs_review,
                })
            return req_ids, req_details
    except Exception as exc:
        logger.warning("Failed to load Faza 2 requirements registry: %s", exc)
        return [], []


async def _legacy_extract(rag_context: str, llm: Any) -> List[str]:
    """Extract requirement IDs from RAG context using the LLM. Returns [] when no LLM."""
    if not llm:
        return []
    prompt = (
        "Extract all formal requirement IDs from the documentation below.\n"
        "Return ONLY a valid JSON array of strings, no preamble, no markdown.\n"
        'Examples: ["FR-001", "FR-002", "NFR-Performance"]\n'
        "Rules:\n"
        "- Include only requirement IDs (e.g. FR-*, NFR-*, REQ-*, US-*)\n"
        "- Do NOT include test case IDs (e.g. TC-*, test identifiers)\n"
        "- If no formal requirement IDs exist, return []\n\n"
        f"Documentation:\n{rag_context}"
    )
    try:
        response = await llm.acomplete(prompt)
        raw = strip_fences(str(response).strip())
        for match in reversed(list(re.finditer(r"\[.*?\]", raw, re.DOTALL))):
            try:
                items = json.loads(match.group())
                return [r for r in items if not str(r).upper().startswith("TC-")]
            except json.JSONDecodeError:
                continue
        return json.loads(raw)
    except Exception:
        return []


async def _load_persisted_scores(project_id: str) -> Dict[str, Any] | None:
    """Try loading Faza 5+6 persisted coverage scores. Returns None if none exist.

    is_covered = total_score > 0 (Faza 6 model; a single mapping yields ≥35 pts).
    """
    try:
        async with AsyncSessionLocal() as db:
            stmt = select(CoverageScore).where(CoverageScore.project_id == project_id)
            score_rows = (await db.execute(stmt)).scalars().all()
            if not score_rows:
                return None

            req_ids = [s.requirement_id for s in score_rows]
            req_stmt = select(Requirement).where(Requirement.id.in_(req_ids))
            req_rows = (await db.execute(req_stmt)).scalars().all()
            reqs_by_id = {r.id: r for r in req_rows}

            per_req_scores, covered_ids, uncovered_ids, all_req_ids = [], [], [], []

            for s in score_rows:
                req = reqs_by_id.get(s.requirement_id)
                identifier = (req.external_id or req.title) if req else s.requirement_id
                all_req_ids.append(identifier)
                is_covered = s.total_score > 0
                (covered_ids if is_covered else uncovered_ids).append(identifier)

                per_req_scores.append({
                    "requirement_id": s.requirement_id,
                    "external_id": req.external_id if req else None,
                    "title": req.title if req else "Unknown",
                    "level": req.level if req else None,
                    "taxonomy": json.loads(req.taxonomy) if req and req.taxonomy else {},
                    "is_covered": is_covered, "score": s.total_score,
                    "confidence": req.confidence if req else 0.5,
                    "needs_review": req.needs_review if req else False,
                    "base_coverage": s.base_coverage, "depth_coverage": s.depth_coverage,
                    "quality_weight": s.quality_weight, "confidence_penalty": s.confidence_penalty,
                    "crossref_bonus": s.crossref_bonus, "matched_tc_count": s.matched_tc_count,
                })

            total = len(score_rows)
            n_covered = len(covered_ids)
            return {
                "requirements_from_docs": all_req_ids, "requirements_covered": covered_ids,
                "coverage_pct": round(n_covered / total * 100, 1) if total else 0.0,
                "requirements_total": total, "requirements_covered_count": n_covered,
                "requirements_uncovered": uncovered_ids, "registry_available": True,
                "per_requirement_scores": per_req_scores,
            }
    except Exception as exc:
        logger.debug("No Faza 5+6 scores available: %s", exc)
        return None


def _build_live_coverage_result(
    req_ids: List[str],
    req_details: List[Dict],
    covered: List[str],
) -> Dict[str, Any]:
    """
    Build the coverage result dict from live matching output (Priority 2/3).

    is_covered = identifier appears in the matched set (binary pattern/LLM match).
    This differs from Priority 1's score > 0 threshold — do not unify.
    """
    total = len(req_ids)
    covered_set = set(covered)
    n_covered = len(covered_set & set(req_ids))
    uncovered = [r for r in req_ids if r not in covered_set]
    coverage_pct = round((n_covered / total) * 100, 1) if total else 0.0

    per_req_scores = []
    if req_details:
        for detail in req_details:
            identifier = detail.get("external_id") or detail.get("title")
            is_covered = identifier in covered_set
            confidence = detail.get("confidence", 0.5)
            base = 40.0 if is_covered else 0.0
            penalty = -10.0 * max(0, 0.7 - confidence) / 0.7 if confidence < 0.7 else 0.0
            per_req_scores.append({
                "requirement_id": detail["id"], "external_id": detail.get("external_id"),
                "title": detail["title"], "level": detail["level"],
                "taxonomy": detail.get("taxonomy", {}), "is_covered": is_covered,
                "score": round(max(0, base + penalty), 1), "confidence": confidence,
                "needs_review": detail.get("needs_review", False),
            })

    return {
        "requirements_from_docs": req_ids, "requirements_covered": covered,
        "coverage_pct": coverage_pct, "requirements_total": total,
        "requirements_covered_count": n_covered, "requirements_uncovered": uncovered,
        "registry_available": bool(req_details), "per_requirement_scores": per_req_scores,
    }


async def _match_requirements_to_tests(
    cases: List[Dict], req_ids: List[str], req_details: List[Dict], llm: Any,
) -> List[str]:
    if not req_ids:
        return []
    covered: set = set()
    for case in cases:
        # Skip _-prefixed internal keys (e.g. _source_file, _identifier added by mapping_workflow)
        # to avoid false matches like a file named "FR-017_suite.csv" matching requirement FR-017.
        text = " ".join(str(v) for k, v in case.items() if isinstance(v, str) and not k.startswith("_"))
        for req_id in req_ids:
            if req_id.lower() in text.lower():
                covered.add(req_id)
    if req_details and llm and len(covered) < len(req_ids) * 0.5:
        uncovered_details = [
            d for d in req_details
            if (d.get("external_id") or d.get("title")) not in covered
        ]
        if uncovered_details and len(uncovered_details) <= 30:
            case_names = [c.get("name", "") or c.get("title", "") for c in cases[:30]]
            reqs_text = "\n".join(
                f"- {d.get('external_id') or 'N/A'}: {d['title']} - {d.get('description', '')[:100]}"
                for d in uncovered_details[:20]
            )
            prompt = (
                "Given these test cases:\n"
                f"{json.dumps(case_names, ensure_ascii=False)}\n\n"
                f"And these uncovered requirements:\n{reqs_text}\n\n"
                "Which requirements are covered by at least one test case?\n"
                "Match based on what the test case actually verifies, not just name similarity.\n"
                "Return ONLY a valid JSON array of covered requirement identifiers."
            )
            try:
                response = await llm.acomplete(prompt)
                raw = strip_fences(str(response).strip())
                for match in reversed(list(re.finditer(r"\[.*?\]", raw, re.DOTALL))):
                    try:
                        covered.update(json.loads(match.group()))
                        break
                    except json.JSONDecodeError:
                        continue
            except Exception as exc:
                logger.warning("LLM requirement matching failed: %s", exc)
    return list(covered)
