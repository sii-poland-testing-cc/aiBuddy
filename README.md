# AI Buddy — QA Test Suite Intelligence

FastAPI + LlamaIndex Workflows backend with a Next.js frontend that audits, optimizes, and grounds QA test suites in domain documentation via per-project RAG.

---

## Architecture Overview

```
Browser (Next.js 14)
    │  SSE / REST (JSON)
    ▼
FastAPI + uvicorn
    │
    ├── LlamaIndex Workflows ──► Amazon Bedrock (claude-3-5-sonnet)
    │       │                    or Anthropic API
    │       │
    │       └── Chroma ─────────── per-project vector store
    │               kb_{project_id}
    │
    └── SQLAlchemy async ──► SQLite (dev) / PostgreSQL (prod)
            Projects, ProjectFiles, AuditSnapshots,
            Requirements, RequirementTCMappings, CoverageScores
```

**M1 Context Builder** — processes project documentation:
```
parse (.docx/.pdf) → embed (Chroma) → extract (mind map + glossary) → assemble
```

**Faza 2 — Requirements Registry** — reconstructs a hierarchical requirements model from M1 RAG context:
```
extract → validate → persist  →  DB: requirements table
```

**M2 Suite Analyzer** — three-tier audit pipeline:
```
Tier 1: Audit      — requirement coverage, duplicates, gap analysis
Tier 2: Optimize   — tag normalisation, priority assignment
Tier 3: Regenerate — (planned)
```

**Faza 5+6 — Semantic Mapping & Coverage Scoring** — maps test cases to requirements:
```
load → coarse match (embedding) → fine match (LLM) → score → persist
```

**M1 → M2 integration**: every M2 audit query retrieves RAG context from the M1 knowledge base and injects it into the LLM prompt. When Faza 2/5+6 data is available, persisted coverage scores are used directly; otherwise the system falls back to live LLM-based requirement extraction.

---

## Tech Stack

| Layer | Tech | Notes |
|---|---|---|
| Workflow orchestration | LlamaIndex Workflows 0.12+ | async event-driven; `ctx.store.set/get` |
| LLM | Bedrock `claude-3-5-sonnet-20241022-v2:0` / Anthropic API | switched via `LLM_PROVIDER` |
| Embeddings | Bedrock Titan `titan-embed-text-v2:0` / `BAAI/bge-m3` | local HuggingFace fallback (~560 MB) |
| Vector store | Chroma 0.5+ | one collection per project |
| Backend framework | FastAPI 0.115+ + uvicorn | all long-running ops stream via SSE |
| ORM / DB | SQLAlchemy 2.0 async + aiosqlite | schema v5; idempotent `ALTER TABLE` migrations |
| Document parsing | python-docx + pdfplumber | `.docx`, `.pdf`, `.xlsx`, `.csv`, `.json`, `.feature` |
| Frontend | Next.js 14 (App Router) | TypeScript, Tailwind CSS |
| Charts | Recharts | audit trend panel in `AuditHistory` |
| Frontend testing | Vitest + Testing Library | jsdom; 154 tests across 12 suites |
| Backend testing | pytest + pytest-asyncio | 82 tests across 7+ suites |

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- One of:
  - AWS credentials with Bedrock access (`claude-3-5-sonnet-20241022` + `titan-embed-text-v2:0`)
  - Anthropic API key

---

## Setup

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # fill in credentials
```

### Frontend

```bash
cd frontend
npm install
```

### Environment variables

Create `backend/.env`. All paths are relative to the `backend/` directory; `data/` is created automatically.

```bash
# Provider — "anthropic" or "bedrock" (default)
LLM_PROVIDER=anthropic

# Anthropic (when LLM_PROVIDER=anthropic)
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL_ID=claude-sonnet-4-6        # optional override

# Amazon Bedrock (when LLM_PROVIDER=bedrock)
AWS_REGION=eu-central-1
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
BEDROCK_EMBED_MODEL_ID=amazon.titan-embed-text-v2:0

# Storage (defaults shown)
DATABASE_URL=sqlite+aiosqlite:///./data/ai_buddy.db
CHROMA_PERSIST_DIR=./data/chroma
UPLOAD_DIR=./data/uploads

# Limits
MAX_UPLOAD_MB=50
```

---

## Running

```bash
# Backend (from backend/)
uvicorn app.main:app --reload --port 8000

