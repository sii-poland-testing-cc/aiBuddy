# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend

```bash
cd backend

# Option A — PDM (recommended)
pdm install
cp .env.example .env   # fill in credentials
alembic upgrade head   # apply DB migrations

# Option B — plain venv
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head

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

### Context mode RAG chat
- In the unified v3 page, switching to **Context** mode gives access to a RAG chat backed by M1.
- Glossary terms are clickable — clicking fires `"wyjaśnij termin: {term}"` into the chat.
- Backend detects the `wyjaśnij termin:` prefix, uses `"{term} definition description context usage"` as the RAG query, and returns a structured 3-section response (Opis / Kontekst / Powiązane terminy).
- **Powiązane terminy** chips in the response are rendered as clickable links if the term exists in the glossary; clicking chains to the next "wyjaśnij termin" query.
- Context mode sends `tier: "rag_chat"` to `/api/chat/stream`; this tier bypasses M2 file auto-loading.

### rag_ready isolation
`rag_ready` is `True` **only** when BOTH conditions hold:
1. `project.context_built_at IS NOT NULL` — M1 pipeline completed at least once
2. `is_indexed()` — Chroma collection still has vectors (guards against manual deletion)

Both M1 and M2 write to the same Chroma collection per `project_id`. Without the `context_built_at` gate, uploading M2 audit files (CSV/XLSX) would set `rag_ready=True` before any M1 build. The status endpoint checks `context_built_at` first; if NULL, returns `rag_ready=False` immediately without querying Chroma.

### Known gaps (M1)
- Embeddings use `BAAI/bge-m3` (multilingual, 100+ languages including Polish) when `LLM_PROVIDER=anthropic`; Bedrock Titan when `LLM_PROVIDER=bedrock`. Override with `EMBED_MODEL_NAME` env var.
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
| `anthropic` (or non-bedrock) | `BAAI/bge-m3` via HuggingFace (multilingual, ~560 MB on first run, no API key). Override with `EMBED_MODEL_NAME` env var. |

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
- `backend/app/api/routes/projects.py` — Project CRUD + settings endpoints; `project_id` is a UUID auto-generated on creation
- `backend/app/api/routes/files.py` — File upload (`source_type` param), Chroma indexing, DB metadata, `audit-selection` endpoint
- `backend/app/api/routes/snapshots.py` — Audit history CRUD (list, trend, latest, delete)
- `backend/app/db/models.py` — `Project`, `ProjectFile` (`source_type`, `last_used_in_audit_id`), `AuditSnapshot` ORM (SQLAlchemy 2.0 Mapped API)
- `backend/app/db/engine.py` — async engine, `get_db()`, `AsyncSessionLocal`, `init_db()` (test/bootstrap fallback only — real migrations via Alembic)
- `backend/alembic.ini` — Alembic config; `DATABASE_URL` read from app settings (`.env`)
- `backend/migrations/env.py` — async-compatible Alembic env; imports all ORM models; `render_as_batch=True` for SQLite; `compare_type=False` suppresses TEXT/VARCHAR false positives
- `backend/migrations/versions/001_initial_schema.py` — baseline migration: all 6 tables as of schema v5
- `backend/app/rag/context_builder.py` — Chroma manager; `build_with_sources()` returns `(text, sources)`; `delete_collection()` wipes a project's Chroma collection

### DB schema (v5) — managed by Alembic

```bash
alembic upgrade head          # apply all pending migrations
alembic downgrade -1          # roll back last migration
alembic revision --autogenerate -m "add X"  # generate migration from model diff
alembic stamp head            # mark existing DB as current (first run on existing install)
alembic check                 # verify models and DB are in sync
```

- `projects` — id, name, description, created_at, mind_map, glossary, context_stats, context_built_at, context_files, settings
- `project_files` — id, project_id, filename, file_path, size_bytes, indexed, uploaded_at, last_used_in_audit_id, source_type
- `audit_snapshots` — id, project_id, created_at, files_used (JSON), summary (JSON), requirements_uncovered (JSON), recommendations (JSON), diff (JSON)
- `requirements`, `requirement_tc_mappings`, `coverage_scores` — Faza 2/5+6 tables (see requirements_models.py)

### Frontend — Routing

All project work happens in a single unified page (v3):

```
/                        — project list + create (app/page.tsx)
/project/[projectId]     — unified v3 page (app/project/[projectId]/page.tsx)
  ?mode=audit            — M2 Suite Analyzer (default)
  ?mode=context          — M1 Context Builder chat
  ?mode=requirements     — Faza 2 Requirements Registry

