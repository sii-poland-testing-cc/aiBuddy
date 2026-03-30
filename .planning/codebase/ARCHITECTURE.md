# Architecture

**Analysis Date:** 2026-03-27

## Pattern Overview

**Overall:** Multi-tier QA Agent Platform with LlamaIndex Workflow orchestration + RAG context management

**Key Characteristics:**
- Modular workflow-based architecture (M1 Context Builder, M2 Audit/Optimize, Faza 2/5/6 Requirements & Mapping)
- Streaming SSE endpoints for long-running LLM operations (progress updates in real-time)
- Per-project Chroma vector stores (shared between M1 documentation context and M2 test file context)
- Write-through in-memory caching for artefacts (mind maps, glossaries) with DB as source of truth
- Global operation state management via React Context (survives navigation)

## Layers

**API Layer (FastAPI + SSE):**
- Purpose: Handle HTTP endpoints and stream LLM workflow events to frontend
- Location: `backend/app/api/routes/` (context, chat, files, projects, snapshots, requirements, mapping)
- Contains: Route handlers, request/response schemas, SSE event formatting
- Depends on: Workflows, Services, DB
- Used by: Frontend (Next.js client)

**Workflow/Agent Layer (LlamaIndex Workflows):**
- Purpose: Orchestrate multi-step LLM-powered processes with intermediate state
- Location: `backend/app/agents/` (context_builder_workflow, audit_workflow, optimize_workflow, requirements_workflow, mapping_workflow, audit_workflow_integration)
- Contains: LlamaIndex `@step` decorated async functions, event emission, LLM calls via semaphore-gated concurrency
- Depends on: RAG (ContextBuilder), Parsers, LLM provider, DB models
- Used by: Chat and Context routes, triggered via SSE streaming

**RAG/Indexing Layer (Chroma + Embeddings):**
- Purpose: Build and query vector stores for semantic search across documents
- Location: `backend/app/rag/context_builder.py`
- Contains: Per-project Chroma client, SimpleDirectoryReader parsing, VectorStoreIndex management
- Depends on: LLM embeddings (HuggingFace or Bedrock)
- Used by: M1 (context extraction), M2 (RAG-grounded audit), Faza 2 (requirement extraction)

**Database Layer (SQLAlchemy + Async):**
- Purpose: Persist projects, files, audit snapshots, requirements registry, and mappings
- Location: `backend/app/db/` (models.py, requirements_models.py, engine.py, queries.py)
- Contains: ORM models (Project, ProjectFile, AuditSnapshot, Requirement, RequirementTCMapping, CoverageScore), async session factory, migrations (Alembic)
- Depends on: SQLite (dev) or PostgreSQL (prod), `aiosqlite` or `asyncpg`
- Used by: All routes, services, workflows

**Service Layer (Business Logic):**
- Purpose: Encapsulate reusable domain logic (snapshot diffing, requirement extraction)
- Location: `backend/app/services/` (snapshots.py, requirements.py, mapping.py)
- Contains: `save_snapshot()` (diff computation, max-5 enforcement), requirement CRUD, mapping logic
- Depends on: DB models, ORM queries
- Used by: Routes (chat, snapshots), workflows

**Parsing/Extraction Layer:**
- Purpose: Convert uploaded files into structured data
- Location: `backend/app/parsers/` (document_parser.py, test_case_parser.py)
- Contains: `.docx` (python-docx) + `.pdf` (pdfplumber) parsing; test case extraction from CSV/XLSX/JSON
- Depends on: File I/O, regex patterns
- Used by: M1 workflow (documents), M2 workflow (test cases)

**Frontend Layer (Next.js + React):**
- Purpose: Single-page unified interface for all QA workflows
- Location: `frontend/app/` (page.tsx, project/[projectId]/page.tsx, layout.tsx)
- Contains: Server components (layout), client components (pages, modals, input boxes)
- Depends on: Custom hooks (useAIBuddyChat, useContextBuilder, useRequirements, useMapping), ProjectOperationsContext
- Used by: End users (QA engineers, test managers)

