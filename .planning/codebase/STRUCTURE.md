# STRUCTURE.md — Directory Layout & Organization

## Top-Level Layout

```
D:/kod/sii/aiBuddy/
├── backend/                  — Python FastAPI backend
├── frontend/                 — Next.js 14 frontend
├── .planning/                — GSD planning artifacts
├── .claude/                  — Claude Code config & GSD harness
├── docker-compose.yml        — Full-stack container orchestration
├── CLAUDE.md                 — Project instructions for Claude Code
└── .gitignore
```

---

## Backend Directory (`backend/`)

```
backend/
├── app/
│   ├── main.py               — FastAPI app entry point, CORS, lifespan, route registration
│   ├── agents/               — LlamaIndex Workflow implementations
│   │   ├── audit_workflow.py                — M2 Tier 1: parse → analyse → report
│   │   ├── audit_workflow_integration.py    — Bridge: Faza 5+6 → Faza 2 → legacy priority chain
│   │   ├── context_builder_workflow.py      — M1: parse → embed → extract → review → assemble
│   │   ├── mapping_workflow.py              — Faza 5+6: load → coarse → fine → score → persist
│   │   ├── optimize_workflow.py             — M2 Tier 2: prepare → deduplicate → tag
│   │   └── requirements_workflow.py         — Faza 2: extract → review → assemble
│   ├── api/
│   │   ├── sse.py                           — SSE helpers
│   │   ├── streaming.py                     — Streaming utilities
│   │   └── routes/
│   │       ├── chat.py                      — M2 SSE endpoint, tier dispatch, snapshot save
│   │       ├── context.py                   — M1 SSE + status/mindmap/glossary GETs
│   │       ├── files.py                     — File upload, Chroma indexing, audit-selection
│   │       ├── mapping.py                   — Faza 5+6 run, mappings, scores, heatmap
│   │       ├── projects.py                  — Project CRUD + settings
│   │       ├── requirements.py              — Faza 2 API: extract, CRUD, stats, gaps
│   │       └── snapshots.py                 — Audit history CRUD (list, trend, latest, delete)
│   ├── core/
│   │   ├── config.py                        — Pydantic Settings (all env vars)
│   │   └── llm.py                           — LLM provider factory (get_llm(), embed model)
│   ├── db/
│   │   ├── engine.py                        — Async SQLAlchemy engine, get_db(), init_db()
│   │   ├── models.py                        — Project, ProjectFile, AuditSnapshot ORM
│   │   └── requirements_models.py           — Requirement, RequirementTCMapping, CoverageScore ORM
│   ├── parsers/
│   │   └── document_parser.py               — .docx (python-docx) + .pdf (pdfplumber) parser
│   ├── rag/
│   │   └── context_builder.py               — Chroma manager: build(), retrieve_nodes(), index_from_docs()
│   ├── services/                             — Shared service layer
│   └── utils/                               — Internal utilities
├── casbin/                   — Authorization policy files
├── data/                     — Runtime data (gitignored)
│   └── uploads/              — Uploaded files per project
├── migrations/               — Alembic DB migrations
│   ├── env.py                — Async-compatible Alembic env
│   └── versions/
│       └── 001_initial_schema.py  — Baseline migration (schema v5, 6 tables)
├── tests/
│   ├── conftest.py           — Shared pytest fixtures, env overrides, temp dirs
│   ├── mapping_helpers.py    — Shared helpers for mapping tests
│   ├── fixtures/
│   │   ├── sample_domain.docx        — Minimal QA domain doc for M1 unit tests
│   │   ├── sample_tests.csv          — 5 fake test cases for M2 tests
│   │   └── synthetic_docs/           — Rich synthetic QA docs for integration tests
│   │       ├── srs_payment_module.docx   — PayFlow SRS with 12 FRs
│   │       ├── test_plan_payment.docx    — Test plan with scope, approach, environments
│   │       ├── qa_process.docx           — QA process with defect lifecycle, severity levels
│   │       └── generate_synthetic_docs.py
│   ├── test_audit_integration.py
│   ├── test_m1_context.py            — 13 unit/endpoint tests for M1
│   ├── test_m1_e2e.py                — 5 e2e tests + 1 skipped
│   ├── test_m1_m2_integration.py     — Full M1→M2 integration
│   ├── test_m1_manual.py             — M1 pipeline end-to-end
│   ├── test_mapping.py               — Faza 5+6 tests
│   ├── test_mapping_extended.py
│   ├── test_projects.py
│   ├── test_rag_ready_isolation.py   — 4 rag_ready regression tests
│   ├── test_reflection.py            — 15 tests: reflection loop patterns
│   ├── test_requirements.py          — Faza 2 tests
│   ├── test_requirements_extended.py
│   ├── test_requirements_rag_quality.py
│   └── test_snapshots.py             — 11 tests: snapshot + audit-selection endpoints
├── .env.example              — Environment variable template
├── alembic.ini               — Alembic config
├── pyproject.toml            — PDM project descriptor
└── requirements.txt          — pip-compatible dependency list
```

