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
3. **M2 prep**: Upload test files via `POST /api/files/{project_id}/upload?source_type=file|url|jira|confluence` — files stored on disk, indexed into Chroma, metadata to SQLite
4. **M2 chat**: `POST /api/chat/stream` — SSE stream:
   - No files attached → auto-loads only **default-selected** project files (new + URL sources); falls back to LLM conversational response if still empty
   - Files attached → dispatches to LlamaIndex Workflow (audit/optimize)
5. Workflow queries M1 RAG with `user_message + "test coverage gaps"`, injects context into LLM prompt, returns `rag_sources` in result
6. After audit completes → `save_snapshot()` persists `AuditSnapshot`, injects `snapshot_id` into result

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

### Context page RAG chat
- The M1 Context Builder page (`/context/[projectId]`) includes a right-panel RAG chat.
- Glossary terms are clickable — clicking fires `"wyjaśnij termin: {term}"` into the chat.
- Backend detects the `wyjaśnij termin:` prefix, uses `"{term} definition description context usage"` as the RAG query, and returns a structured 3-section response (Opis / Kontekst / Powiązane terminy).
- **Powiązane terminy** chips in the response are rendered as clickable links if the term exists in the glossary; clicking chains to the next "wyjaśnij termin" query.
- Context page sends `tier: "rag_chat"` to `/api/chat/stream`; this tier bypasses M2 file auto-loading.

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

### Requirement-based coverage
Coverage is computed from actual requirement IDs extracted from the M1 RAG context:
1. `_extract_requirements(rag_context)` — LLM extracts `["FR-001", "FR-002", ...]` from RAG context; `llm=None` returns mock list; falls back to `[]` on error
2. `_requirements_in_tests(cases, known_reqs)` — Step A: pattern-matches req IDs in concatenated test case string fields; Step B: LLM fallback for fuzzier matching
3. `coverage_pct = covered / total * 100`; if `total == 0` → `0.0` + fallback recommendation mentioning Context Builder