**Hook Layer (React Data Management):**
- Purpose: Manage API calls, SSE streams, local state, and in-flight operation tracking
- Location: `frontend/lib/` (use*.ts files)
- Contains: `useAIBuddyChat` (M2 chat SSE), `useContextBuilder` (M1 build SSE), `useRequirements` (Faza 2 extraction), `useMapping` (Faza 5+6), `useProjectFiles`, `useSnapshots`
- Depends on: `sseStream.ts` utility, ProjectOperationsContext
- Used by: Pages, components

## Data Flow

**M1: Context Builder (Documentation Ingestion)**

1. Frontend: User uploads `.docx`/`.pdf` files → `POST /api/context/{project_id}/build?mode=append|rebuild`
2. API: Saves files to `./data/uploads/{project_id}/context/`, triggers M1 workflow via SSE
3. Workflow `parse` step: DocumentParser extracts text, headings, tables from each file
4. Workflow `embed` step: SimpleDirectoryReader loads files, SentenceSplitter chunks (RAG_CHUNK_SIZE/OVERLAP), passes to ContextBuilder.index_files()
5. ContextBuilder: Creates Chroma collection per project_id, indexes chunks with filename metadata
6. Workflow `extract` step: LLM extracts entities (actors, data flows, components), relations, domain terms via parallel RAG queries (12 concurrent, top_k=10 per query, 60K char cap)
7. Workflow `review` step: LLM critic validates extracted entities; refine loop (up to REFLECTION_MAX_ITERATIONS cycles) fixes missing/duplicate/hallucinated items
8. Workflow `assemble` step: Merges entities/relations/terms into mind map JSON + glossary JSON; persists to Project row (mind_map, glossary, context_stats, context_built_at, context_files)
9. Frontend: Cache warmth via GET /api/context/{project_id}/mindmap, /glossary, /status

**M2: Test Suite Analyzer (Audit + Optimize)**

1. Frontend: User uploads test files (.xlsx, .csv, .json) → `POST /api/files/{project_id}/upload?source_type=file|url|jira|confluence`
2. API: Saves files to `./data/uploads/{project_id}/`, indexes into same Chroma collection as M1, stores metadata (filename, size_bytes, source_type, uploaded_at)
3. User navigates to audit mode, selects files (new files auto-selected, previously-audited deselected), sends chat message
4. Frontend: `POST /api/chat/stream` with tier="audit", file_paths=[], user_message
5. Chat route: Detects no file_paths → auto-loads default-selected files (WHERE last_used_in_audit_id IS NULL OR source_type != 'file')
6. Audit workflow `parse` step: Parses test files into structured test cases (id, name, description, tags, priority, status, acceptance_criteria)
7. Audit workflow `analyse` step:
   - Detects duplicates via cosine similarity (threshold 0.93 candidate, 0.98 certain) + LLM confirmation
   - Extracts requirements from M1 RAG context (12 parallel queries: "test coverage gaps" + user message)
   - Computes coverage: pattern-matching (literal FR-IDs) + LLM fallback
   - If Faza 2 requirements registry exists in DB, uses that instead of LLM extraction
   - Identifies untagged test cases (no priority/tags assigned)
   - Collects recommendations (e.g., "add negative test for payment timeout")
8. Audit workflow returns: duplicates, untagged cases, coverage_pct, requirements_uncovered, recommendations, rag_sources (filenames from M1)
9. Chat route: Calls `save_snapshot()` to persist AuditSnapshot; computes diff vs previous; enforces max-5 snapshots per project
10. Frontend: Renders audit report, timeline (coverage delta), rag_sources collapsible panel

**Faza 2: Requirements Extraction (Optional, Prerequisite for Advanced Coverage)**

