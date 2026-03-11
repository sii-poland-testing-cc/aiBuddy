"""
Optimize Agent Workflow  (Tier 2 – Optimize)
============================================
Receives the audit report produced by AuditWorkflow plus the original
test-suite file paths, then returns a cleaned, fully-tagged test suite:

  - Duplicates identified in the audit are removed (no re-analysis needed).
  - Cases without tags are assigned tags + priorities by the LLM, with a
    keyword-based heuristic fallback when no LLM is available.
  - A structured change log records every removal and tagging decision.

Events:
  StartEvent  →  PreparedEvent  →  DeduplicatedEvent  →  StopEvent

StartEvent inputs (via workflow.run()):
  project_id   str                – project identifier
  file_paths   list[str]          – original test-suite files (same as audit)
  audit_report dict               – full result dict from AuditWorkflow
"""

import json
from typing import Any, Dict, List

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


# ─── Events ──────────────────────────────────────────────────────────────────

class OptimizeProgressEvent(Event):
    """Streamed to the frontend during each optimization step."""
    message: str
    progress: float  # 0.0 – 1.0


class PreparedEvent(Event):
    """Emitted after test cases are loaded and audit metadata is merged."""
    all_cases: List[Dict[str, Any]]
    duplicate_names: List[str]   # lower-stripped names flagged as duplicates
    untagged_names: List[str]    # lower-stripped names of cases lacking tags


class DeduplicatedEvent(Event):
    """Emitted after all duplicate cases have been dropped."""
    clean_cases: List[Dict[str, Any]]
    removed: List[Dict[str, Any]]


# ─── Workflow ─────────────────────────────────────────────────────────────────