### Audit workflow result shape
```json
{
  "project_id": "...",
  "snapshot_id": "uuid",
  "summary": {
    "duplicates_found": 0,
    "untagged_cases": 0,
    "coverage_pct": 75.0,
    "requirements_total": 10,
    "requirements_covered": 7,
    "requirements_uncovered": ["FR-005", "FR-009"]
  },
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

### Audit snapshot persistence
After every completed audit, `save_snapshot()` in `chat.py`:
- Saves `AuditSnapshot` row (JSON Text fields: `files_used`, `summary`, `requirements_uncovered`, `recommendations`, `diff`)
- Computes diff vs. previous snapshot: `coverage_delta`, `duplicates_delta`, `new_covered`, `newly_uncovered`, `files_added`, `files_removed`; `null` on first snapshot
- Enforces max 5 snapshots per project (oldest deleted)
- Updates `ProjectFile.last_used_in_audit_id` for all files used in the audit

### File selection for audits
`ProjectFile.source_type` classifies each file: `"file"` | `"url"` | `"jira"` | `"confluence"`.

Default selection rules (used by auto-load in chat + `GET /api/files/{project_id}/audit-selection`):
- `source_type != "file"` (URL/Jira/Confluence) → **always selected** (checkbox disabled in UI)
- `last_used_in_audit_id == null` → **selected** (never audited)
- `last_used_in_audit_id` set → **deselected** (already used in a prior audit)

Chat endpoint auto-load (when `file_paths` is empty): `WHERE last_used_in_audit_id IS NULL OR source_type != 'file'`

---

## Audit Snapshots API

```
GET    /api/snapshots/{project_id}                  — list last 5 snapshots, newest first; JSON fields parsed
GET    /api/snapshots/{project_id}/trend            — {labels, coverage, duplicates, requirements_covered, requirements_total}; oldest→newest for charts
GET    /api/snapshots/{project_id}/latest           — single most recent snapshot, or 404
DELETE /api/snapshots/{project_id}/{snapshot_id}    — 204 on success, 404 if not found or wrong project
```

Each snapshot response item has: `id`, `created_at`, `files_used` (list), `summary` (dict), `requirements_uncovered` (list), `recommendations` (list), `diff` (dict or null).

---

## Audit File Selection Rules

When loading files for audit (`GET /api/files/{project_id}/audit-selection`):

- **File** (source_type=file), last_used_in_audit_id=null → selected: true
  (never used in any audit — new content)
- **File** (source_type=file), last_used_in_audit_id set → selected: false
  (already audited — same content, deselect by default)
- **URL / Jira / Confluence** (source_type != "file") → selected: true always
  (live sources — content may have changed since last audit,
   e.g. Jira ticket may have new status, comments, acceptance criteria)

Max 5 AuditSnapshots per project — oldest pruned automatically on insert.

---

## Files API

```
POST /api/files/{project_id}/upload?source_type=file   — upload test files; source_type saved to DB
GET  /api/files/{project_id}                           — list all project files
GET  /api/files/{project_id}/audit-selection           — list files with computed selected:bool + last_used_in_audit_at
```

`audit-selection` response shape per item:
```json
{
  "id": "uuid", "filename": "suite.xlsx", "file_path": "...",
  "source_type": "file", "size_bytes": 12400, "uploaded_at": "...",
  "last_used_in_audit_id": null, "last_used_in_audit_at": null,
  "selected": true
}
```
Order: selected (new) first, deselected (used) last; newest-first within each group.

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
- `backend/app/agents/audit_workflow.py` — M2 Tier 1: parse → analyse (RAG + req extraction) → report
- `backend/app/agents/optimize_workflow.py` — M2 Tier 2: prepare → deduplicate → tag
- `backend/app/parsers/document_parser.py` — .docx and .pdf parser
- `backend/app/api/routes/context.py` — M1 SSE + artefact GETs
- `backend/app/api/routes/chat.py` — M2 SSE; `wyjaśnij termin:` detection; `save_snapshot()`; selection-aware file auto-load; conversational fallback when no files
- `backend/app/api/routes/projects.py` — Project CRUD; `project_id` is a UUID auto-generated on creation
- `backend/app/api/routes/files.py` — File upload (`source_type` param), Chroma indexing, DB metadata, `audit-selection` endpoint
- `backend/app/api/routes/snapshots.py` — Audit history CRUD (list, trend, latest, delete)
- `backend/app/db/models.py` — `Project`, `ProjectFile` (`source_type`, `last_used_in_audit_id`), `AuditSnapshot` ORM (SQLAlchemy 2.0 Mapped API)
- `backend/app/db/engine.py` — async engine, `get_db()`, `AsyncSessionLocal`, `init_db()` (schema v4; idempotent ALTER TABLE migrations for `context_files`, `last_used_in_audit_id`, `source_type`)
- `backend/app/rag/context_builder.py` — Chroma manager; `build_with_sources()` returns `(text, sources)`; `delete_collection()` wipes a project's Chroma collection

### DB schema (v4)
- `projects` — id, name, description, created_at, mind_map, glossary, context_stats, context_built_at, context_files
- `project_files` — id, project_id, filename, file_path, size_bytes, indexed, uploaded_at, last_used_in_audit_id, **source_type** (v4)
- `audit_snapshots` — id, project_id, created_at, files_used (JSON), summary (JSON), requirements_uncovered (JSON), recommendations (JSON), diff (JSON)

### Frontend
- `frontend/lib/useAIBuddyChat.ts` — SSE hook; async `formatResult` fetches `/api/snapshots/{projectId}/latest` after audit to append diff summary (📌/📈/📉/📊); exposes `latestSnapshotId`
- `frontend/lib/useContextBuilder.ts` — SSE hook for M1 build + status polling
- `frontend/lib/useProjects.ts` — Project CRUD hook
- `frontend/lib/useProjectFiles.ts` — File upload + list hook
- `frontend/lib/parseRelatedTerms.ts` — splits "Powiązane terminy" section into `TermChunk[]` (isGlossaryTerm + glossaryItem) for chip rendering
- `frontend/app/context/[projectId]/page.tsx` — M1 Context Builder page: two-panel layout; `RagChat` with `prefillQuery` (seq-based trigger), `onTermClick`, `glossary` props; glossary term click fires "wyjaśnij termin:" query
- `frontend/app/chat/[projectId]/page.tsx` — M2 chat page; `AuditFileSelector`, `AuditHistory`, `latestSnapshotId` wired from hook; `handleSend` merges selected files with any newly-attached paths
- `frontend/components/Sidebar.tsx` — Module switcher (🧠 Context Builder / 🔍 Suite Analyzer with 🔒 lock when no context); project list with context-ready dot; `activeModule` prop highlights active module
- `frontend/components/MindMap.tsx` — SVG mind map; dagre TB layout (`computeLayout()`); rounded rect nodes (120×40, rx=8); cubic bezier edges (exit bottom-center, enter top-center) with arrow markers; pan (mouse drag), zoom (scroll wheel 0.5–2.0), reset button; TYPE_COLORS: `data=#c8902a, actor=#4a9e6b, process=#5b7fba, system=#9b6bbf, concept=#ba7a5b`; hover shows type label
- `frontend/components/Glossary.tsx` — Searchable glossary; wireframe card style; `onTermClick` prop — hover shows amber border (`#c8902a`, 0.15s transition), cursor pointer
- `frontend/components/MessageList.tsx` — Chat bubbles + collapsible `SourcesPanel`; `renderAssistantContent` detects `**Powiązane terminy**` marker and renders known glossary terms as amber dashed clickable chips
- `frontend/components/ChatInputArea.tsx` — Textarea, file chips, send/stop
- `frontend/components/PipelineSteps.tsx` — Audit → Optimize → Regenerate tier selector
- `frontend/components/AuditFileSelector.tsx` — Fetches `/api/files/{projectId}/audit-selection`; groups files into "Nowe źródła" / "Poprzednio użyte"; URL sources always-checked/disabled; `refreshKey` prop triggers refetch after audit; calls `onSelectionChange(paths[])` on toggle
- `frontend/components/AuditHistory.tsx` — Collapsible "📋 Historia audytów" panel; snapshot rows with date, coverage badge (green ≥80% / amber ≥50% / red <50%), diff badge (▲/▼/→), expandable details (uncovered chips, recommendations, diff lists); 🗑 delete on hover; recharts dual-axis trend chart (coverage + duplicates) when ≥ 2 snapshots; refetches on `latestSnapshotId` change