1. Frontend: User clicks "Extract Requirements" button → `POST /api/requirements/{project_id}/extract` (SSE)
2. Requirements workflow `extract` step:
   - Queries M1 RAG context with 12 parallel questions: formal requirements, implicit stories, acceptance criteria, glossary terms, etc.
   - Each query retrieves top_k=10 nodes; combined result capped at 60K chars
   - Injects [Source: filename — section] breadcrumbs into LLM context
   - LLM extracts hierarchical requirements: features → functional_req → acceptance_criteria
   - Assigns confidence scores and identifies low-confidence items (< 0.7) for human review
3. Requirements workflow `review` step: Producer-critic-refine loop (optional reflection, REFLECTION_MAX_ITERATIONS)
4. Requirements workflow `persist` step: Inserts Requirement rows (hierarchical parent_id linkage); stores source_references per requirement
5. Frontend: Renders hierarchical requirements registry; user can mark items as reviewed, view coverage gaps

**Faza 5+6: Semantic Mapping & Coverage Scoring (Optional, Refinement)**

1. Frontend: User clicks "Run Mapping" → `POST /api/mapping/{project_id}/run` (SSE)
2. Mapping workflow:
   - Loads Requirement records from DB + test case records from ProjectFile
   - CoarseMatch: Pattern-matching (requirement ID literals in test text) → 0.95 confidence
   - FineMatch: Embedding similarity (cosine > 0.65) between requirement + test case; LLM fallback for ambiguous pairs
   - Scoring: Multi-dimensional score (base_coverage + depth_coverage + quality_weight + confidence_penalty + crossref_bonus)
   - Persists RequirementTCMapping and CoverageScore rows
3. Frontend: Renders heatmap (requirement × module/TC source), per-requirement scores (color-coded: 🟢 80+ / 🟡 60-79 / 🟠 30-59 / 🔴 <30)
4. Next Audit: If Faza 5+6 scores exist, audit uses them (coverage = persisted scores) instead of Faza 2 registry

**Audit Integration Priority Chain:**

1. Faza 5+6 scores in DB? → Use persisted scores (best quality, no LLM calls)
2. Faza 2 requirements in DB? → Load requirements, compute live mappings
3. Neither? → Run legacy LLM extraction (fallback)

## Key Abstractions

**LlamaIndex Workflow:**
- Purpose: Multi-step async task orchestration with event-driven communication
- Examples: `backend/app/agents/context_builder_workflow.py`, `backend/app/agents/audit_workflow.py`
- Pattern: @step methods emit Events, context API (ctx.store.set/get, ctx.write_event_to_stream), final StopEvent returns result

**ContextBuilder (RAG Manager):**
- Purpose: Unified interface for vector store operations
- Examples: `backend/app/rag/context_builder.py`
- Pattern: Per-project Chroma collections, SentenceSplitter chunking, SimpleDirectoryReader for file parsing, build_with_sources() returns (text, sources)

**Audit Snapshot (Event Sourcing):**
- Purpose: Immutable record of an audit result + delta vs previous
- Examples: `backend/app/db/models.py` (AuditSnapshot), `backend/app/services/snapshots.py` (save_snapshot)
- Pattern: Computed diff (coverage_delta, new_covered, newly_uncovered, etc.), max-5 per project, files_used tracks which files were audited

**ProjectOperationsContext (Global In-Flight State):**
- Purpose: Track long-running operations (M1 builds, requirements extraction, mapping runs) across page navigation
- Examples: `frontend/lib/ProjectOperationsContext.tsx`
- Pattern: useRef<Map<projectId, Map<OpType, OpState>>> for data, version counter for re-renders, useMemo runningProjects derived value

**SSE Event Streaming:**
- Purpose: Push progress updates from backend to frontend without polling
- Examples: `backend/app/api/sse.py`, `frontend/lib/sseStream.ts`
- Pattern: `text/event-stream` content-type, `{"type": "progress"|"result"|"error", "data": {...}}` JSON events, `stream_with_keepalive` sends keep-alive `: ` lines to prevent timeout

## Entry Points

**Backend Server:**
- Location: `backend/app/main.py`
- Triggers: `python app/main.py` or `uvicorn app.main:app --reload`
- Responsibilities: FastAPI app initialization, CORS setup, route registration (context, snapshots, chat, projects, files, requirements, mapping), lifespan init_db() for SQLite dev