Permanent redirects (next.config.mjs):
  /chat/:id         → /project/:id?mode=audit
  /context/:id      → /project/:id?mode=context
  /requirements/:id → /project/:id?mode=requirements
```

### Frontend — Key Files

- `frontend/app/page.tsx` — Project list + create form; routes to `/project/[id]`; shows amber pulsing dot on rows with active operations (reads `runningProjects` from `ProjectOperationsContext`)
- `frontend/app/project/[projectId]/page.tsx` — Unified v3 page; reads `?mode` from `useSearchParams()`; wires all hooks; hosts TopBar + chat column + ArtifactPanel + UtilityPanel
- `frontend/app/layout.tsx` — Root layout; wraps `<ErrorBoundary>` with `<ProjectOperationsProvider>` (keeps operation state alive across navigation)
- `frontend/lib/ProjectOperationsContext.tsx` — Global in-flight operation registry; `useRef<Map<projectId, Map<OpType, OpState>>>` holds data (no re-render on write); version counter triggers re-renders; exports `ProjectOperationsProvider`, `OpState`, `OpType`, `useProjectOps`; derived `runningProjects: Set<string>`
- `frontend/lib/useAIBuddyChat.ts` — SSE hook; async `formatResult` fetches `/api/snapshots/{projectId}/latest` after audit to append diff summary (📌/📈/📉/📊); exposes `latestSnapshotId`
- `frontend/lib/useContextBuilder.ts` — SSE hook for M1 build + status polling; dual-writes to `ProjectOperationsContext` (opType `"contextBuild"`) so progress survives navigation
- `frontend/lib/useRequirements.ts` — Faza 2 hook: `requirements`, `stats`, `extractRequirements()` (SSE), `patchRequirement()`, `refresh`; dual-writes to `ProjectOperationsContext` (opType `"requirements"`); `useEffect` auto-calls `fetchAll()` when `isExtracting` transitions `true→false` (catches re-mount after navigation)
- `frontend/lib/useMapping.ts` — Faza 5+6 mapping hook; dual-writes to `ProjectOperationsContext` (opType `"mapping"`)
- `frontend/lib/useHeatmap.ts` — Coverage heatmap data hook; `retry` triggers refetch after mapping run
- `frontend/lib/useProjects.ts` — Project CRUD hook
- `frontend/lib/useProjectFiles.ts` — File upload + list hook
- `frontend/lib/parseRelatedTerms.ts` — splits "Powiązane terminy" section into `TermChunk[]` (isGlossaryTerm + glossaryItem) for chip rendering

### Global in-flight state (ProjectOperationsContext)

Long-running SSE operations (M1 context build, requirements extraction, mapping) survive React navigation. When a user navigates away mid-operation and back, the progress bar reappears correctly.

**Pattern used in all three hooks:**
- Local `useState` for fast same-page re-renders
- `ops?.updateOp(projectId, OP_TYPE, patch)` mirrors every state transition to context
- Derived values: `isRunning = ctxOp?.isRunning ?? localIsRunning` (context wins)
- Re-entry guard (`if (isRunning) return`) uses derived value — correctly blocks re-entry even after navigation
- On mount, context values are read automatically via derived state — no explicit "restore" needed

### Frontend — Components

- `frontend/components/TopBar.tsx` — Fixed 48px header; project name + RAG-ready indicator; panel toggle button; links back to `/`
- `frontend/components/ModeInputBox.tsx` — Unified chat input; mode pills (context / requirements / audit) with `data-testid="mode-pill-{mode}"`, `aria-pressed`; artifact chips (mindmap / glossary); auto-resize textarea (capped 140px); file chips; send/stop; Enter sends, Shift+Enter newline
- `frontend/components/UtilityPanel.tsx` — 300px collapsible right panel; mode-specific card stacks:
  - **Context mode**: Sources (Files/Links tabs) → MindMap thumbnail + "Pełny ekran" → Glossary search → Context status → Build mode selector
  - **Requirements mode**: Sources → Coverage heatmap table → Run mapping button
  - **Audit mode**: Sources → Audit history (snapshots) → Tier selector (Audit/Optimize/Regenerate)
  - Types exported: `PanelFile`, `AuditSnapshot`
- `frontend/components/MindMapModal.tsx` — Fullscreen mind map modal; dagre layout + BFS depth (`layoutModalNodes()` exported); pan+zoom (non-passive wheel); cluster collapse (depth≥3 hidden at zoom<0.55, depth≥2 at zoom<0.30); node click tooltip; search dimming; +N badges; Escape to close; `data-testid="mm-node-{id}"`, `data-dimmed`; `getCluster()` has cycle detection (visited Set) — safe for cyclic LLM-generated edges
- `frontend/components/RequirementsView.tsx` — Requirements registry view (replaces MessageList when mode=requirements); module-grouped collapsible cards; sticky header with stats badges + search; loading skeletons; empty state with extract button; `RequirementCard` (level/source badges, mark-reviewed); `ModuleGroup` (collapsible, `data-testid="req-module-group"`)
- `frontend/components/MindMap.tsx` — SVG mind map (inline panel); dagre TB layout; rounded rect nodes (120×40, rx=8); cubic bezier edges; pan+zoom; TYPE_COLORS: `data=#c8902a, actor=#4a9e6b, process=#5b7fba, system=#9b6bbf, concept=#ba7a5b`
- `frontend/components/Glossary.tsx` — Searchable glossary; wireframe card style; `onTermClick` prop — hover shows amber border (`#c8902a`, 0.15s transition)
- `frontend/components/MessageList.tsx` — Chat bubbles + collapsible `SourcesPanel`; `renderAssistantContent` detects `**Powiązane terminy**` marker and renders known glossary terms as amber dashed clickable chips
- `frontend/components/AuditFileSelector.tsx` — Fetches `/api/files/{projectId}/audit-selection`; groups files into "Nowe źródła" / "Poprzednio użyte"; URL sources always-checked/disabled; `refreshKey` prop triggers refetch; calls `onSelectionChange(paths[])` on toggle
- `frontend/components/AuditHistory.tsx` — Collapsible "📋 Historia audytów" panel; snapshot rows with coverage badge (green ≥80% / amber ≥50% / red <50%), diff badge (▲/▼/→); recharts dual-axis trend chart when ≥2 snapshots

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
- `backend/tests/test_rag_ready_isolation.py` — 4 regression tests: `rag_ready` must be False when only M2 files indexed (no M1 build); mindmap/glossary 404 before M1; `rag_ready` becomes True after M1 runs on top of M2 files; fresh project baseline

