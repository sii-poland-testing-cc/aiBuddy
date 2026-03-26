"""
M1: Context Builder Workflow
=============================
Pipeline:
  Start → Parse → Embed → Extract → Review → Assemble → Stop

Outputs (all three):
  1. RAG knowledge base  (Chroma via existing ContextBuilder)
  2. Domain mind map     (JSON: nodes + edges)
  3. Auto-glossary       (list of {term, definition, source, related_terms})

NOTE: Uses LlamaIndex Workflow Context API v0.14+
  Write: await ctx.store.set("key", value)
  Read:  value = await ctx.store.get("key")
"""

import asyncio
import json
import logging
from pathlib import Path
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
from app.parsers.document_parser import DocumentParser
from app.rag.context_builder import ContextBuilder
from app.utils.json_utils import strip_fences

logger = logging.getLogger("ai_buddy.m1")

_EXTRACT_MAX_RETRIES = 2


# ─── Events ──────────────────────────────────────────────────────────────────

class ParsedDocsEvent(Event):
    docs: List[Dict[str, Any]]   # [{filename, text, tables, headings, metadata}]


class EmbeddedEvent(Event):
    project_id: str
    chunk_count: int


class ExtractedEvent(Event):
    entities: List[Dict]
    relations: List[Dict]
    terms: List[Dict]


class ReviewedEvent(Event):
    """Output of the Review step — replaces ExtractedEvent going into Assemble."""
    entities: List[Dict]
    relations: List[Dict]
    terms: List[Dict]


class ProgressEvent(Event):
    message: str
    progress: float              # 0.0–1.0
    stage: str                   # "parse" | "embed" | "extract" | "review" | "assemble"


# ─── Workflow ─────────────────────────────────────────────────────────────────

