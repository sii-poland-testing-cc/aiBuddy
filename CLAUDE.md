# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run dev server
uvicorn app.main:app --reload
# or
python app/main.py
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Docker (full stack)

```bash
docker compose up --build
```

---

## Architecture

**AI Buddy** is a QA Agent Platform for test suite audit and optimization.

### Module Overview

```
M1: Context Builder  ──→  M2: Test Suite Analyzer
    (prerequisite)              (uses M1 RAG context)
```

M1 builds a per-project RAG knowledge base from documentation (.docx/.pdf). M2 audit queries that knowledge base to ground LLM recommendations in domain knowledge.

### Backend Request Flow

1. **Create project** via `POST /api/projects/` → returns `project_id` (UUID)
2. **M1**: Upload docs via `POST /api/context/{project_id}/build` — parses .docx/.pdf, indexes into Chroma, extracts mind map + glossary (SSE stream)
3. **M2 prep**: Upload test files via `POST /api/files/{project_id}/upload` — files stored on disk, indexed into Chroma, metadata to SQLite
4. **M2 chat**: `POST /api/chat/stream` — SSE stream:
   - No files attached → LLM conversational response
   - Files attached → dispatches to LlamaIndex Workflow (audit/optimize)
5. Workflow queries M1 RAG with `user_message + "test coverage gaps"`, injects context into LLM prompt, returns `rag_sources` in result

---

## M1: Context Builder

### Pipeline
```
Parse → Embed → Extract → Assemble
StartEvent → ParsedDocsEvent → EmbeddedEvent → ExtractedEvent → StopEvent
```

### Outputs (all three built in one run)
1. **RAG knowledge base** — Chroma per-project, queried by M2
2. **Domain mind map** — JSON `{nodes, edges}` rendered as SVG in frontend
3. **Auto-glossary** — `[{term, definition, related_terms, source}]`

### Key files
- `backend/app/agents/context_builder_workflow.py` — M1 LlamaIndex Workflow
- `backend/app/parsers/document_parser.py` — `.docx` (python-docx) + `.pdf` (pdfplumber)
- `backend/app/api/routes/context.py` — SSE endpoint + status/mindmap/glossary GETs; `_context_store` dict as write-through cache; DB is authoritative store
- `backend/app/rag/context_builder.py` — Chroma manager; `build()`, `build_with_sources()`, `index_from_docs()`, `is_indexed()`

### API endpoints
```
POST /api/context/{project_id}/build?mode=append|rebuild  — upload .docx/.pdf, SSE stream M1 pipeline
GET  /api/context/{project_id}/status    — {rag_ready, artefacts_ready, stats, context_built_at, document_count, context_files}
GET  /api/context/{project_id}/mindmap   — {nodes: [...], edges: [...]}
GET  /api/context/{project_id}/glossary  — [{term, definition, ...}]
```

### Build modes
- `mode=append` (default) — indexes new docs into existing Chroma collection; merges mind map + glossary artefacts (dedup by id/term); extends `context_files` list
- `mode=rebuild` — `delete_collection()` wipes Chroma; clears `_context_store`; replaces `context_files` with only the new filenames

### SSE event format
```json
{"type": "progress", "data": {"message": "string", "progress": 0.0–1.0, "stage": "parse|embed|extract|assemble"}}
{"type": "result",   "data": {"project_id": "...", "rag_ready": true, "mind_map": {...}, "glossary": [...], "stats": {...}}}
{"type": "error",    "data": {"message": "string"}}
```

### Artefact persistence (M1)
After `/build` completes, artefacts are written to the `Project` DB row:
- `mind_map` — `json.dumps({nodes, edges})`
- `glossary` — `json.dumps([{term, definition, ...}])`
- `context_stats` — `json.dumps({entity_count, relation_count, term_count})`
- `context_built_at` — `datetime.utcnow()` (timezone-aware)
- `context_files` — `json.dumps(["file1.docx", ...])` — list of uploaded filenames, accumulated across appends

`_context_store` dict is a write-through in-memory cache; GET endpoints check it first, then fall back to DB (and warm the cache on miss). This survives server restarts.

### Known gaps (M1)
- Embeddings use `BAAI/bge-small-en-v1.5` (HuggingFace local) when `LLM_PROVIDER=anthropic`; Bedrock Titan when `LLM_PROVIDER=bedrock`
- Backend doesn't return `x,y` on mind map nodes; `MindMap.tsx` uses dagre for layout (TB direction)

---

## M2: Test Suite Analyzer

### Three-Tier Workflow Model

| Tier | File | Status |
|------|------|--------|
| Audit | `backend/app/agents/audit_workflow.py` | Implemented |
| Optimize | `backend/app/agents/optimize_workflow.py` | Implemented |
| Regenerate | — | Not yet implemented |