### Frontend tests (Vitest)
```bash
cd frontend && npm test
```
205 tests across 15 files:
- `frontend/tests/TopBar.test.tsx` — 9 tests: renders, project id, RAG indicator, panel toggle, back navigation
- `frontend/tests/ModeInputBox.test.tsx` — 17 tests: mode pills, locked pills, file chips, placeholder, send/stop, artifact chips, attach button
- `frontend/tests/MindMapModal.test.tsx` — 26 tests: visibility, toolbar, close/Escape, node rendering, search dimming, match count, tooltip show/hide, cluster collapse, `layoutModalNodes` unit tests; **cycle-safety tests** (direct cycle e1↔e2, longer cycle e1→e2→e3→e1, LLM-style numeric IDs)
- `frontend/tests/UtilityPanel.test.tsx` — 35 tests: panel open/close, mode-specific card content, source tabs, heatmap, tier selector, snapshot rows, ↗ opens audit modal, × closes modal
- `frontend/tests/RequirementsView.test.tsx` — 36 tests: header stats, empty state, error, loading skeletons, module groups, search/filter, card badges, mark-reviewed, group collapse
- `frontend/tests/ProjectPage.test.tsx` — 13 tests: page renders for each mode, hook wiring
- `frontend/tests/MindMap.test.tsx` — 9 tests: renders, nodes (rect), edges (bezier path), labels, empty state, arrow marker, reset button
- `frontend/tests/Glossary.test.tsx` — 10 tests: renders, filter, empty state, term click callback, hover border
- `frontend/tests/MessageList.test.tsx` — 3 tests: renders, Powiązane terminy chips, term click fires callback
- `frontend/tests/parseRelatedTerms.test.ts` — 3 tests: known terms matched, unknown terms plain, comma splitting
- `frontend/tests/AuditFileSelector.test.tsx` — 4 tests: new files checked, used files unchecked+muted, URL source always-checked/disabled, onSelectionChange called correctly
- `frontend/tests/AuditHistory.test.tsx` — 5 tests: empty state, snapshot rows rendered, latest highlight, coverage badge colors, trend chart requires ≥2 snapshots
- `frontend/tests/useRequirements.test.ts` — 8 tests: fetch, extract SSE, patch optimistic update; **re-mount after navigation** (isExtracting context true→false triggers fetchAll)
- `frontend/tests/useAuditPipeline.test.ts` — 12 tests: fresh project (extract+map+send), sequential order, status messages, skip-when-done, guards (isExtracting/isMappingRunning), fetch failure resilience, send arguments
- `frontend/tests/useAIBuddyChat.test.ts` — 13 tests: localStorage load/save/clear, status message exclusion, per-project isolation, projectId change re-load
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
| `EMBED_MODEL_NAME` | `BAAI/bge-m3` | HuggingFace embed model (non-Bedrock only) |
| `VECTOR_STORE_TYPE` | `chroma` | `chroma` or `pgvector` |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/ai_buddy.db` | |
| `MAX_UPLOAD_MB` | `50` | |
| `ALLOWED_EXTENSIONS` | `.xlsx .csv .json .pdf .feature .txt .md .docx` | |

---

## What to Build Next

1. **Regenerate workflow** — `backend/app/agents/regenerate_workflow.py` (M2 Tier 3)
2. **Confluence connector** — M1 ingestion from Confluence REST API
3. **Mind map backend coords** — backend doesn't return `x,y` on nodes; dagre layout runs client-side in `MindMap.tsx`; optionally move layout to backend
4. ~~**DB migration tooling**~~ — ✅ Alembic added (migrations/)
5. **Jira connector** — upload Jira issues as test source (`source_type="jira"`); currently the field exists in the DB and selection UI but no ingestion pipeline

---

## Known Gaps

- Regenerate workflow (Tier 3) not implemented
- `build_with_sources()` deduplicates sources by filename only — multiple chunks from the same file are collapsed to one excerpt
- Schema migrations now managed by Alembic (`alembic upgrade head`); `init_db()` is a test/bootstrap fallback only (`create_all`)
- `_extract_requirements` uses LLM to parse FR IDs from RAG context — accuracy depends on M1 context quality; returns `[]` (coverage 0%) when no context is indexed
- Trend chart in `AuditHistory` only appears with ≥ 2 snapshots; single-audit projects show no chart
- `recharts` added as a runtime dependency (`npm install recharts`)


---

## Faza 2/5/6: Coverage Analysis Pipeline

### Module Overview (extended)

```
M1: Context Builder  ──→  Faza 2: Requirements Extraction
    (prerequisite)              │
                                ▼
                         Faza 5+6: Mapping & Coverage Scoring
                                │
                                ▼
                         M2: Test Suite Analyzer (audit uses Faza 2/5/6 when available)