class OptimizeWorkflow(Workflow):
    """
    Three-step workflow:
      1. prepare     – parse original files; extract audit duplicate/tag lists
      2. deduplicate – drop cases whose names appear in the audit's duplicate set
      3. tag         – assign LLM-suggested (or heuristic) tags + priorities
    """

    def __init__(self, llm=None, **kwargs):
        super().__init__(**kwargs)
        self.llm = llm
        self.context_builder = ContextBuilder()

    # ── Step 1: Prepare ───────────────────────────────────────────────────────

    @step
    async def prepare(self, ctx: Context, ev: StartEvent) -> PreparedEvent:
        project_id: str = ev.get("project_id", "unknown")
        file_paths: List[str] = ev.get("file_paths", [])
        audit_report: Dict[str, Any] = ev.get("audit_report") or {}

        await ctx.store.set("project_id", project_id)
        await ctx.store.set("audit_report", audit_report)

        # Re-parse the original files to get the complete test suite.
        # The audit report only stores flagged subsets, not all cases.
        all_cases: List[Dict] = []
        for path in file_paths:
            all_cases.extend(await self._parse_file(path))

        ctx.write_event_to_stream(
            OptimizeProgressEvent(
                message=f"Loaded {len(all_cases)} test cases from {len(file_paths)} file(s)",
                progress=0.15,
            )
        )

        duplicate_names = [
            d.get("name", "").lower().strip()
            for d in audit_report.get("duplicates", [])
        ]
        untagged_names = [
            u.get("name", "").lower().strip()
            for u in audit_report.get("untagged", [])
        ]

        return PreparedEvent(
            all_cases=all_cases,
            duplicate_names=duplicate_names,
            untagged_names=untagged_names,
        )

    # ── Step 2: Deduplicate ───────────────────────────────────────────────────

    @step
    async def deduplicate(self, ctx: Context, ev: PreparedEvent) -> DeduplicatedEvent:
        ctx.write_event_to_stream(
            OptimizeProgressEvent(message="Removing duplicate test cases…", progress=0.35)
        )

        duplicate_set = set(ev.duplicate_names)
        seen: set = set()
        clean_cases: List[Dict] = []
        removed: List[Dict] = []

        for case in ev.all_cases:
            key = case.get("name", "").lower().strip()
            if key in duplicate_set or key in seen:
                removed.append(case)
            else:
                clean_cases.append(case)
                seen.add(key)

        ctx.write_event_to_stream(
            OptimizeProgressEvent(
                message=f"Removed {len(removed)} duplicate(s) — {len(clean_cases)} cases remain",
                progress=0.5,
            )
        )

        await ctx.store.set("untagged_names", ev.untagged_names)
        return DeduplicatedEvent(clean_cases=clean_cases, removed=removed)

    # ── Step 3: Tag ───────────────────────────────────────────────────────────

    @step
    async def tag(self, ctx: Context, ev: DeduplicatedEvent) -> StopEvent:
        project_id = await ctx.store.get("project_id")
        audit_report = await ctx.store.get("audit_report")
        untagged_names: set = set(await ctx.store.get("untagged_names"))

        ctx.write_event_to_stream(
            OptimizeProgressEvent(
                message="Retrieving RAG context for tag assignment…", progress=0.65
            )
        )
        rag_context = await self.context_builder.build(
            project_id, query="test case categories priorities smoke regression"
        )

        ctx.write_event_to_stream(
            OptimizeProgressEvent(
                message="Assigning tags and priorities…", progress=0.8
            )
        )
        optimized_suite, tagging_log = await self._assign_tags(
            ev.clean_cases, untagged_names, rag_context
        )

        ctx.write_event_to_stream(
            OptimizeProgressEvent(message="Building optimized suite…", progress=0.95)
        )

        original_count = len(ev.clean_cases) + len(ev.removed)
        result = {
            "project_id": project_id,
            "summary": {
                "original_count": original_count,
                "duplicates_removed": len(ev.removed),
                "cases_tagged": len(tagging_log),
                "final_count": len(optimized_suite),
                "coverage_pct": audit_report.get("summary", {}).get("coverage_pct", 0.0),
            },
            "optimized_suite": optimized_suite,
            "changes": {
                "removed": ev.removed,
                "tagged": tagging_log,
            },
            "next_tier": "regenerate",
        }
        return StopEvent(result=result)

    # ── Private: file parsing (mirrors AuditWorkflow) ─────────────────────────

    async def _parse_file(self, path: str) -> List[Dict]:
        ext = path.rsplit(".", 1)[-1].lower()
        if ext in ("xlsx", "csv"):
            return await self._parse_spreadsheet(path)
        if ext == "json":
            return await self._parse_json(path)
        if ext == "feature":
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

    # ── Private: tagging ──────────────────────────────────────────────────────

    async def _assign_tags(
        self,
        cases: List[Dict],
        untagged_names: set,
        rag_context: str,
    ) -> tuple[List[Dict], List[Dict]]:
        """
        Walk through clean_cases. For each case whose name is in untagged_names
        (and has no existing tags), call the LLM (or heuristic) to suggest tags
        and a priority. Returns (updated cases, change log).
        """
        tagging_log: List[Dict] = []
        updated: List[Dict] = []

        for case in cases:
            key = case.get("name", "").lower().strip()
            if key not in untagged_names or case.get("tags"):
                updated.append(case)
                continue

            suggestion = await self._suggest_tags(case, rag_context)
            case = {**case, "tags": suggestion["tags"], "priority": suggestion["priority"]}
            tagging_log.append({
                "name": case.get("name"),
                "assigned_tags": suggestion["tags"],
                "assigned_priority": suggestion["priority"],
            })
            updated.append(case)

        return updated, tagging_log

    async def _suggest_tags(self, case: Dict, rag_context: str) -> Dict:
        """Return {"tags": [...], "priority": "P1|P2|P3"} for one test case."""
        if not self.llm:
            return self._heuristic_tags(case)

        prompt = (
            "You are a senior QA engineer. Assign tags and a priority to the test case below.\n\n"
            f"Project context (from documentation):\n{rag_context[:2000]}\n\n"
            f"Test case:\n{json.dumps(case, indent=2, default=str)}\n\n"
            'Respond ONLY with a JSON object: {"tags": ["tag1", "tag2"], "priority": "P1|P2|P3"}\n'
            "Choose tags from: smoke, regression, critical, payment, ui, api, integration, unit, e2e"
        )

        try:
            response = await self.llm.acomplete(prompt)
            parsed = json.loads(str(response))
            return {
                "tags": parsed.get("tags", []),
                "priority": parsed.get("priority", "P3"),
            }
        except Exception:
            return self._heuristic_tags(case)

    @staticmethod
    def _heuristic_tags(case: Dict) -> Dict:
        """Keyword-based fallback used when no LLM is configured."""
        text = " ".join(
            filter(None, [case.get("name", ""), *( case.get("steps") or [])])
        ).lower()

        tags: List[str] = []
        if any(w in text for w in ("login", "auth", "password", "token", "session")):
            tags.append("smoke")
        if any(w in text for w in ("payment", "checkout", "invoice", "price", "cart")):
            tags.extend(["payment", "critical"])
        if any(w in text for w in ("api", "endpoint", "request", "response", "http")):
            tags.append("api")
        if any(w in text for w in ("ui", "click", "button", "page", "screen", "form")):
            tags.append("ui")
        if any(w in text for w in ("integration", "service", "contract")):
            tags.append("integration")
        if not tags:
            tags.append("regression")

        priority = (
            "P1" if any(t in tags for t in ("critical", "smoke"))
            else "P2" if "payment" in tags
            else "P3"
        )
        return {"tags": list(dict.fromkeys(tags)), "priority": priority}
