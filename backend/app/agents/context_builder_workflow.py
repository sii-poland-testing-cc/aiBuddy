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
from typing import Any, Dict, List

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
        docs: List[Dict] = await ctx.store.get("docs")
        combined = self._combine_text(docs, max_chars=80_000)

        ctx.write_event_to_stream(ProgressEvent(
            message="Extracting domain entities and relationships…",
            progress=0.50, stage="extract"
        ))

        entities, relations = await self._extract_entities(combined)

        ctx.write_event_to_stream(ProgressEvent(
            message=f"✓ Found {len(entities)} domain concepts, {len(relations)} relationships",
            progress=0.70, stage="extract"
        ))

        terms = await self._extract_glossary(combined)

        ctx.write_event_to_stream(ProgressEvent(
            message=f"✓ Built glossary with {len(terms)} terms",
            progress=0.80, stage="extract"
        ))

        return ExtractedEvent(entities=entities, relations=relations, terms=terms)

    # ── Step 4: Assemble ──────────────────────────────────────────────────────

    @step
    async def assemble(self, ctx: Context, ev: ExtractedEvent) -> StopEvent:
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

    async def _extract_entities(self, text: str):
        logger.info("[DEBUG] _extract_entities: combined text length = %d", len(text))
        logger.info("[DEBUG] _extract_entities: first 500 chars = %r", text[:500])

        if not self.llm:
            logger.info("[DEBUG] _extract_entities: llm is None → MOCK FALLBACK")
            return self._mock_entities(), self._mock_relations()

        logger.info("[DEBUG] _extract_entities: llm present (%s) → LLM BRANCH", type(self.llm).__name__)

        prompt = f"""You are a domain analyst reviewing software QA documentation.
Extract the 40 most important domain entities and their relationships.
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
{text[:60000]}
"""
        try:
            response = await self.llm.acomplete(prompt)
            raw_str = str(response).strip()
            logger.info("[DEBUG] _extract_entities: raw LLM response (first 500 chars) = %r", raw_str[:500])
            raw = _strip_fences(raw_str)
            data = json.loads(raw)
            return data.get("entities", []), data.get("relations", [])
        except Exception as e:
            logger.warning("[DEBUG] _extract_entities: EXCEPTION → mock fallback. Exception: %s: %s", type(e).__name__, e)
            return self._mock_entities(), self._mock_relations()

    async def _extract_glossary(self, text: str) -> List[Dict]:
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
Include 10–30 most important domain-specific terms.

Documentation:
{text[:50000]}
"""
        try:
            response = await self.llm.acomplete(prompt)
            raw = _strip_fences(str(response).strip())
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"Glossary extraction failed: {e}, using mock data")
            return self._mock_glossary()

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

    def _combine_text(self, docs: List[Dict], max_chars: int) -> str:
        parts, total = [], 0
        for doc in docs:
            text = doc.get("text", "")
            remaining = max_chars - total
            if remaining <= 0:
                break
            chunk = text[:remaining]
            parts.append(f"=== {doc.get('filename', 'document')} ===\n{chunk}")
            total += len(chunk)
        return "\n\n".join(parts)

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
