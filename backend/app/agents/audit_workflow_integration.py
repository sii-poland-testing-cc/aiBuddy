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
from typing import Any, Dict, List, Tuple

from app.utils.json_utils import strip_fences

logger = logging.getLogger("ai_buddy.audit_integration")


async def extract_requirements_from_registry(
    project_id: str,
    rag_context: str,
    llm: Any = None,
) -> Tuple[List[str], List[Dict]]:
    from app.db.engine import AsyncSessionLocal
    try:
        from app.db.requirements_models import Requirement
    except ImportError:
        logger.info("Requirements models not available - using legacy extraction")
        return await _legacy_extract(rag_context, llm), []
    try:
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            stmt = (
                select(Requirement)
                .where(Requirement.project_id == project_id)
                .where(Requirement.level.in_(["functional_req", "acceptance_criterion"]))
                .order_by(Requirement.created_at)
            )
            rows = (await db.execute(stmt)).scalars().all()
            if rows:
                logger.info("project=%s - loaded %d requirements from Faza 2 registry", project_id, len(rows))
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
            logger.info("project=%s - no Faza 2 registry, falling back to LLM", project_id)
    except Exception as exc:
        logger.warning("Failed to load requirements registry: %s", exc)
    return await _legacy_extract(rag_context, llm), []


async def _legacy_extract(rag_context: str, llm: Any) -> List[str]:
    if not llm:
        return ["FR-001", "FR-002", "FR-003"]
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
        import re
        for match in reversed(list(re.finditer(r"\[.*?\]", raw, re.DOTALL))):
            try:
                items = json.loads(match.group())
                return [r for r in items if not str(r).upper().startswith("TC-")]
            except json.JSONDecodeError:
                continue
        return json.loads(raw)
    except Exception:
        return []


async def compute_registry_coverage(
    project_id: str,
    cases: List[Dict],
    rag_context: str,
    llm: Any = None,
) -> Dict[str, Any]:
    """
    Enhanced coverage computation. Priority:
      1. Faza 5+6 persisted scores -> return immediately (best quality)
      2. Faza 2 registry -> live matching
      3. Legacy LLM extraction -> original behavior
    """
    # Priority 1: Try Faza 5+6 persisted scores
    persisted = await _load_persisted_scores(project_id)
    if persisted:
        logger.info("project=%s - using Faza 5+6 persisted scores (%d reqs)", project_id, persisted["requirements_total"])
        return persisted

    # Priority 2+3: Faza 2 registry or legacy extraction
    req_ids, req_details = await extract_requirements_from_registry(project_id, rag_context, llm)

    if not req_ids:
        return {
            "requirements_from_docs": [], "requirements_covered": [],
            "coverage_pct": 0.0, "requirements_total": 0,
            "requirements_covered_count": 0, "requirements_uncovered": [],
            "registry_available": False, "per_requirement_scores": [],
        }

    covered = await _match_requirements_to_tests(cases, req_ids, req_details, llm)

    total = len(req_ids)
    n_covered = len(set(covered) & set(req_ids))
    uncovered = [r for r in req_ids if r not in set(covered)]
    coverage_pct = round((n_covered / total) * 100, 1) if total else 0.0

    per_req_scores = []
    if req_details:
        covered_set = set(covered)
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


async def _load_persisted_scores(project_id: str) -> Dict[str, Any] | None:
    """Try loading Faza 5+6 persisted coverage scores. Returns None if none exist."""
    try:
        from app.db.engine import AsyncSessionLocal
        from app.db.requirements_models import CoverageScore, Requirement
        from sqlalchemy import select

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


async def _match_requirements_to_tests(
    cases: List[Dict], req_ids: List[str], req_details: List[Dict], llm: Any,
) -> List[str]:
    if not req_ids:
        return []
    covered: set = set()
    for case in cases:
        text = " ".join(str(v) for v in case.values() if isinstance(v, str))
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
                import re
                for match in reversed(list(re.finditer(r"\[.*?\]", raw, re.DOTALL))):
                    try:
                        covered.update(json.loads(match.group()))
                        break
                    except json.JSONDecodeError:
                        continue
            except Exception as exc:
                logger.warning("LLM requirement matching failed: %s", exc)
    return list(covered)