### Audit workflow result shape
```json
{
  "project_id": "...",
  "summary": {"duplicates_found": 0, "untagged_cases": 0, "coverage_pct": 100.0},
  "duplicates": [],
  "untagged": [],
  "recommendations": ["...", "..."],
  "rag_sources": [{"filename": "doc.docx", "excerpt": "..."}],
  "next_tier": "optimize"
}
```

### RAG integration in Audit workflow
- Queries `context_builder.build_with_sources(project_id, query=f"{user_message} test coverage gaps")`
- Returns sources in `rag_sources` field — rendered as collapsible "Źródła" panel in frontend
- Logs a warning (does not crash) if project has no M1 context indexed

---

## LLM Provider Switching

Controlled by `LLM_PROVIDER` env var. Logic in `backend/app/core/llm.py`.

| Provider | Package | Credentials |
|----------|---------|-------------|
| `bedrock` (default) | `llama-index-llms-bedrock-converse` | AWS credentials |
| `anthropic` | `llama-index-llms-anthropic` | `ANTHROPIC_API_KEY` in `backend/.env` |

### Embedding model
| Provider | Embed model |
|----------|------------|
| `bedrock` | Bedrock Titan (`BEDROCK_EMBED_MODEL_ID`) |
| `anthropic` (or non-bedrock) | `BAAI/bge-small-en-v1.5` via HuggingFace (local, no API key) |

`_build_embed_model()` in `context_builder.py` handles the switch.

---

## LlamaIndex Workflow Context API (v0.14+)

`ctx.set()` / `ctx.get()` were removed. Use:
- **Write**: `await ctx.store.set("key", value)`
- **Read**: `value = await ctx.store.get("key")`

Applies to all workflows: `audit_workflow.py`, `optimize_workflow.py`, `context_builder_workflow.py`.

---

## Key Files

### Backend
- `backend/app/main.py` — FastAPI app, CORS, route registration, `init_db()` in lifespan
- `backend/app/core/config.py` — Pydantic settings (all env vars)
- `backend/app/core/llm.py` — LLM provider factory (`get_llm()`)
- `backend/app/agents/context_builder_workflow.py` — M1: parse → embed → extract → assemble
- `backend/app/agents/audit_workflow.py` — M2 Tier 1: parse → analyse (RAG) → report
- `backend/app/agents/optimize_workflow.py` — M2 Tier 2: prepare → deduplicate → tag
- `backend/app/parsers/document_parser.py` — .docx and .pdf parser
- `backend/app/api/routes/context.py` — M1 SSE + artefact GETs
- `backend/app/api/routes/chat.py` — M2 SSE; conversational fallback when no files attached
- `backend/app/api/routes/projects.py` — Project CRUD; `project_id` is a UUID auto-generated on creation
- `backend/app/api/routes/files.py` — File upload, Chroma indexing, DB metadata
- `backend/app/db/models.py` — `Project` (+ `mind_map`, `glossary`, `context_stats`, `context_built_at`, `context_files` columns) + `ProjectFile` ORM (SQLAlchemy 2.0 Mapped API)
- `backend/app/db/engine.py` — async engine, `get_db()`, `AsyncSessionLocal`, `init_db()` (schema v2; idempotent ALTER TABLE migration adds `context_files` if missing)
- `backend/app/rag/context_builder.py` — Chroma manager; `build_with_sources()` returns `(text, sources)`; `delete_collection()` wipes a project's Chroma collection

### Frontend
- `frontend/lib/useAIBuddyChat.ts` — SSE hook; `ChatMessage` has `sources?: ChatSource[]`; `formatResult` extracts `rag_sources`
- `frontend/lib/useContextBuilder.ts` — SSE hook for M1 build + status polling
- `frontend/lib/useProjects.ts` — Project CRUD hook
- `frontend/lib/useProjectFiles.ts` — File upload + list hook
- `frontend/app/context/[projectId]/page.tsx` — M1 Context Builder page: two-panel layout (320px left: upload→progress→RAG chat; flex-1 right: Mind Map / Glossary tabs)
- `frontend/app/chat/[projectId]/page.tsx` — M2 chat page; context status badge in header
- `frontend/components/Sidebar.tsx` — Module switcher (🧠 Context Builder / 🔍 Suite Analyzer with 🔒 lock when no context); project list with context-ready dot; `activeModule` prop highlights active module
- `frontend/components/MindMap.tsx` — SVG mind map; dagre TB layout (`computeLayout()`); rounded rect nodes (120×40, rx=8); cubic bezier edges (exit bottom-center, enter top-center) with arrow markers; pan (mouse drag), zoom (scroll wheel 0.5–2.0), reset button; TYPE_COLORS: `data=#c8902a, actor=#4a9e6b, process=#5b7fba, system=#9b6bbf, concept=#ba7a5b`; hover shows type label
- `frontend/components/Glossary.tsx` — Searchable glossary; wireframe card style (dark bg, `#f0c060` term, `#c8b89a` definition, monospace related_terms chips)
- `frontend/components/MessageList.tsx` — Chat bubbles + collapsible `SourcesPanel` (Źródła)
- `frontend/components/ChatInputArea.tsx` — Textarea, file chips, send/stop
- `frontend/components/PipelineSteps.tsx` — Audit → Optimize → Regenerate tier selector

