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
"""

import json
import logging
from dataclasses import dataclass, field
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

logger = logging.getLogger("ai_buddy.audit")


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
    duplicates: List[Dict]
    untagged: List[Dict]
    coverage_pct: float
    recommendations: List[str]
    rag_sources: List[Dict]   # [{"filename": str, "excerpt": str}]


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
            cases = await self._parse_file(path)
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
        duplicates = self._find_duplicates(cases)

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

        requirements_from_docs = await self._extract_requirements(rag_context)
        await ctx.store.set("requirements_from_docs", requirements_from_docs)
        logger.info("Requirements found in docs: %s", requirements_from_docs)

        covered = await self._requirements_in_tests(cases, requirements_from_docs)
        await ctx.store.set("requirements_covered", covered)
        logger.info("Requirements covered by tests: %s", covered)

        recommendations = await self._llm_recommendations(cases, rag_context, user_message)
        coverage_pct = max(0.0, 100.0 - (len(untagged) / max(len(cases), 1)) * 100)

        ctx.write_event_to_stream(
            AnalysisProgressEvent(message="Generating report…", progress=0.9)
        )

        return AuditResultEvent(
            duplicates=duplicates,
            untagged=untagged,
            coverage_pct=round(coverage_pct, 1),
            recommendations=recommendations,
            rag_sources=rag_sources,
        )

    # ── Step 3: Report ────────────────────────────────────────────────────────

    @step
    async def report(self, ctx: Context, ev: AuditResultEvent) -> StopEvent:
        project_id = await ctx.store.get("project_id")

        report = {
            "project_id": project_id,
            "summary": {
                "duplicates_found": len(ev.duplicates),
                "untagged_cases": len(ev.untagged),
                "coverage_pct": ev.coverage_pct,
            },
            "duplicates": ev.duplicates,
            "untagged": ev.untagged,
            "recommendations": ev.recommendations,
            "rag_sources": ev.rag_sources,
            "next_tier": "optimize" if ev.coverage_pct >= 50 else "regenerate",
        }

        return StopEvent(result=report)

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _parse_file(self, path: str) -> List[Dict]:
        """Parse .xlsx / .csv / .json / .feature into a uniform dict list."""
        ext = path.rsplit(".", 1)[-1].lower()
        if ext in ("xlsx", "csv"):
            return await self._parse_spreadsheet(path)
        elif ext == "json":
            return await self._parse_json(path)
        elif ext == "feature":
            return await self._parse_gherkin(path)
        return []

    async def _parse_spreadsheet(self, path: str) -> List[Dict]:
        import pandas as pd
        df = pd.read_excel(path) if path.endswith(".xlsx") else pd.read_csv(path)
        return df.to_dict(orient="records")

    async def _parse_json(self, path: str) -> List[Dict]:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, list) else [data]

    async def _parse_gherkin(self, path: str) -> List[Dict]:
        # Minimal Gherkin parser – replace with `gherkin` package in production
        cases = []
        with open(path) as f:
            scenario, steps = None, []
            for line in f:
                line = line.strip()
                if line.startswith("Scenario"):
                    if scenario:
                        cases.append({"name": scenario, "steps": steps, "tags": []})
                    scenario, steps = line.split(":", 1)[1].strip(), []
                elif line.startswith(("Given", "When", "Then", "And")):
                    steps.append(line)
            if scenario:
                cases.append({"name": scenario, "steps": steps, "tags": []})
        return cases

    def _find_duplicates(self, cases: List[Dict]) -> List[Dict]:
        seen, dupes = set(), []
        for c in cases:
            key = c.get("name", "").lower().strip()
            if key in seen:
                dupes.append(c)
            seen.add(key)
        return dupes

    async def _requirements_in_tests(
        self, cases: List[Dict], known_reqs: List[str]
    ) -> List[str]:
        """Return which known requirement IDs are mentioned in the test suite."""
        if not known_reqs:
            return []

        # Step A — pattern matching (no LLM needed)
        covered: set[str] = set()
        for case in cases:
            text = " ".join(str(v) for v in case.values() if isinstance(v, str))
            for req in known_reqs:
                if req.lower() in text.lower():
                    covered.add(req)

        # Step B — LLM fallback when pattern matching finds nothing
        if not covered and self.llm:
            prompt = (
                "Given these test cases:\n"
                f"{json.dumps([c.get('name', '') for c in cases[:20]])}\n\n"
                f"And these requirements:\n{known_reqs}\n\n"
                "Which requirements are covered by at least one test case?\n"
                "Return ONLY a valid JSON array of covered requirement IDs."
            )
            try:
                response = await self.llm.acomplete(prompt)
                raw = str(response).strip()
                if raw.startswith("```"):
                    raw = raw.lstrip("```json").lstrip("```").rstrip("```").strip()
                covered = set(json.loads(raw))
            except Exception as exc:
                logger.warning("LLM requirement matching failed: %s", exc)

        return list(covered)

    async def _extract_requirements(self, rag_context: str) -> List[str]:
        """Extract formal requirement IDs (e.g. FR-001) from the RAG context."""
        if not self.llm:
            return ["FR-001", "FR-002", "FR-003"]

        prompt = (
            "Extract all requirement IDs from the documentation below.\n"
            "Return ONLY a valid JSON array of strings, no preamble, no markdown.\n"
            'Examples: ["FR-001", "FR-002", "NFR-Performance"]\n'
            "If no formal IDs exist, return [].\n\n"
            f"Documentation:\n{rag_context}"
        )
        try:
            response = await self.llm.acomplete(prompt)
            raw = str(response).strip()
            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.lstrip("```json").lstrip("```").rstrip("```").strip()
            return json.loads(raw)
        except Exception as exc:
            logger.warning("Could not extract requirements from docs: %s", exc)
            return []

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

        response = await self.llm.acomplete(prompt)
        raw = str(response).strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        try:
            return json.loads(raw)
        except Exception:
            return [raw]