# Frontend (from frontend/)
npm run dev                  # http://localhost:3000

# Interactive API docs
open http://localhost:8000/docs
```

### Docker (full stack)

```bash
docker compose up --build
```

---

## Frontend — Routing

All project work happens in a single unified page:

| URL | Description |
|-----|-------------|
| `/` | Project list + create |
| `/project/[id]?mode=audit` | M2 Suite Analyzer (default) |
| `/project/[id]?mode=context` | M1 Context Builder chat + artefacts |
| `/project/[id]?mode=requirements` | Faza 2 Requirements Registry |

Old routes redirect permanently (308):

```
/chat/:id         → /project/:id?mode=audit
/context/:id      → /project/:id?mode=context
/requirements/:id → /project/:id?mode=requirements
```

The unified page layout: **TopBar** (fixed 48px) + **chat/requirements column** (flex-1) + **ArtifactPanel** (inline, 0↔420px slide) + **UtilityPanel** (collapsible, 300px).

---

## Project Structure

```
ai-buddy/
├── backend/
│   ├── app/
│   │   ├── main.py                              # FastAPI app, lifespan, CORS, router registration
│   │   ├── agents/
│   │   │   ├── context_builder_workflow.py      # M1: parse→embed→extract→assemble
│   │   │   ├── audit_workflow.py                # M2 Tier 1: RAG-grounded coverage + gap audit
│   │   │   ├── optimize_workflow.py             # M2 Tier 2: dedup + tag normalisation
│   │   │   ├── requirements_workflow.py         # Faza 2: extract→validate→persist requirements
│   │   │   ├── mapping_workflow.py              # Faza 5+6: coarse→fine match→score→persist
│   │   │   └── audit_workflow_integration.py    # Bridge: priority chain (Faza 5+6 → Faza 2 → legacy)
│   │   ├── api/routes/
│   │   │   ├── projects.py                      # Project CRUD
│   │   │   ├── context.py                       # M1 SSE build + mindmap/glossary/status GETs
│   │   │   ├── files.py                         # Upload, Chroma index, audit-selection endpoint
│   │   │   ├── chat.py                          # M2 SSE stream; save_snapshot(); wyjaśnij termin
│   │   │   ├── snapshots.py                     # Audit history CRUD (list/trend/latest/delete)
│   │   │   ├── requirements.py                  # Faza 2: SSE extract, CRUD, stats, gaps, review
│   │   │   └── mapping.py                       # Faza 5+6: SSE run, mappings, scores, heatmap
│   │   ├── core/
│   │   │   ├── config.py                        # Pydantic Settings — all env vars with defaults
│   │   │   └── llm.py                           # LLM provider factory (get_llm())
│   │   ├── db/
│   │   │   ├── models.py                        # Project, ProjectFile, AuditSnapshot ORM models
│   │   │   ├── requirements_models.py           # Requirement, RequirementTCMapping, CoverageScore
│   │   │   └── engine.py                        # Async engine, AsyncSessionLocal, init_db() v5
│   │   ├── parsers/
│   │   │   └── document_parser.py               # .docx (python-docx) + .pdf (pdfplumber) → Document[]
│   │   └── rag/
│   │       └── context_builder.py               # Chroma manager: build(), build_with_sources(), index_files()
│   ├── tests/
│   │   ├── conftest.py                          # Fixtures: temp dirs, PDF builder, app_client
│   │   ├── fixtures/
│   │   │   ├── sample_domain.docx               # Minimal QA domain doc for M1 unit tests
│   │   │   ├── sample_tests.csv                 # 5 fake test cases for M2 tests
│   │   │   └── synthetic_docs/                  # PayFlow SRS, test plan, QA process (.docx × 3)
│   │   ├── test_m1_context.py                   # 13 tests: parser, ContextBuilder, endpoints, DB
│   │   ├── test_m1_e2e.py                       # 5 tests: full M1 SSE pipeline (+ 1 skipped)
│   │   ├── test_m1_m2_integration.py            # 8 tests: audit, RAG, coverage, snapshots
│   │   ├── test_snapshots.py                    # 11 tests: snapshots API + file selection
│   │   ├── test_requirements.py                 # Faza 2 endpoint + workflow tests
│   │   ├── test_requirements_extended.py        # Faza 2 edge cases: re-extract, delete, no-context
│   │   └── test_mapping.py                      # Faza 5+6: mapping pipeline + coverage scores
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── app/
│   │   ├── page.tsx                             # Project list / landing; routes to /project/[id]
│   │   └── project/[projectId]/page.tsx         # Unified v3 page — all modes in one layout
│   ├── components/
│   │   ├── TopBar.tsx                           # Fixed 48px header; project name + RAG indicator
│   │   ├── ModeInputBox.tsx                     # Unified input: mode pills, artifact chips, send/stop
│   │   ├── UtilityPanel.tsx                     # 300px collapsible right panel; mode-specific cards
│   │   ├── MindMapModal.tsx                     # Fullscreen mind map; pan/zoom/cluster-collapse/search
│   │   ├── RequirementsView.tsx                 # Requirements registry; module groups + search + cards
│   │   ├── MindMap.tsx                          # SVG mind map (inline panel, dagre TB layout)
│   │   ├── Glossary.tsx                         # Searchable glossary; terms clickable → RAG chat
│   │   ├── MessageList.tsx                      # Chat bubbles + RAG sources + Powiązane terminy chips
│   │   ├── AuditFileSelector.tsx                # Per-file checklist: new=checked, used=unchecked, URL=locked
│   │   └── AuditHistory.tsx                     # Collapsible audit log + Recharts coverage trend chart
│   ├── lib/
│   │   ├── useAIBuddyChat.ts                    # SSE hook; async formatResult with diff summary appended
│   │   ├── useContextBuilder.ts                 # M1 build SSE + status polling
│   │   ├── useRequirements.ts                   # Faza 2: requirements, stats, extractRequirements (SSE)
│   │   ├── useHeatmap.ts                        # Coverage heatmap data; retry after mapping run
│   │   ├── useProjectFiles.ts                   # File upload + list
│   │   ├── useProjects.ts                       # Project CRUD
│   │   └── parseRelatedTerms.ts                 # Split "Powiązane terminy" section into clickable chips
│   ├── tests/                                   # Vitest + Testing Library (154 tests, 12 suites)
│   ├── vitest.config.ts
│   └── Dockerfile
├── docker-compose.yml
└── CLAUDE.md                                    # AI coding assistant context and conventions
```

---

## Key Architectural Decisions

- **Single unified page** — all modes (context / requirements / audit) live at `/project/[id]?mode=...`; `useSearchParams()` sets the initial mode; old routes redirect permanently so bookmarks and deep links still work
- **LlamaIndex Workflows over LangChain** — explicit typed events, async step isolation, and a `StopEvent` return value make multi-stage SSE streaming straightforward; no implicit chain state
- **`ctx.store.set/get` (not `ctx.set/ctx.get`)** — LlamaIndex v0.14+ removed the old context API; all workflows use `await ctx.store.set("key", value)` / `await ctx.store.get("key")`
- **SSE for all long-running operations** — M1 build, Faza 2 extraction, Faza 5+6 mapping, and M2 audit all stream `{type: "progress", data: {message, progress}}` events; the frontend renders progress bars directly from the stream without polling
- **One Chroma collection per project** — named `kb_{project_id}`; `delete_collection()` in `context_builder.py` gives clean rebuild semantics on `mode=rebuild`
- **`AuditSnapshot` persistence** — immutable audit record saved after every completed audit; max 5 per project (oldest pruned at save time); diff vs. previous snapshot computed and stored as a JSON column at write time, not at read time
- **File selection by audit history** — `ProjectFile.last_used_in_audit_id` tracks whether a file has been audited; chat auto-load applies `WHERE last_used_in_audit_id IS NULL OR source_type != 'file'` so only genuinely new files are included in the next audit by default
- **`source_type` column** (`"file"` | `"url"` | `"jira"` | `"confluence"`) — URL/Jira/Confluence sources always stay selected regardless of audit history; column infrastructure is in place for future connector ingestion pipelines
- **Faza 2/5+6 priority chain** — audit coverage uses persisted scores if available (best quality, no LLM calls), falls back to live Faza 2 matching, then falls back to legacy `_extract_requirements()`
- **LLM_PROVIDER embed split** — `bedrock` uses Titan embeddings via AWS; `anthropic` downloads `BAAI/bge-m3` locally on first run (~560 MB, multilingual including Polish); no extra API key required for embeddings in the Anthropic path

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness — `{status, version}` |
| `POST` | `/api/projects/` | Create project — returns `{project_id}` |
| `GET` | `/api/projects/` | List all projects |
| `GET` | `/api/projects/{project_id}` | Get single project |
| `DELETE` | `/api/projects/{project_id}` | Delete project and cascades |
| `POST` | `/api/context/{project_id}/build` | Upload `.docx`/`.pdf`, run M1 pipeline (SSE) |
| `GET` | `/api/context/{project_id}/status` | `{rag_ready, artefacts_ready, stats, context_built_at, context_files}` |
| `GET` | `/api/context/{project_id}/mindmap` | `{nodes, edges}` |
| `GET` | `/api/context/{project_id}/glossary` | `[{term, definition, related_terms, source}]` |
| `POST` | `/api/files/{project_id}/upload` | Multipart upload; `?source_type=file\|url\|jira\|confluence` |
| `GET` | `/api/files/{project_id}` | List project files |
| `GET` | `/api/files/{project_id}/audit-selection` | Files with computed `selected` flag + `last_used_in_audit_at` |
| `POST` | `/api/chat/stream` | M2 audit / optimize / rag_chat (SSE) |
| `GET` | `/api/snapshots/{project_id}` | Last 5 audit snapshots, newest first |
| `GET` | `/api/snapshots/{project_id}/trend` | `{labels, coverage, duplicates, requirements_covered, requirements_total}` |
| `GET` | `/api/snapshots/{project_id}/latest` | Most recent snapshot or 404 |
| `DELETE` | `/api/snapshots/{project_id}/{snapshot_id}` | Delete snapshot — 204 or 404 |
| `POST` | `/api/requirements/{project_id}/extract` | Run Faza 2 extraction (SSE) |
| `GET` | `/api/requirements/{project_id}/flat` | Flat requirements list |
| `GET` | `/api/requirements/{project_id}/stats` | Summary statistics |
| `GET` | `/api/requirements/{project_id}/gaps` | Identified gaps |
| `PATCH` | `/api/requirements/{project_id}/{req_id}` | Human review update |
| `DELETE` | `/api/requirements/{project_id}` | Wipe requirements for re-extraction |
| `POST` | `/api/mapping/{project_id}/run` | Run Faza 5+6 mapping + scoring (SSE) |
| `GET` | `/api/mapping/{project_id}/coverage` | Per-requirement coverage scores |
| `GET` | `/api/mapping/{project_id}/summary` | Aggregate stats + distribution |
| `GET` | `/api/mapping/{project_id}/heatmap` | Module-level heatmap data |
| `DELETE` | `/api/mapping/{project_id}` | Wipe mappings + scores |

### SSE event envelope

```
data: {"type": "progress", "data": {"message": "Parsing…", "progress": 0.25, "stage": "parse"}}
data: {"type": "result",   "data": { ... }}
data: {"type": "error",    "data": {"message": "..."}}
data: [DONE]
```

### `/api/chat/stream` request body

```json
{
  "project_id": "uuid",
  "message": "run audit",
  "file_paths": [],         // explicit paths — bypasses auto-selection when non-empty
  "tier": "audit",          // "audit" | "optimize" | "rag_chat"
  "audit_report": null      // required for tier="optimize"
}
```

---

## Database Schema

Schema v5. `init_db()` applies idempotent `ALTER TABLE ADD COLUMN` on startup for additive changes.

### `projects`

| Column | Type | Notes |
|--------|------|-------|
| `id` | String PK | UUID auto-generated |
| `name` | String | |
| `description` | String | default `""` |
| `created_at` | DateTime(tz) | |
| `mind_map` | Text | JSON `{nodes, edges}` — written after M1 build |
| `glossary` | Text | JSON `[{term, definition, related_terms, source}]` |
| `context_stats` | Text | JSON `{entity_count, relation_count, term_count}` |
| `context_built_at` | DateTime(tz) | nullable |
| `context_files` | Text | JSON `["file1.docx", ...]` — accumulated across appends |

### `project_files`

| Column | Type | Notes |
|--------|------|-------|
| `id` | String PK | UUID |
| `project_id` | String FK | → `projects.id` ON DELETE CASCADE |
| `filename` | String | |
| `file_path` | String | absolute path on disk |
| `size_bytes` | Integer | |
| `indexed` | Boolean | True after successful Chroma indexing |
| `uploaded_at` | DateTime(tz) | |
| `source_type` | String | `"file"` \| `"url"` \| `"jira"` \| `"confluence"` — default `"file"` |
| `last_used_in_audit_id` | String | nullable — snapshot ID of last audit that included this file |

### `audit_snapshots`

| Column | Type | Notes |
|--------|------|-------|
| `id` | String PK | UUID |
| `project_id` | String FK | → `projects.id` ON DELETE CASCADE |
| `created_at` | DateTime(tz) | |
| `files_used` | Text | JSON list of absolute file paths |
| `summary` | Text | JSON `{coverage_pct, duplicates_found, requirements_total, requirements_covered, untagged_cases}` |
| `requirements_uncovered` | Text | JSON `["FR-005", "FR-009"]` |
| `recommendations` | Text | JSON `["rec 1", …]` |
| `diff` | Text | `null` on first snapshot; JSON `{coverage_delta, duplicates_delta, new_covered, newly_uncovered, files_added, files_removed}` |

### `requirements` (Faza 2)

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
| `taxonomy` | Text | JSON `{module, risk_level, business_domain}` |
| `confidence` | Float | 0.0–1.0 |
| `human_reviewed` | Boolean | default False |
| `needs_review` | Boolean | default False — flagged when confidence < 0.7 |

### `requirement_tc_mappings` + `coverage_scores` (Faza 5+6)

See `backend/app/db/requirements_models.py` for full column definitions.

---

## Testing

```bash
# All backend tests
cd backend && pytest -v