```

### Pipeline Flow

```
Faza 2: Requirements Reconstruction
  POST /api/requirements/{project_id}/extract  (SSE)
  Workflow: Extract → Validate → Persist
  Input:  M1 RAG context (multiple queries)
  Output: Hierarchical requirements registry in DB
  Tables: requirements (hierarchical, with confidence + human_reviewed)

Faza 5+6: Semantic Mapping & Coverage Scoring
  POST /api/mapping/{project_id}/run  (SSE)
  Workflow: LoadData → CoarseMatch → FineMatch → Score → Persist
  Input:  requirements (from Faza 2 DB) + test files (uploaded)
  Output: requirement↔TC mappings + multi-dimensional scores
  Tables: requirement_tc_mappings, coverage_scores
```

### Key Files (Faza 2/5/6)

- `backend/app/db/requirements_models.py` — `Requirement`, `RequirementTCMapping`, `CoverageScore` ORM models (share `Base` with `models.py`)
- `backend/app/agents/requirements_workflow.py` — Faza 2: LlamaIndex Workflow (Extract → Validate → Persist)
- `backend/app/agents/mapping_workflow.py` — Faza 5+6: LlamaIndex Workflow (Load → CoarseMatch → FineMatch → Score → Persist)
- `backend/app/agents/audit_workflow_integration.py` — Bridge: audit uses Faza 5+6 scores → Faza 2 registry → legacy extraction (3-tier priority)
- `backend/app/api/routes/requirements.py` — Faza 2 API: SSE extract, CRUD, stats, gaps, human review
- `backend/app/api/routes/mapping.py` — Faza 5+6 API: SSE run, mappings list, coverage scores, summary, heatmap, verify

### DB Schema (v5) — New Tables

#### `requirements`

| Column | Type | Notes |
|--------|------|-------|
| `id` | String PK | UUID |
| `project_id` | String FK | → `projects.id` ON DELETE CASCADE |
| `parent_id` | String FK | → `requirements.id` (self-referential hierarchy) |
| `level` | String | `"domain_concept"` \| `"feature"` \| `"functional_req"` \| `"acceptance_criterion"` |
| `external_id` | String | nullable — original ID from docs (e.g. `"FR-017"`) |
| `title` | String | |
| `description` | Text | |
| `source_type` | String | `"formal"` \| `"implicit"` \| `"reconstructed"` |
| `source_references` | Text | JSON list of source filenames |
| `taxonomy` | Text | JSON `{module, risk_level, business_domain}` |
| `completeness_score` | Float | 0.0–1.0, nullable |
| `confidence` | Float | 0.0–1.0 — how certain the system is this requirement is real |
| `human_reviewed` | Boolean | default False |
| `needs_review` | Boolean | default False — flagged when confidence < 0.7 |
| `review_reason` | String | nullable |
| `created_at` | DateTime(tz) | |
| `updated_at` | DateTime(tz) | nullable |

#### `requirement_tc_mappings`

| Column | Type | Notes |
|--------|------|-------|
| `id` | String PK | UUID |
| `requirement_id` | String FK | → `requirements.id` ON DELETE CASCADE |
| `project_id` | String FK | → `projects.id` ON DELETE CASCADE |
| `tc_source_file` | String | filename of TC source |
| `tc_identifier` | String | TC ID or title |
| `mapping_confidence` | Float | 0.0–1.0 |
| `mapping_method` | String | `"pattern"` \| `"embedding"` \| `"llm"` \| `"human"` |
| `coverage_aspects` | Text | JSON `["happy_path", "negative", "boundary"]` |
| `human_verified` | Boolean | default False |
| `created_at` | DateTime(tz) | |

#### `coverage_scores`

| Column | Type | Notes |
|--------|------|-------|
| `id` | String PK | UUID |
| `requirement_id` | String FK | → `requirements.id` ON DELETE CASCADE |
| `snapshot_id` | String FK | nullable → `audit_snapshots.id` |
| `project_id` | String FK | → `projects.id` ON DELETE CASCADE |
| `total_score` | Float | 0–100, sum of components below |
| `base_coverage` | Float | 0–40: happy path covered? |
| `depth_coverage` | Float | 0–30: negative, boundary, edge cases |
| `quality_weight` | Float | 0–20: avg mapping confidence × 20 |
| `confidence_penalty` | Float | -10–0: penalty for low-confidence requirement |
| `crossref_bonus` | Float | 0–10: covered by TCs from multiple files |
| `matched_tc_count` | Integer | |
| `coverage_aspects_present` | Text | JSON array |
| `coverage_aspects_missing` | Text | JSON array |
| `created_at` | DateTime(tz) | |

### Audit Integration Priority Chain

When `compute_registry_coverage()` runs during an M2 audit:

1. **Faza 5+6 scores in DB?** → return persisted scores (best quality, no LLM calls)
2. **Faza 2 requirements in DB?** → load requirements, do live matching against TCs
3. **Neither?** → run legacy `_extract_requirements()` (original behavior)

### Matching Algorithm (Faza 5)

Three levels, merged:
- **Level 0 — Pattern**: TC text contains requirement ID literally (e.g. "FR-017"). Confidence: 0.95
- **Level 1 — Embedding**: cosine similarity > 0.58 between requirement and TC embeddings. Confident > 0.78, ambiguous 0.58–0.78
- **Level 2 — LLM**: evaluates ambiguous pairs. Returns COVERS/PARTIAL/NO + coverage_aspects

### Scoring Model (Faza 6)

```
total_score = min(100, base_coverage + depth_coverage + quality_weight + confidence_penalty + crossref_bonus)
```

Color coding: 🟢 80-100 | 🟡 60-79 | 🟠 30-59 | 🔴 0-29

### API Endpoints (Faza 2)

```
POST   /api/requirements/{project_id}/extract    — run Faza 2 pipeline (SSE)
GET    /api/requirements/{project_id}             — hierarchical list
GET    /api/requirements/{project_id}/flat        — flat list
GET    /api/requirements/{project_id}/stats       — summary statistics
GET    /api/requirements/{project_id}/gaps        — identified gaps
PATCH  /api/requirements/{project_id}/{req_id}    — human review update
DELETE /api/requirements/{project_id}             — wipe for re-extract
```

### API Endpoints (Faza 5+6)

```
POST   /api/mapping/{project_id}/run              — run mapping + scoring (SSE)
GET    /api/mapping/{project_id}                   — list all mappings
GET    /api/mapping/{project_id}/coverage          — per-requirement scores (sortable)
GET    /api/mapping/{project_id}/summary           — aggregate stats + distribution
GET    /api/mapping/{project_id}/heatmap           — module-level heatmap
PATCH  /api/mapping/{project_id}/{mapping_id}      — human verify mapping
DELETE /api/mapping/{project_id}                   — wipe mappings + scores
```

### SSE Event Format (same as M1/M2)

```json
{"type": "progress", "data": {"message": "string", "progress": 0.0–1.0, "stage": "extract|validate|persist|load|coarse|fine|score"}}
{"type": "result",   "data": { ... }}
{"type": "error",    "data": {"message": "string"}}
```

### Requirements Workflow Context API

Same pattern as existing workflows:
- `await ctx.store.set("key", value)` / `await ctx.store.get("key")`
- `ctx.write_event_to_stream(ProgressEvent(...))` for SSE
- Returns `StopEvent(result={...})`

### Testing (Faza 2/5/6)

```bash
# After integration, run from backend/
pytest tests/test_requirements.py -v      # Faza 2 tests
pytest tests/test_mapping.py -v           # Faza 5+6 tests
```