**Frontend Server:**
- Location: `frontend/app/layout.tsx` (root layout), `frontend/app/page.tsx` (project list), `frontend/app/project/[projectId]/page.tsx` (unified project page)
- Triggers: `npm run dev` (Next.js dev server) or `npm run build` + `npm start` (production)
- Responsibilities: Root error boundary wrapping ProjectOperationsProvider, routing via /project/:id?mode=audit|context|requirements, mode-specific UI rendering

**Key Workflow Endpoints:**

- `POST /api/context/{project_id}/build` (SSE) → ContextBuilderWorkflow
- `POST /api/chat/stream` (SSE) → AuditWorkflow or OptimizeWorkflow (tier-based routing)
- `POST /api/requirements/{project_id}/extract` (SSE) → RequirementsWorkflow
- `POST /api/mapping/{project_id}/run` (SSE) → MappingWorkflow

## Error Handling

**Strategy:** Graceful degradation with fallbacks

**Patterns:**

- **Workflow failures:** Workflow emits `ProgressEvent(message="error...", ...)` then StopEvent; frontend catches error event via SSE, displays ErrorBanner
- **RAG fallback:** When M1 context not available (context_built_at is null or Chroma empty), audit still runs using LLM-extracted requirements from chat message
- **Coverage fallback:** If Faza 2 requirements extraction fails, audit computes coverage using legacy _extract_requirements() pattern-matching + LLM
- **DB transaction rollback:** Async session auto-rollbacks on exception; Alembic migrations guard schema consistency
- **Missing files:** If test file upload fails (e.g., unsupported extension), API returns 400 HTTPException with reason; frontend shows error banner
- **Concurrency:** LLM calls gated by asyncio.Semaphore (LLM_CONCURRENT_CALLS) to prevent rate-limit exhaustion
- **Timeout:** Workflows have M1_WORKFLOW_TIMEOUT_SECONDS, REQUIREMENTS_WORKFLOW_TIMEOUT_SECONDS env overrides; SSE stream_with_keepalive prevents network timeout

## Cross-Cutting Concerns

**Logging:**
- Framework: Python `logging` module, uvicorn + FastAPI structured logs
- Approach: Per-module loggers (e.g., `logging.getLogger("ai_buddy.m1")` in context_builder_workflow), INFO level for workflow progress, ERROR for failures

**Validation:**
- Pydantic BaseModel schemas for all API requests (ChatRequest, ProjectCreate, etc.)
- File extension whitelisting (M1_ALLOWED = {".docx", ".pdf"}, test files = {".xlsx", ".csv", ".json", ".pdf", ".feature", ".txt", ".md"})
- SQLAlchemy ORM constraints (ForeignKey, ondelete="CASCADE"/"SET NULL", nullable=False on required fields)

**Authentication:**
- **Current:** Implemented for compliance models but no enforced auth on main API (all endpoints public)
- **DB:** Casbin RBAC setup in `/backend/casbin/` (not actively used in routes)
- **Pattern:** FastAPI `depends()` on `get_db()` provides session; future auth middleware can wrap routes with `Depends(verify_jwt)` pattern

**Concurrency Control:**
- **LLM calls:** asyncio.Semaphore initialized at workflow start with LLM_CONCURRENT_CALLS limit
- **DB:** SQLAlchemy async sessions + asyncpg (prod) or aiosqlite (dev) handle connection pooling
- **Chroma:** Per-project collections; no cross-project conflicts (each project_id gets isolated vector store)

**Artefact Caching:**
- **M1 outputs:** Mind map + glossary cached in `_context_store` dict (frontend GET calls check cache first, then DB)
- **Isolation:** Write-through on M1 build completion; single-process cache (multi-worker Gunicorn limitation noted in context.py)
- **Invalidation:** Automatic on rebuild mode (cache key deleted); append mode merges in-memory then persists

---

*Architecture analysis: 2026-03-27*