# Individual suites
pytest tests/test_m1_context.py           # M1: parser, ContextBuilder, endpoints, DB
pytest tests/test_m1_e2e.py               # M1: full SSE pipeline
pytest tests/test_m1_m2_integration.py    # M1→M2: audit, RAG, coverage, snapshots
pytest tests/test_snapshots.py            # Snapshots API + file selection rules
pytest tests/test_requirements.py         # Faza 2: extraction, CRUD, stats, review
pytest tests/test_requirements_extended.py # Faza 2: re-extract, delete, no-context
pytest tests/test_mapping.py              # Faza 5+6: mapping pipeline + coverage scores

# With coverage report
pytest --cov=app --cov-report=term-missing

# Frontend (from frontend/)
npm test                                   # 154 tests, 12 suites
```

Test isolation: `conftest.py` overrides `DATABASE_URL`, `CHROMA_PERSIST_DIR`, and `UPLOAD_DIR` to `tempfile.mkdtemp()` paths before any app module is imported. Each test session gets a fresh SQLite file and Chroma directory.

---

## LLM Provider Notes

### Bedrock

```bash
LLM_PROVIDER=bedrock
AWS_REGION=eu-central-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
BEDROCK_EMBED_MODEL_ID=amazon.titan-embed-text-v2:0
```

Requires Bedrock model access enabled in the target region. Uses `llama-index-llms-bedrock-converse` (Converse API, not InvokeModel).

### Anthropic

```bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL_ID=claude-sonnet-4-6     # optional
```

Embeddings fall back to `BAAI/bge-m3` via `llama-index-embeddings-huggingface`. Downloaded to the HuggingFace cache on first run (~560 MB, multilingual including Polish). No additional API key needed for embeddings.

---

## Known Limitations

- **DB migrations**: `init_db()` applies idempotent `ALTER TABLE ADD COLUMN` for additive changes only. Column renames, type changes, or index additions require manual migration or deleting `./data/ai_buddy.db`. Alembic integration is planned.
- **Regenerate workflow** (M2 Tier 3): the tier selector UI exists but the workflow class is not yet implemented.
- **Confluence / Jira ingestion**: `source_type` column and UI selection rules are in place; the connector pipelines (OAuth, REST fetch, document transform) are not yet built.
- **MindMap layout**: dagre runs entirely client-side in `MindMap.tsx` and `MindMapModal.tsx`. The backend returns only node IDs and edge pairs with no coordinates.
- **SQLite idempotent migrations**: the `PRAGMA table_info` introspection in `init_db()` is SQLite-specific. A PostgreSQL production deployment requires those migration blocks to be replaced with Alembic revisions.
- **RAG coverage accuracy**: `_extract_requirements()` uses an LLM call to extract FR IDs from RAG context. If M1 has not been run for a project, `coverage_pct` returns `0.0` and a fallback recommendation is appended prompting the user to run Context Builder first.