---

## Frontend Directory (`frontend/`)

```
frontend/
├── app/                      — Next.js App Router pages
│   ├── layout.tsx            — Root layout; ErrorBoundary + ProjectOperationsProvider
│   ├── page.tsx              — Project list + create form
│   ├── globals.css           — Global styles
│   ├── project/
│   │   └── [projectId]/
│   │       └── page.tsx      — Unified v3 project page (?mode=audit|context|requirements)
│   ├── (auth)/               — Auth route group (placeholder/future)
│   ├── dashboard/            — Dashboard page (future)
│   ├── getting-started/      — Onboarding page
│   └── mockup/               — UI mockup pages
├── components/               — Shared React components
│   ├── AuditHistory.tsx      — Collapsible snapshot history + recharts trend chart
│   ├── AuditModePanel.tsx    — Audit mode side panel
│   ├── AuditResultCard.tsx   — Single audit result display
│   ├── ChatInputArea.tsx     — Chat textarea with file attachment
│   ├── ContextModePanel.tsx  — Context mode side panel
│   ├── ErrorBanner.tsx       — Inline error display
│   ├── ErrorBoundary.tsx     — React error boundary
│   ├── Glossary.tsx          — Searchable glossary with term click callback
│   ├── MessageList.tsx       — Chat bubbles + collapsible SourcesPanel
│   ├── MindMap.tsx           — SVG inline mind map (dagre TB layout)
│   ├── MindMapModal.tsx      — Fullscreen mind map with pan/zoom, cluster collapse
│   ├── ModeInputBox.tsx      — Unified chat input with mode pills + file chips
│   ├── PanelCard.tsx         — Collapsible card wrapper for utility panel sections
│   ├── ProgressBar.tsx       — SSE progress indicator
│   ├── ProjectList.tsx       — Project list + create form component
│   ├── ProjectSwitcherDropdown.tsx — Project navigation dropdown
│   ├── RequirementsModePanel.tsx   — Requirements mode side panel
│   ├── RequirementsView.tsx  — Requirements registry (replaces MessageList in req mode)
│   ├── SourcesCard.tsx       — File/link sources panel card
│   ├── TierButton.tsx        — M2 tier selector button
│   ├── TopBar.tsx            — Fixed 48px header with RAG indicator + panel toggle
│   └── UtilityPanel.tsx      — 300px collapsible right panel (mode-specific content)
├── lib/                      — Custom hooks and utilities
│   ├── ProjectOperationsContext.tsx — Global in-flight SSE operation registry (survives navigation)
│   ├── parseRelatedTerms.ts  — Splits "Powiązane terminy" into TermChunk[]
│   ├── useAIBuddyChat.ts     — SSE chat hook + snapshot diff append
│   ├── useAuditPipeline.ts   — Orchestrates extract → map → send audit pipeline
│   ├── useContextBuilder.ts  — M1 build + status polling hook
│   ├── useHeatmap.ts         — Coverage heatmap data hook
│   ├── useMapping.ts         — Faza 5+6 mapping hook
│   ├── useProjectFiles.ts    — File upload + list hook
│   ├── useProjects.ts        — Project CRUD hook
│   └── useRequirements.ts    — Faza 2 hook: requirements, stats, extract, patch
├── tests/                    — Vitest test files
│   ├── setup.ts              — @testing-library/jest-dom setup
│   ├── AuditHistory.test.tsx
│   ├── Glossary.test.tsx
│   ├── MessageList.test.tsx
│   ├── MindMap.test.tsx
│   ├── MindMapModal.test.tsx
│   ├── ModeInputBox.test.tsx
│   ├── ProjectList.test.tsx
│   ├── ProjectPage.test.tsx
│   ├── ProjectSettingsPage.test.tsx
│   ├── RequirementsView.test.tsx
│   ├── TopBar.test.tsx
│   ├── UtilityPanel.test.tsx
│   ├── mindMapLayout.test.ts
│   ├── parseRelatedTerms.test.ts
│   ├── useAIBuddyChat.test.ts
│   ├── useAuditPipeline.test.ts
│   └── useRequirements.test.ts
├── docs/                     — Frontend documentation
├── mockups/                  — UI mockup images/files
├── next.config.mjs           — Next.js config; permanent redirects (chat→project, context→project)
├── package.json              — npm dependencies
├── tsconfig.json             — TypeScript config
└── vitest.config.ts          — Vitest config (jsdom, @vitejs/plugin-react, @ alias)
```

