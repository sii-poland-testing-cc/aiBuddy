"""
M1: Context Builder Workflow
=============================
Pipeline:
  Start → Parse → Embed → Extract → Assemble → Stop

Outputs (all three):
  1. RAG knowledge base  (Chroma via existing ContextBuilder)
  2. Domain mind map     (JSON: nodes + edges)
  3. Auto-glossary       (list of {term, definition, source, related_terms})

NOTE: Uses LlamaIndex Workflow Context API v0.14+
  Write: await ctx.store.set("key", value)
  Read:  value = await ctx.store.get("key")
"""

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

from app.parsers.document_parser import DocumentParser
from app.rag.context_builder import ContextBuilder

logger = logging.getLogger("ai_buddy.m1")


def _strip_fences(text: str) -> str:
    """Remove markdown code fences and find the first valid JSON value."""
    import re
    # Remove ```json ... ``` or ``` ... ``` wrappers
    text = re.sub(r"^```[a-z]*\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)
    # Find first [ or { and trim anything before it
    for i, ch in enumerate(text):
        if ch in ("{", "["):
            return text[i:]
    return text


def _recover_truncated_array(raw: str) -> List[Dict]:
    """
    Attempt to salvage a JSON array that was cut off mid-token (e.g. at max_tokens limit).
    Finds the last complete object `}` inside the array and closes it.
    Returns a list of successfully parsed items, or an empty list on failure.
    """
    # Find rightmost `}` — end of the last potentially complete entry
    last_brace = raw.rfind("}")
    if last_brace == -1:
        return []
    candidate = raw[: last_brace + 1] + "]"
    # Strip any leading non-`[` characters so json.loads sees a valid array
    for i, ch in enumerate(candidate):
        if ch == "[":
            candidate = candidate[i:]
            break
    else:
        return []
    try:
        result = json.loads(candidate)
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
    except json.JSONDecodeError:
        pass
    return []


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
    stage: str                   # "parse" | "embed" | "extract" | "assemble"


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

    BATCH_CHARS = 12_000
    BATCH_OVERLAP = 1_800

    def __init__(self, llm=None, **kwargs):
        super().__init__(**kwargs)
        self.llm = llm
        self.parser = DocumentParser()
        self.context_builder = ContextBuilder()

    # ── Step 1: Parse ─────────────────────────────────────────────────────────

    @step
    async def parse(self, ctx: Context, ev: StartEvent) -> ParsedDocsEvent:
        file_paths: List[str] = ev.get("file_paths", [])
        project_id: str = ev.get("project_id", "default")

        await ctx.store.set("project_id", project_id)

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
        import asyncio
        docs: List[Dict] = await ctx.store.get("docs")
        combined = self._combine_text(docs)
        batches = self._split_batches(combined)
        total_batches = len(batches)

        ctx.write_event_to_stream(ProgressEvent(
            message=f"Extracting entities + glossary from {total_batches} batch(es) in parallel…",
            progress=0.50, stage="extract"
        ))

        # Run batches concurrently (semaphore caps API calls to avoid rate limiting)
        from app.core.config import settings
        sem = asyncio.Semaphore(settings.LLM_CONCURRENT_CALLS)

        async def _guarded(text: str):
            async with sem:
                return await self._extract_batch(text)

        results = await asyncio.gather(
            *[_guarded(b) for b in batches],
            return_exceptions=True,
        )

        entity_batches: List[List[Dict]] = []
        relation_batches: List[List[Dict]] = []
        term_batches: List[List[Dict]] = []
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                raise RuntimeError(
                    f"Context extraction failed on batch {i + 1}/{total_batches} "
                    f"after 2 attempts: {res}"
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
        from app.core.config import settings

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

        ctx.write_event_to_stream(ProgressEvent(
            message="Assembling mind map and glossary…",
            progress=0.88, stage="assemble"
        ))

        mind_map = self._build_mind_map(ev.entities, ev.relations)
        glossary = self._enrich_glossary(ev.terms, ev.entities)

        ctx.write_event_to_stream(ProgressEvent(
            message="✅ Context built successfully!",
            progress=1.0, stage="assemble"
        ))

        return StopEvent(result={
            "project_id": project_id,
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

    async def _extract_batch(self, text: str):
        """Run entity and glossary extraction for one batch concurrently."""
        import asyncio
        (entities, relations), terms = await asyncio.gather(
            self._extract_entities_batch(text),
            self._extract_glossary_batch(text),
        )
        return entities, relations, terms

    async def _extract_entities_batch(self, text: str):
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
        for attempt in range(2):
            try:
                response = await self.llm.acomplete(prompt, max_tokens=4096)
                raw = _strip_fences(str(response).strip())
                data = json.loads(raw)
                return data.get("entities", []), data.get("relations", [])
            except Exception as e:
                last_exc = e
                logger.warning("_extract_entities_batch attempt %d failed: %s: %s", attempt + 1, type(e).__name__, e)
        raise last_exc

    async def _extract_glossary_batch(self, text: str) -> List[Dict]:
        if not self.llm:
            return self._mock_glossary()

        prompt = f"""Extract a domain glossary from this QA documentation.
Return ONLY valid JSON — a list, no preamble, no markdown fences:
[
  {{
    "term": "...",
    "definition": "...",
    "related_terms": ["...", "..."],
    "source": "uploaded documentation"
  }}
]
Include all important domain-specific terms present in the text.

Documentation:
{text}
"""
        last_exc: Exception = RuntimeError("no attempts made")
        for attempt in range(2):
            try:
                response = await self.llm.acomplete(prompt, max_tokens=8192)
                raw = _strip_fences(str(response).strip())
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    # Response may be truncated at token limit — recover partial terms
                    recovered = _recover_truncated_array(raw)
                    if recovered:
                        logger.warning(
                            "_extract_glossary_batch attempt %d: recovered %d term(s) from truncated response",
                            attempt + 1, len(recovered),
                        )
                        return recovered
                    raise
            except Exception as e:
                last_exc = e
                logger.warning("_extract_glossary_batch attempt %d failed: %s: %s", attempt + 1, type(e).__name__, e)
        raise last_exc

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
            response = await self.llm.acomplete(prompt)
            raw = _strip_fences(str(response).strip())
            return json.loads(raw)
        except Exception as e:
            logger.warning("Review LLM call failed (%s) — treating as APPROVED", e)
            return {"verdict": "APPROVED"}

    async def _refine_extraction(
        self,
        source_sample: str,
        entities: List[Dict],
        relations: List[Dict],
        terms: List[Dict],
        issues: Dict,
    ) -> tuple:
        """Per-issue parallel refinement — avoids one huge monolithic LLM call."""
        import asyncio
        import copy

        entities = copy.deepcopy(entities)
        relations = copy.deepcopy(relations)
        terms = copy.deepcopy(terms)

        next_id = [len(entities) + 1]  # mutable counter for new entity IDs

        # ── 1. Add missing entities (parallel) ────────────────────────────────
        missing = issues.get("missing_entities", [])
        if missing and self.llm:
            new_entity_results = await asyncio.gather(
                *[self._create_entity_llm(source_sample, name) for name in missing],
                return_exceptions=True,
            )
            for name, result in zip(missing, new_entity_results):
                if isinstance(result, dict):
                    result["id"] = f"e{next_id[0]}"
                    next_id[0] += 1
                    entities.append(result)
                else:
                    # fallback: add a minimal entity so it at least appears in the map
                    entities.append({"id": f"e{next_id[0]}", "name": name, "type": "concept", "description": ""})
                    next_id[0] += 1

        # ── 2. Merge duplicate entities (sequential — order matters) ──────────
        for pair in issues.get("duplicate_entities", []):
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                continue
            name_a, name_b = str(pair[0]), str(pair[1])
            idx_a = next((i for i, e in enumerate(entities) if e.get("name", "").lower() == name_a.lower()), None)
            idx_b = next((i for i, e in enumerate(entities) if e.get("name", "").lower() == name_b.lower()), None)
            if idx_a is not None and idx_b is not None and idx_a != idx_b:
                # Keep whichever has the longer description; remap relations
                keep, drop = (idx_a, idx_b) if len(entities[idx_a].get("description", "")) >= len(entities[idx_b].get("description", "")) else (idx_b, idx_a)
                drop_id = entities[drop]["id"]
                keep_id = entities[keep]["id"]
                for r in relations:
                    if r.get("source") == drop_id:
                        r["source"] = keep_id
                    if r.get("target") == drop_id:
                        r["target"] = keep_id
                entities.pop(drop)

        # ── 3. Add missing glossary terms (parallel) ──────────────────────────
        missing_terms = issues.get("missing_terms", [])
        if missing_terms and self.llm:
            new_term_results = await asyncio.gather(
                *[self._create_term_llm(source_sample, t) for t in missing_terms],
                return_exceptions=True,
            )
            existing_keys = {t.get("term", "").lower() for t in terms}
            for result in new_term_results:
                if isinstance(result, dict) and result.get("term", "").lower() not in existing_keys:
                    terms.append(result)
                    existing_keys.add(result.get("term", "").lower())

        # ── 4. Fix vague definitions (parallel) ───────────────────────────────
        vague = issues.get("vague_definitions", [])
        if vague and self.llm:
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
                        terms[term_map[key]]["definition"] = fixed.get("definition", terms[term_map[key]].get("definition", ""))

        return entities, relations, terms

    async def _create_entity_llm(self, source_sample: str, name: str) -> Optional[Dict]:
        prompt = f"""Create a domain entity entry for: "{name}"

Source documentation (excerpt):
{source_sample[:2000]}

Return ONLY a JSON object:
{{"name": "{name}", "type": "process|actor|system|data|rule|concept", "description": "max 15 words"}}
No markdown fences."""
        try:
            response = await self.llm.acomplete(prompt, max_tokens=256)  # type: ignore[union-attr]
            return json.loads(_strip_fences(str(response).strip()))
        except Exception as e:
            logger.warning("Create entity '%s' failed: %s", name, e)
            return None

    async def _create_term_llm(self, source_sample: str, term: str) -> Optional[Dict]:
        prompt = f"""Write a glossary entry for the term: "{term}"

Source documentation (excerpt):
{source_sample[:2000]}

Return ONLY a JSON object:
{{"term": "{term}", "definition": "...", "related_terms": [], "source": "uploaded documentation"}}
No markdown fences."""
        try:
            response = await self.llm.acomplete(prompt, max_tokens=256)  # type: ignore[union-attr]
            return json.loads(_strip_fences(str(response).strip()))
        except Exception as e:
            logger.warning("Create term '%s' failed: %s", term, e)
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
            response = await self.llm.acomplete(prompt, max_tokens=256)  # type: ignore[union-attr]
            return json.loads(_strip_fences(str(response).strip()))
        except Exception as e:
            logger.warning("Fix term '%s' failed: %s", term, e)
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

    def _enrich_glossary(self, terms: List[Dict], entities: List[Dict]) -> List[Dict]:
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
        if len(text) <= self.BATCH_CHARS:
            return [text]
        batches, start = [], 0
        while start < len(text):
            end = min(start + self.BATCH_CHARS, len(text))
            batches.append(text[start:end])
            start += self.BATCH_CHARS - self.BATCH_OVERLAP
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