### Tests
- `backend/tests/fixtures/sample_domain.docx` — minimal QA domain doc for M1 unit tests
- `backend/tests/fixtures/sample_tests.csv` — 5 fake test cases for M2 tests
- `backend/tests/fixtures/synthetic_docs/` — rich synthetic QA docs for integration tests:
  - `srs_payment_module.docx` — PayFlow SRS with 12 FRs, glossary table, domain actors table
  - `test_plan_payment.docx` — test plan with scope, approach, environments, risk register
  - `qa_process.docx` — QA process with defect lifecycle, severity levels, roles tables
  - `generate_synthetic_docs.py` — script to regenerate all three files
- `backend/tests/conftest.py` — pytest fixtures: env var overrides (temp dirs), PDF fixture, `app_client`
- `backend/tests/test_m1_context.py` — 13 unit/endpoint tests: parser, ContextBuilder, workflow mock, endpoints, DB persistence, append/rebuild modes, context_files, AuditSnapshot table, requirement extraction
- `backend/tests/test_m1_e2e.py` — 5 e2e tests (a–e) + 1 skipped (f, needs real API key)
- `backend/tests/test_m1_manual.py` — M1 pipeline end-to-end test (SSE + status/mindmap/glossary)
- `backend/tests/test_m1_m2_integration.py` — full M1→M2 integration: audit trigger, RAG chat, term explanation, requirement coverage, snapshot persistence (saved, diff, max-5)
- `backend/tests/test_snapshots.py` — 11 tests: snapshots list/trend/latest/delete endpoints + 4 audit-selection tests (new files, used files, URL sources, chat auto-select)

### Frontend tests (Vitest)
```bash
cd frontend && npm test
```
- `frontend/tests/MindMap.test.tsx` — 9 tests: renders, nodes (rect), edges (bezier path), labels, empty state, arrow marker, reset button
- `frontend/tests/Glossary.test.tsx` — 10 tests: renders, filter, empty state, term click callback, hover border
- `frontend/tests/Sidebar.test.tsx` — 7 tests: module switcher, 🔒 lock, navigation, active highlight
- `frontend/tests/MessageList.test.tsx` — 3 tests: renders, Powiązane terminy chips, term click fires callback
- `frontend/tests/parseRelatedTerms.test.ts` — 3 tests: known terms matched, unknown terms plain, comma splitting
- `frontend/tests/AuditFileSelector.test.tsx` — 4 tests: new files checked, used files unchecked+muted, URL source always-checked/disabled, onSelectionChange called correctly
- `frontend/tests/AuditHistory.test.tsx` — 5 tests: empty state, snapshot rows rendered, latest highlight, coverage badge colors, trend chart requires ≥2 snapshots
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
3. **Mind map backend coords** — backend doesn't return `x,y` on nodes; dagre layout runs client-side in `MindMap.tsx`; optionally move layout to backend
4. **DB migration tooling** — add Alembic for schema migrations (currently: idempotent `ALTER TABLE` in `init_db()`; doesn't handle column renames or type changes)
5. **Jira connector** — upload Jira issues as test source (`source_type="jira"`); currently the field exists in the DB and selection UI but no ingestion pipeline

---

## Known Gaps

- Regenerate workflow (Tier 3) not implemented
- `useChatAdapter.ts` exists but is unused
- `build_with_sources()` deduplicates sources by filename only — multiple chunks from the same file are collapsed to one excerpt
- `init_db()` idempotent migrations only add columns; column renames or type changes require manual migration or deleting `./data/ai_buddy.db`
- `_extract_requirements` uses LLM to parse FR IDs from RAG context — accuracy depends on M1 context quality; returns `[]` (coverage 0%) when no context is indexed
- Trend chart in `AuditHistory` only appears with ≥ 2 snapshots; single-audit projects show no chart
- `recharts` added as a runtime dependency (`npm install recharts`)