### Tests
- `backend/tests/fixtures/sample_domain.docx` — minimal QA domain doc for M1 unit tests
- `backend/tests/fixtures/sample_tests.csv` — 5 fake test cases for M2 tests
- `backend/tests/fixtures/synthetic_docs/` — rich synthetic QA docs for integration tests:
  - `srs_payment_module.docx` — PayFlow SRS with 12 FRs, glossary table, domain actors table
  - `test_plan_payment.docx` — test plan with scope, approach, environments, risk register
  - `qa_process.docx` — QA process with defect lifecycle, severity levels, roles tables
  - `generate_synthetic_docs.py` — script to regenerate all three files
- `backend/tests/conftest.py` — pytest fixtures: env var overrides (temp dirs), PDF fixture, `app_client`
- `backend/tests/test_m1_context.py` — 10 unit/endpoint tests: parser, ContextBuilder, workflow mock, endpoints, DB persistence, append/rebuild modes, context_files tracking
- `backend/tests/test_m1_e2e.py` — 5 e2e tests (a–e) + 1 skipped (f, needs real API key)
- `backend/tests/test_m1_manual.py` — M1 pipeline end-to-end test (SSE + status/mindmap/glossary)
- `backend/tests/test_m1_m2_integration.py` — full M1→M2 integration test

### Frontend tests (Vitest)
```bash
cd frontend && npm test
```
- `frontend/tests/MindMap.test.tsx` — 9 tests: renders, nodes (rect), edges (bezier path), labels, empty state, arrow marker, reset button
- `frontend/tests/Glossary.test.tsx` — 7 tests: renders, filter by term, filter by definition, empty state
- `frontend/tests/Sidebar.test.tsx` — 7 tests: module switcher, 🔒 lock, navigation, active highlight
- `frontend/tests/setup.ts` — `@testing-library/jest-dom` setup
- `frontend/vitest.config.ts` — jsdom environment, `@vitejs/plugin-react`, `@` alias

---

## Data Layer

- `backend/.env` — secret overrides (not committed); `ANTHROPIC_API_KEY`, `LLM_PROVIDER`
- `./data/uploads/{project_id}/` — M2 test files per project
- `./data/uploads/{project_id}/context/` — M1 doc uploads per project
- `./data/chroma/` — Chroma vector store (shared collection per `project_id`)
- `./data/ai_buddy.db` — SQLite (dev); swap `DATABASE_URL` for PostgreSQL in prod

---

## Key Environment Variables

| Variable | Default | Notes |
|----------|---------|-------|
| `LLM_PROVIDER` | `bedrock` | `bedrock` or `anthropic` |
| `AWS_REGION` | `eu-central-1` | Required for Bedrock |
| `AWS_ACCESS_KEY_ID` | — | Required for Bedrock |
| `AWS_SECRET_ACCESS_KEY` | — | Required for Bedrock |
| `BEDROCK_MODEL_ID` | `anthropic.claude-3-5-sonnet-20241022-v2:0` | |
| `BEDROCK_EMBED_MODEL_ID` | `amazon.titan-embed-text-v2:0` | |
| `ANTHROPIC_API_KEY` | `""` | Required when `LLM_PROVIDER=anthropic` |
| `ANTHROPIC_MODEL_ID` | `claude-sonnet-4-6` | |
| `VECTOR_STORE_TYPE` | `chroma` | `chroma` or `pgvector` |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/ai_buddy.db` | |
| `MAX_UPLOAD_MB` | `50` | |
| `ALLOWED_EXTENSIONS` | `.xlsx .csv .json .pdf .feature .txt .md .docx` | |

---

## What to Build Next

1. **Regenerate workflow** — `backend/app/agents/regenerate_workflow.py` (M2 Tier 3)
2. **Confluence connector** — M1 ingestion from Confluence REST API
3. **M1 re-run / append** — allow adding more docs to an existing project's knowledge base
4. **Mind map backend coords** — backend doesn't return `x,y` on nodes; dagre layout runs client-side in `MindMap.tsx`; optionally move layout to backend
5. **DB migration tooling** — add Alembic for schema migrations (currently: delete SQLite file + `init_db()` recreates)

---

## Known Gaps

- Regenerate workflow (Tier 3) not implemented
- `useChatAdapter.ts` exists but is unused
- `build_with_sources()` deduplicates sources by filename only — multiple chunks from the same file are collapsed to one excerpt
- SQLite schema changes require deleting `./data/ai_buddy.db` (no Alembic yet); `init_db()` uses `create_all` (IF NOT EXISTS) so new columns won't be added to existing DBs automatically