class ContextBuilderWorkflow(Workflow):
    """
    M1 pipeline. Returns:
    {
      "project_id": str,
      "rag_ready": bool,
      "mind_map": {"nodes": [...], "edges": [...]},
      "glossary": [{term, definition, source, related_terms}],
      "stats": {entity_count, relation_count, term_count}
    }
    """

    def __init__(self, llm=None, **kwargs):
        super().__init__(**kwargs)
        self.llm = llm
        self.parser = DocumentParser()
        self.context_builder = ContextBuilder()
        # Initialised here with limit=1 as a safe default; replaced at the
        # start of the extract step with settings.LLM_CONCURRENT_CALLS so that
        # ALL LLM calls across all batches, phases, and reflection cycles share
        # one concurrency limit. Initialising in __init__ avoids the
        # "sem is None" guard that previously existed in _llm_call.
        self._llm_sem = asyncio.Semaphore(1)

    # ── Step 1: Parse ─────────────────────────────────────────────────────────

    @step
    async def parse(self, ctx: Context, ev: StartEvent) -> ParsedDocsEvent:
        file_paths: List[str] = ev.get("file_paths", [])
        project_id: str = ev.get("project_id", "default")
        work_context_id: Optional[str] = ev.get("work_context_id", None)

        await ctx.store.set("project_id", project_id)
        await ctx.store.set("work_context_id", work_context_id)

        ctx.write_event_to_stream(ProgressEvent(
            message=f"Parsing {len(file_paths)} document(s)…",
            progress=0.05, stage="parse"
        ))

        docs = []
        for path in file_paths:
            try:
                doc = await self.parser.parse(path)
                docs.append(doc)
                ctx.write_event_to_stream(ProgressEvent(
                    message=f"✓ Parsed: {Path(path).name}",
                    progress=0.05 + 0.15 * (len(docs) / max(len(file_paths), 1)),
                    stage="parse"
                ))
            except Exception as e:
                logger.warning(f"Failed to parse {path}: {e}")

        return ParsedDocsEvent(docs=docs)

    # ── Step 2: Embed into RAG ────────────────────────────────────────────────

    @step
    async def embed(self, ctx: Context, ev: ParsedDocsEvent) -> EmbeddedEvent:
        project_id = await ctx.store.get("project_id")
        await ctx.store.set("docs", ev.docs)

        ctx.write_event_to_stream(ProgressEvent(
            message="Chunking & embedding documents into knowledge base…",
            progress=0.25, stage="embed"
        ))

        # Use existing ContextBuilder — index_from_docs indexes already-parsed text
        chunk_count = await self.context_builder.index_from_docs(
            project_id=project_id,
            docs=ev.docs
        )

        ctx.write_event_to_stream(ProgressEvent(
            message=f"✓ Indexed {chunk_count} chunks into RAG knowledge base",
            progress=0.45, stage="embed"
        ))

        return EmbeddedEvent(project_id=project_id, chunk_count=chunk_count)

    # ── Step 3: LLM Extraction ────────────────────────────────────────────────

    @step
    async def extract(self, ctx: Context, ev: EmbeddedEvent) -> ExtractedEvent:
        docs: List[Dict] = await ctx.store.get("docs")
        combined = self._combine_text(docs)
        batches = self._split_batches(combined)
        total_batches = len(batches)

        ctx.write_event_to_stream(ProgressEvent(
            message=f"Extracting entities + glossary from {total_batches} batch(es) in parallel…",
            progress=0.50, stage="extract"
        ))

        # Replace semaphore at run start so all LLM calls in this run share one limit.
        self._llm_sem = asyncio.Semaphore(settings.LLM_CONCURRENT_CALLS)

        results = await asyncio.gather(
            *[self._extract_batch(b) for b in batches],
            return_exceptions=True,
        )

        entity_batches: List[List[Dict]] = []
        relation_batches: List[List[Dict]] = []
        term_batches: List[List[Dict]] = []
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                raise RuntimeError(
                    f"Context extraction failed on batch {i + 1}/{total_batches} "
                    f"after {_EXTRACT_MAX_RETRIES} attempts: {res}"
                ) from res
            else:
                e, r, t = res  # type: ignore[misc]
                entity_batches.append(e)
                relation_batches.append(r)
                term_batches.append(t)

        ctx.write_event_to_stream(ProgressEvent(
            message=f"✓ All {total_batches} batch(es) complete — merging results…",
            progress=0.72, stage="extract"
        ))

        entities = self._merge_entities(entity_batches)
        relations = self._merge_relations(list(zip(entity_batches, relation_batches)), entities)
        terms = self._merge_terms(term_batches)

        ctx.write_event_to_stream(ProgressEvent(
            message=f"✓ Found {len(entities)} concepts, {len(relations)} relationships, {len(terms)} glossary terms",
            progress=0.80, stage="extract"
        ))

        return ExtractedEvent(entities=entities, relations=relations, terms=terms)

    # ── Step 4: Review (Producer-Reviewer reflection) ─────────────────────────

    @step
    async def review(self, ctx: Context, ev: ExtractedEvent) -> ReviewedEvent:
        max_iter = settings.REFLECTION_MAX_ITERATIONS
        if max_iter == 0 or not self.llm:
            # Reflection disabled or no LLM — pass through
            return ReviewedEvent(
                entities=ev.entities,
                relations=ev.relations,
                terms=ev.terms,
            )

        docs: List[Dict] = await ctx.store.get("docs")
        source_sample = self._combine_text(docs)[:6_000]

        entities, relations, terms = ev.entities, ev.relations, ev.terms

        for iteration in range(1, max_iter + 1):
            ctx.write_event_to_stream(ProgressEvent(
                message=f"Reviewing extracted knowledge (pass {iteration}/{max_iter})…",
                progress=0.82 + 0.04 * (iteration - 1),
                stage="review",
            ))

            issues = await self._review_extraction(source_sample, entities, relations, terms)
            if not isinstance(issues, dict):
                issues = {"verdict": "APPROVED"}

            if issues.get("verdict") == "APPROVED":
                ctx.write_event_to_stream(ProgressEvent(
                    message=f"✓ Knowledge approved on pass {iteration}",
                    progress=0.82 + 0.04 * iteration,
                    stage="review",
                ))
                break

            issue_count = (
                len(issues.get("missing_entities", []))
                + len(issues.get("duplicate_entities", []))
                + len(issues.get("missing_terms", []))
                + len(issues.get("vague_definitions", []))
                + len(issues.get("orphan_nodes", []))
            )
            ctx.write_event_to_stream(ProgressEvent(
                message=f"Reviewer found {issue_count} issue(s) — refining…",
                progress=0.82 + 0.04 * iteration,
                stage="review",
            ))

            entities, relations, terms = await self._refine_extraction(
                source_sample, entities, relations, terms, issues
            )

        return ReviewedEvent(entities=entities, relations=relations, terms=terms)

    # ── Step 5: Assemble ──────────────────────────────────────────────────────

    @step
    async def assemble(self, ctx: Context, ev: ReviewedEvent) -> StopEvent:
        project_id = await ctx.store.get("project_id")
        work_context_id: Optional[str] = await ctx.store.get("work_context_id")

        ctx.write_event_to_stream(ProgressEvent(
            message="Assembling mind map and glossary…",
            progress=0.88, stage="assemble"
        ))

        mind_map = self._build_mind_map(ev.entities, ev.relations)
        glossary = self._normalise_glossary(ev.terms)

        ctx.write_event_to_stream(ProgressEvent(
            message="✅ Context built successfully!",
            progress=1.0, stage="assemble"
        ))

        return StopEvent(result={
            "project_id": project_id,
            "work_context_id": work_context_id,
            "rag_ready": True,
            "mind_map": mind_map,
            "glossary": glossary,
            "stats": {
                "entity_count": len(ev.entities),
                "relation_count": len(ev.relations),
                "term_count": len(glossary),
            }
        })

    # ── LLM calls ─────────────────────────────────────────────────────────────

    async def _llm_call(self, prompt: str, max_tokens: int = 4096) -> str:
        """Semaphore-guarded LLM call. Semaphore is set in extract() so all LLM
        calls across all batches, phases, and reflection cycles share one limit."""
        async with self._llm_sem:
            return str(await self.llm.acomplete(prompt, max_tokens=max_tokens))  # type: ignore[union-attr]

    async def _extract_batch(self, text: str):
        """Run entity extraction and two-phase glossary extraction concurrently."""
        (entities, relations), terms = await asyncio.gather(
            self._extract_entities_batch(text),
            self._extract_glossary_batch(text),
        )
        return entities, relations, terms

    async def _extract_entities_batch(self, text: str, _depth: int = 0):
        """
        Extract entities + relations from one text batch.
        On JSONDecodeError (truncated response) at depth 0, splits the batch in half
        and retries each half — adaptive rather than identical retry.
        """
        if not self.llm:
            return self._mock_entities(), self._mock_relations()

        prompt = f"""You are a domain analyst reviewing software QA documentation.
Extract all significant domain entities and their relationships from the text below.
Keep each description under 15 words. Prefer specificity over completeness.

Return ONLY valid JSON — no preamble, no markdown fences, no commentary:
{{
  "entities": [
    {{"id": "e1", "name": "...", "type": "process|actor|system|data|rule", "description": "..."}}
  ],
  "relations": [
    {{"source": "e1", "target": "e2", "label": "..."}}
  ]
}}

Documentation:
{text}
"""
        last_exc: Exception = RuntimeError("no attempts made")
        for attempt in range(_EXTRACT_MAX_RETRIES):
            try:
                raw = strip_fences(await self._llm_call(prompt, max_tokens=4096))
                data = json.loads(raw)
                return data.get("entities", []), data.get("relations", [])
            except json.JSONDecodeError as exc:
                last_exc = exc
                # Adaptive split — retrying identical input never fixes truncation.
                # Split the batch in half and merge results from each half instead.
                if attempt == 0 and _depth == 0:
                    logger.warning("_extract_entities_batch: truncated response — split-retrying batch")
                    mid = len(text) // 2
                    sub = await asyncio.gather(
                        self._extract_entities_batch(text[:mid], _depth=1),
                        self._extract_entities_batch(text[mid:], _depth=1),
                        return_exceptions=True,
                    )
                    if not any(isinstance(r, Exception) for r in sub):
                        all_e: List[Dict] = []
                        all_r: List[Dict] = []
                        for sub_e, sub_r in sub:  # type: ignore[misc]
                            all_e.extend(sub_e)
                            all_r.extend(sub_r)
                        logger.info("_extract_entities_batch: split-retry recovered %d entities", len(all_e))
                        return all_e, all_r
                logger.warning("_extract_entities_batch attempt %d failed: %s: %s", attempt + 1, type(exc).__name__, exc)
            except Exception as exc:
                last_exc = exc
                logger.warning("_extract_entities_batch attempt %d failed: %s: %s", attempt + 1, type(exc).__name__, exc)
        raise last_exc

    async def _extract_glossary_batch(self, text: str) -> List[Dict]:
        """
        Two-phase glossary extraction.

        Phase 1 — enumerate: ask for term *names only* (output ≤ ~10 tokens/name,
          max_tokens=1024 → handles up to ~100 names; never truncates).
        Phase 2 — define: split names into groups of M1_GLOSSARY_TERMS_PER_GROUP and
          request definitions in parallel. Each group call output is bounded
          (300 tokens × group_size) so it always fits within max_tokens.

        This eliminates the "unbounded glossary JSON" truncation class entirely.
        """
        if not self.llm:
            return self._mock_glossary()

        # ── Phase 1: enumerate term names ─────────────────────────────────────
        term_names = await self._enumerate_term_names(text)
        if not term_names:
            logger.warning("_extract_glossary_batch: phase 1 returned no terms")
            return []

        # ── Phase 2: define terms in parallel groups ──────────────────────────
        group_size = settings.M1_GLOSSARY_TERMS_PER_GROUP
        groups = [
            term_names[i: i + group_size]
            for i in range(0, len(term_names), group_size)
        ]
        results = await asyncio.gather(
            *[self._define_term_group(text, group, term_names) for group in groups],
            return_exceptions=True,
        )

        terms: List[Dict] = []
        seen: set = set()
        for r in results:
            if isinstance(r, list):
                for t in r:
                    key = t.get("term", "").strip().lower()
                    if key and key not in seen:
                        seen.add(key)
                        terms.append(t)
            elif isinstance(r, Exception):
                logger.warning("_define_term_group failed: %s", r)

        logger.info("_extract_glossary_batch: two-phase extracted %d terms", len(terms))
        return terms

    async def _enumerate_term_names(self, text: str) -> List[str]:
        """
        Phase 1 of glossary extraction: return only term names as a string array.
        Output is always small (~10 tokens/name) so max_tokens=1024 handles ≤100 names.
        """
        prompt = f"""List every important domain-specific term in this QA/software documentation.
Return ONLY a JSON array of term name strings — no definitions, no extra fields:
["Term A", "Term B", "Term C"]

Include: domain concepts, process names, roles, system components, QA methodologies,
         requirement IDs, data entities, acronyms, tool names.
Exclude: common English words, generic verbs, basic programming terms, formatting artifacts.

Documentation:
{text}
"""
        last_exc: Exception = RuntimeError("no attempts made")
        for attempt in range(_EXTRACT_MAX_RETRIES):
            try:
                raw = strip_fences(await self._llm_call(prompt, max_tokens=1024))
                names = json.loads(raw)
                if isinstance(names, list):
                    return [str(n).strip() for n in names if n and str(n).strip()]
            except Exception as exc:
                last_exc = exc
                logger.warning("_enumerate_term_names attempt %d failed: %s: %s", attempt + 1, type(exc).__name__, exc)
        raise last_exc

    async def _define_term_group(
        self,
        text: str,
        group: List[str],
        all_term_names: List[str],
    ) -> List[Dict]:
        """
        Phase 2 of glossary extraction: define a bounded group of terms.
        max_tokens = 300 × group_size + 256 — always fits for groups ≤ M1_GLOSSARY_TERMS_PER_GROUP.
        """
        terms_list = "\n".join(f"- {t}" for t in group)
        known_json = json.dumps(all_term_names[:80], ensure_ascii=False)
        prompt = f"""Write glossary definitions for the following terms, based on the documentation below.

Terms to define:
{terms_list}

All known domain terms (use for the related_terms field — only reference terms from this list):
{known_json}

Return ONLY a JSON array — one object per term:
[
  {{
    "term": "exact term name from the list above",
    "definition": "1-2 sentence definition grounded in the documentation",
    "related_terms": ["related term from the known list above"],
    "source": "uploaded documentation"
  }}
]

Documentation:
{text}
"""
        max_out = 300 * len(group) + 256
        try:
            raw = strip_fences(await self._llm_call(prompt, max_tokens=max_out))
            try:
                result = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("_define_term_group: could not parse response for group %s", group)
                return []
            if isinstance(result, list):
                return [t for t in result if isinstance(t, dict) and t.get("term") and t.get("definition")]
        except Exception as exc:
            logger.warning("_define_term_group failed for group %s: %s", group, exc)
        return []

    # ── Reflection helpers ────────────────────────────────────────────────────

    async def _review_extraction(
        self,
        source_sample: str,
        entities: List[Dict],
        relations: List[Dict],
        terms: List[Dict],
    ) -> Dict:
        """Critic call: evaluate quality of extracted entities + glossary."""
        entities_json = json.dumps(entities[:60], ensure_ascii=False)
        relations_json = json.dumps(relations[:80], ensure_ascii=False)
        terms_json = json.dumps(terms[:60], ensure_ascii=False)

        prompt = f"""You are a senior domain knowledge architect performing a critical quality review.
You will be given:
1. A sample of the source documentation
2. Extracted domain entities and relationships (mind map)
3. Extracted glossary terms

Your task: find flaws. Be specific, not exhaustive. Focus on the most impactful issues only.

Return ONLY valid JSON — no preamble, no markdown fences:
{{
  "verdict": "APPROVED" | "NEEDS_REVISION",
  "missing_entities": ["name of entity clearly present in source but not extracted"],
  "duplicate_entities": [["name1", "name2"]],
  "orphan_nodes": ["entity id with no edges"],
  "missing_terms": ["term clearly in source but absent from glossary"],
  "vague_definitions": [{{"term": "...", "issue": "why the definition is insufficient"}}]
}}

Rules:
- Return "APPROVED" when you find no meaningful issues.
- List at most 5 items per category — prioritise the most impactful gaps.
- Do NOT invent entities or terms not present in the source.

Source documentation (sample):
{source_sample}

Extracted entities ({len(entities)} total):
{entities_json}

Extracted relations ({len(relations)} total):
{relations_json}

Glossary terms ({len(terms)} total):
{terms_json}
"""
        try:
            raw = strip_fences(await self._llm_call(prompt))
            return json.loads(raw)
        except Exception as exc:
            logger.warning("Review LLM call failed (%s) — treating as APPROVED", exc)
            return {"verdict": "APPROVED"}

    async def _refine_extraction(
        self,
        source_sample: str,
        entities: List[Dict],
        relations: List[Dict],
        terms: List[Dict],
        issues: Dict,
    ) -> tuple:
        """Per-issue parallel refinement — delegates each category to a focused helper."""
        import copy

        entities = copy.deepcopy(entities)
        relations = copy.deepcopy(relations)
        terms = copy.deepcopy(terms)

        # Hard cap per category — prevents runaway LLM calls on rich documents.
        # Reviewer prompt already says "list at most 5" but LLMs don't always comply.
        _MAX = 5

        entities, relations = await self._apply_missing_entities(
            entities, relations, issues.get("missing_entities", [])[:_MAX], source_sample
        )
        entities, relations = self._apply_duplicate_merges(
            entities, relations, issues.get("duplicate_entities", [])
        )
        terms = await self._apply_missing_terms(
            terms, issues.get("missing_terms", [])[:_MAX], source_sample
        )
        terms = await self._apply_vague_fixes(
            terms, issues.get("vague_definitions", [])[:_MAX], source_sample
        )

        return entities, relations, terms

    async def _apply_missing_entities(
        self,
        entities: List[Dict],
        relations: List[Dict],
        missing: List[str],
        source_sample: str,
    ) -> tuple:
        """Add entities identified by the critic as missing."""
        if not missing or not self.llm:
            return entities, relations

        next_id = len(entities) + 1
        new_entity_results = await asyncio.gather(
            *[self._create_entity_llm(source_sample, name) for name in missing],
            return_exceptions=True,
        )
        for name, result in zip(missing, new_entity_results):
            if isinstance(result, dict):
                result["id"] = f"e{next_id}"
            else:
                result = {"id": f"e{next_id}", "name": name, "type": "concept", "description": ""}
            entities.append(result)
            next_id += 1

        return entities, relations

    def _apply_duplicate_merges(
        self,
        entities: List[Dict],
        relations: List[Dict],
        duplicates: List,
    ) -> tuple:
        """Merge entity pairs flagged as duplicates, re-wiring relations to the kept entity."""
        for pair in duplicates:
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                continue
            name_a, name_b = str(pair[0]), str(pair[1])
            idx_a = next((i for i, e in enumerate(entities) if e.get("name", "").lower() == name_a.lower()), None)
            idx_b = next((i for i, e in enumerate(entities) if e.get("name", "").lower() == name_b.lower()), None)
            if idx_a is None or idx_b is None or idx_a == idx_b:
                continue
            keep, drop = (
                (idx_a, idx_b)
                if len(entities[idx_a].get("description", "")) >= len(entities[idx_b].get("description", ""))
                else (idx_b, idx_a)
            )
            drop_id = entities[drop]["id"]
            keep_id = entities[keep]["id"]
            for r in relations:
                if r.get("source") == drop_id:
                    r["source"] = keep_id
                if r.get("target") == drop_id:
                    r["target"] = keep_id
            entities.pop(drop)

        return entities, relations

    async def _apply_missing_terms(
        self,
        terms: List[Dict],
        missing_terms: List[str],
        source_sample: str,
    ) -> List[Dict]:
        """Add glossary terms identified by the critic as missing."""
        if not missing_terms or not self.llm:
            return terms

        new_term_results = await asyncio.gather(
            *[self._create_term_llm(source_sample, t) for t in missing_terms],
            return_exceptions=True,
        )
        existing_keys = {t.get("term", "").lower() for t in terms}
        for result in new_term_results:
            if isinstance(result, dict) and result.get("term", "").lower() not in existing_keys:
                terms.append(result)
                existing_keys.add(result.get("term", "").lower())

        return terms

    async def _apply_vague_fixes(
        self,
        terms: List[Dict],
        vague: List,
        source_sample: str,
    ) -> List[Dict]:
        """Improve definitions flagged as vague by the critic."""
        if not vague or not self.llm:
            return terms

        vague_dicts = [v if isinstance(v, dict) else {"term": str(v), "issue": ""} for v in vague]
        fixed_results = await asyncio.gather(
            *[self._fix_term_llm(source_sample, v) for v in vague_dicts],
            return_exceptions=True,
        )
        term_map = {t.get("term", "").lower(): i for i, t in enumerate(terms)}
        for vague_item, fixed in zip(vague_dicts, fixed_results):
            if isinstance(fixed, dict):
                key = vague_item.get("term", "").lower()
                if key in term_map:
                    idx = term_map[key]
                    terms[idx]["definition"] = fixed.get("definition", terms[idx].get("definition", ""))

        return terms

    async def _create_entity_llm(self, source_sample: str, name: str) -> Optional[Dict]:
        prompt = f"""Create a domain entity entry for: "{name}"

Source documentation (excerpt):
{source_sample[:2000]}

Return ONLY a JSON object:
{{"name": "{name}", "type": "process|actor|system|data|rule|concept", "description": "max 15 words"}}
No markdown fences."""
        try:
            raw = strip_fences(await self._llm_call(prompt, max_tokens=256))
            return json.loads(raw)
        except Exception as exc:
            logger.warning("Create entity '%s' failed: %s", name, exc)
            return None

    async def _create_term_llm(self, source_sample: str, term: str) -> Optional[Dict]:
        prompt = f"""Write a glossary entry for the term: "{term}"

Source documentation (excerpt):
{source_sample[:2000]}

Return ONLY a JSON object:
{{"term": "{term}", "definition": "...", "related_terms": [], "source": "uploaded documentation"}}
No markdown fences."""
        try:
            raw = strip_fences(await self._llm_call(prompt, max_tokens=256))
            return json.loads(raw)
        except Exception as exc:
            logger.warning("Create term '%s' failed: %s", term, exc)
            return None

    async def _fix_term_llm(self, source_sample: str, vague_item: Dict) -> Optional[Dict]:
        term = vague_item.get("term", "")
        issue = vague_item.get("issue", "")
        prompt = f"""Improve this glossary definition.
Term: "{term}"
Problem: {issue}

Source documentation (excerpt):
{source_sample[:2000]}

Return ONLY a JSON object:
{{"term": "{term}", "definition": "improved, specific, non-circular definition"}}
No markdown fences."""
        try:
            raw = strip_fences(await self._llm_call(prompt, max_tokens=256))
            return json.loads(raw)
        except Exception as exc:
            logger.warning("Fix term '%s' failed: %s", term, exc)
            return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_mind_map(self, entities: List[Dict], relations: List[Dict]) -> Dict:
        nodes = [
            {
                "id": e.get("id", f"e{i}"),
                "label": e.get("name", "Unknown"),
                "type": e.get("type", "concept"),
                "description": e.get("description", ""),
            }
            for i, e in enumerate(entities)
        ]
        edges = [
            {
                "source": r.get("source"),
                "target": r.get("target"),
                "label": r.get("label", "relates to"),
            }
            for r in relations
        ]
        return {"nodes": nodes, "edges": edges}

    def _normalise_glossary(self, terms: List[Dict]) -> List[Dict]:
        """Set default fields on each glossary term before returning."""
        for term in terms:
            term.setdefault("related_terms", [])
            term.setdefault("source", "uploaded documentation")
        return terms

    def _combine_text(self, docs: List[Dict]) -> str:
        parts = []
        for doc in docs:
            text = doc.get("text", "")
            parts.append(f"=== {doc.get('filename', 'document')} ===\n{text}")
        return "\n\n".join(parts)

    def _split_batches(self, text: str) -> List[str]:
        batch_chars = settings.M1_BATCH_CHARS
        batch_overlap = settings.M1_BATCH_OVERLAP
        if len(text) <= batch_chars:
            return [text]
        batches, start = [], 0
        while start < len(text):
            end = min(start + batch_chars, len(text))
            batches.append(text[start:end])
            start += batch_chars - batch_overlap
        return batches

    def _merge_entities(self, batches: List[List[Dict]]) -> List[Dict]:
        seen: dict = {}
        result: List[Dict] = []
        counter = 1
        for batch in batches:
            for e in batch:
                key = e.get("name", "").strip().lower()
                if key and key not in seen:
                    seen[key] = f"e{counter}"
                    counter += 1
                    result.append({**e, "id": seen[key]})
        return result

    def _merge_relations(
        self,
        batch_pairs: List[tuple],
        entities: List[Dict],
    ) -> List[Dict]:
        """Resolve entity IDs from each batch into master IDs, then dedup relations."""
        master_name_to_id = {e["name"].strip().lower(): e["id"] for e in entities}
        seen: set = set()
        result: List[Dict] = []
        for batch_entities, batch_relations in batch_pairs:
            # Map this batch's local IDs → entity names
            local_id_to_name: dict = {
                e.get("id", ""): e.get("name", "").strip().lower()
                for e in batch_entities
            }
            for r in batch_relations:
                src_name = local_id_to_name.get(r.get("source", ""), "")
                tgt_name = local_id_to_name.get(r.get("target", ""), "")
                master_src = master_name_to_id.get(src_name, r.get("source", ""))
                master_tgt = master_name_to_id.get(tgt_name, r.get("target", ""))
                key = (master_src, master_tgt)
                if key not in seen:
                    seen.add(key)
                    result.append({**r, "source": master_src, "target": master_tgt})
        return result

    def _merge_terms(self, batches: List[List[Dict]]) -> List[Dict]:
        seen: dict = {}
        result: List[Dict] = []
        for batch in batches:
            for t in batch:
                key = t.get("term", "").strip().lower()
                if key and key not in seen:
                    seen[key] = True
                    result.append(t)
        return result

    # ── Mock data (dev without LLM) ───────────────────────────────────────────

    def _mock_entities(self):
        return [
            {"id": "e1", "name": "Test Case",        "type": "data",    "description": "Single executable test scenario"},
            {"id": "e2", "name": "Test Suite",        "type": "data",    "description": "Collection of related test cases"},
            {"id": "e3", "name": "QA Engineer",       "type": "actor",   "description": "Person responsible for quality"},
            {"id": "e4", "name": "Regression Cycle",  "type": "process", "description": "Periodic test execution"},
            {"id": "e5", "name": "Defect",            "type": "data",    "description": "Identified software issue"},
            {"id": "e6", "name": "Requirements",      "type": "data",    "description": "Functional specification"},
            {"id": "e7", "name": "Release",           "type": "process", "description": "Software deployment event"},
            {"id": "e8", "name": "Environment",       "type": "system",  "description": "Target test environment"},
        ]

    def _mock_relations(self):
        return [
            {"source": "e2", "target": "e1", "label": "contains"},
            {"source": "e3", "target": "e2", "label": "maintains"},
            {"source": "e4", "target": "e2", "label": "executes"},
            {"source": "e1", "target": "e6", "label": "validates"},
            {"source": "e4", "target": "e5", "label": "reveals"},
            {"source": "e5", "target": "e7", "label": "blocks"},
            {"source": "e4", "target": "e8", "label": "runs on"},
        ]

    def _mock_glossary(self):
        return [
            {"term": "Test Case",        "definition": "A set of conditions to verify a specific system behaviour.",         "related_terms": ["Test Suite", "Scenario"],        "source": "mock"},
            {"term": "Regression Cycle", "definition": "Scheduled re-execution of tests after code changes.",               "related_terms": ["Test Suite", "Release"],         "source": "mock"},
            {"term": "Coverage",         "definition": "Fraction of requirements or code paths exercised by tests.",         "related_terms": ["Test Case", "Requirements"],    "source": "mock"},
            {"term": "Defect",           "definition": "A deviation from expected system behaviour found during testing.",   "related_terms": ["Bug", "Issue"],                 "source": "mock"},
            {"term": "Bus Factor",       "definition": "Number of team members whose absence would critically impact work.", "related_terms": ["QA Engineer"],                  "source": "mock"},
            {"term": "Smoke Test",       "definition": "Minimal test set verifying basic functionality before full regression.", "related_terms": ["Test Suite"],              "source": "mock"},
        ]