---

## Runtime Data Directories (gitignored)

```
data/                         — All runtime data (project root or backend/)
├── uploads/
│   └── {project_id}/
│       ├── *.xlsx / *.csv    — M2 uploaded test files
│       └── context/
│           └── *.docx / *.pdf  — M1 uploaded documentation
├── chroma/                   — Chroma vector store (one collection per project_id)
└── ai_buddy.db               — SQLite database (dev)
```

---

## Key Naming Conventions

### Backend (Python)
- Files: `snake_case.py`
- Routes: `snake_case` (e.g. `audit_workflow.py`, `context_builder.py`)
- Test files: `test_<module>.py`
- Classes: `PascalCase` (e.g. `ContextBuilderWorkflow`, `AuditSnapshot`)
- Env vars: `UPPER_SNAKE_CASE`

### Frontend (TypeScript/React)
- Component files: `PascalCase.tsx` (e.g. `MindMapModal.tsx`)
- Hook files: `camelCase.ts` prefixed with `use` (e.g. `useRequirements.ts`)
- Test files: `ComponentName.test.tsx` or `hookName.test.ts`
- Pages: `page.tsx` (Next.js App Router convention)
- Context: `PascalCaseContext.tsx`

### API Routes
- REST pattern: `/api/{resource}/{id}/{action}`
- SSE endpoints always return `text/event-stream`
- Project-scoped: all non-project endpoints are prefixed with `/{project_id}/`

---

## URL Routing (Frontend)

```
/                             — Project list
/project/[projectId]          — Unified v3 project page
  ?mode=audit                 — M2 Test Suite Analyzer (default)
  ?mode=context               — M1 Context Builder
  ?mode=requirements          — Faza 2 Requirements Registry

Permanent redirects (next.config.mjs):
  /chat/:id        → /project/:id?mode=audit
  /context/:id     → /project/:id?mode=context
  /requirements/:id → /project/:id?mode=requirements
```

---

## Configuration Files

| File | Purpose |
|------|---------|
| `backend/.env` | Secret env overrides (not committed) |
| `backend/.env.example` | Template with all required vars |
| `backend/alembic.ini` | Alembic DB migration config |
| `backend/pyproject.toml` | PDM project + dev dependencies |
| `backend/requirements.txt` | pip-compatible dependency list |
| `frontend/next.config.mjs` | Next.js config + URL redirects |
| `frontend/tsconfig.json` | TypeScript config (`@` alias → root) |
| `frontend/vitest.config.ts` | Test runner config |
| `docker-compose.yml` | Multi-service container setup |