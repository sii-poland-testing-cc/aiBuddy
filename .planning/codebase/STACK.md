# Technology Stack

**Analysis Date:** 2026-03-27

## Languages

**Primary:**
- Python 3.10+ - Backend API and workflows (`backend/`)
- TypeScript 5 - Frontend UI and types (`frontend/`)
- JavaScript - Build configuration and scripts

**Secondary:**
- SQL - Database queries (managed via SQLAlchemy ORM)

## Runtime

**Environment:**
- Python 3.12 (slim) - Backend container image
- Node.js 20 (Alpine) - Frontend container image

**Package Managers:**
- PDM (Python Development Master) - Backend dependency management
  - Lockfile: `backend/pdm.lock`
  - Config: `backend/pyproject.toml`
  - Note: `requirements.txt` is generated from PDM
- npm - Frontend dependency management
  - Lockfile: `frontend/package-lock.json`
  - Config: `frontend/package.json`

## Frameworks

**Core Backend:**
- FastAPI 0.135+ - REST API framework with Pydantic validation
  - Entry point: `backend/app/main.py`
  - CORS middleware configured for `localhost:3000` (dev) via `backend/app/core/config.py`

**Core Frontend:**
- Next.js 14.2+ - React SSR framework
  - Entry points: `frontend/app/page.tsx` (project list), `frontend/app/project/[projectId]/page.tsx` (unified v3 page)
  - Build config: `frontend/next.config.mjs` (redirects for legacy routes)
  - API endpoint: `NEXT_PUBLIC_API_URL` env var (default `http://localhost:8000`)

**Workflow Orchestration:**
- LlamaIndex Workflows 2.17+ - Multi-step agent pipelines
  - M1 Context Builder: `backend/app/agents/context_builder_workflow.py` (SSE parse → embed → extract → review → assemble)
  - M2 Audit: `backend/app/agents/audit_workflow.py` (parse → analyse → report)
  - M2 Optimize: `backend/app/agents/optimize_workflow.py` (prepare → deduplicate → tag)
  - Faza 2 Requirements: `backend/app/agents/requirements_workflow.py` (extract → review → assemble)
  - Faza 5+6 Mapping: `backend/app/agents/mapping_workflow.py` (load → coarse → fine → score → persist)

**Testing:**
- Vitest 4.0+ - Frontend unit tests (jsdom environment)
  - Config: `frontend/vitest.config.ts`
  - Run: `npm test` (runs 248 tests across 17 files)
- pytest - Backend unit/integration tests
  - Fixtures in `backend/tests/fixtures/`
  - Config: `backend/tests/conftest.py`

**UI Components:**
- React 18.3+ - React framework
- TailwindCSS 3.4+ - Utility-first CSS framework
  - Processed via PostCSS 8.4+
  - Config: implicit in `tailwind.config.js` (Next.js auto-detects)
- AutoPrefixer 10.4+ - Browser vendor prefix support

**Build & Dev Tools:**
- Vite-based plugins (via Next.js internal bundler)
  - @vitejs/plugin-react 4.7+ - Fast Refresh for React dev
- ESLint 8+ - Code linting
  - Config: `eslint-config-next` (extends Next.js recommended rules)
  - Run: `npm run lint`
- TypeScript 5 - Static type checking

## Key Dependencies

**Critical (Backend):**
- `llama-index-core` 0.14+ - Core RAG and workflow SDK
- `llama-index-llms-anthropic` 0.11+ - Anthropic Claude API client (when `LLM_PROVIDER=anthropic`)
- `llama-index-llms-bedrock-converse` 0.14+ - AWS Bedrock API client (when `LLM_PROVIDER=bedrock`)
- `llama-index-embeddings-huggingface` 0.7+ - HuggingFace embedding model loader (non-Bedrock default: BAAI/bge-m3)
- `llama-index-embeddings-bedrock` 0.8+ - Bedrock Titan embedding service
- `llama-index-vector-stores-chroma` 0.5+ - Chroma vector store integration
- `chromadb` 1.5+ - Vector database (persistent on disk)
- `anthropic[bedrock,vertex]` 0.86+ - Transitive: Anthropic SDK with Bedrock support

**Document Processing (Backend):**
- `python-docx` 1.2+ - Microsoft Word (.docx) parser
  - Location: `backend/app/parsers/document_parser.py` - extracts text, tables, headings
- `pdfplumber` 0.11+ - PDF parser (primary method)
- `pypdf` 6.9+ - PDF fallback parser
- `pandas` 2.3+ - Tabular data handling (.xlsx, .csv)
- `openpyxl` 3.1+ - Excel workbook parsing

**Database (Backend):**
- `sqlalchemy[asyncio]` 2.0+ - Async ORM
  - Models: `backend/app/db/models.py` (Project, ProjectFile, AuditSnapshot)
  - Models: `backend/app/db/requirements_models.py` (Requirement, RequirementTCMapping, CoverageScore)
- `aiosqlite` 0.22+ - SQLite async driver (dev/test)
  - Production: swap `DATABASE_URL` in `.env` to PostgreSQL
- `alembic` 1.18+ - Schema migration tool
  - Config: `backend/alembic.ini`
  - Migrations: `backend/migrations/versions/`

**Infrastructure (Backend):**
- `uvicorn[standard]` 0.42+ - ASGI server for FastAPI
- `fastapi` 0.135+ - REST framework
- `pydantic` 2.12+ - Data validation
- `pydantic-settings` 2.13+ - Environment configuration loader
- `boto3` 1.40+ - AWS SDK (required for Bedrock)
- `httpx` 0.28+ - Async HTTP client
- `python-multipart` 0.0+ - Form/file upload parsing

**ML/NLP (Backend):**
- `sentence-transformers` 5.3+ - HuggingFace sentence embedding models
- `transformers` 5.3+ - HuggingFace transformer library
- `torch` 2.7+ - PyTorch (required by transformers)
- `scikit-learn` 1.7+ - Cosine similarity for duplicate detection
- `nltk` 3.9+ - Natural language toolkit

**Frontend:**
- `@llamaindex/chat-ui` 0.6+ - LlamaIndex chat UI components
  - Transpiled via `next.config.mjs`
- `dagre` 0.8+ - Graph layout for mind map visualization
- `recharts` 3.8+ - React charts library (audit history trend charts)

## Configuration

**Backend Configuration:**
- `backend/app/core/config.py` - Pydantic Settings class
  - Loads from `backend/.env` (not committed; see `.env.example`)
  - Key env vars: `LLM_PROVIDER` (bedrock|anthropic), `DATABASE_URL`, `CHROMA_PERSIST_DIR`, `UPLOAD_DIR`, timeouts, RAG tuning

**Frontend Configuration:**
- `frontend/tsconfig.json` - TypeScript compiler options (strict mode enabled)
- `frontend/next.config.mjs` - Next.js configuration (route redirects for legacy paths)
- `frontend/vitest.config.ts` - Test runner config
- Path alias: `@/*` → current directory (frontend root)

**Database Configuration:**
- Default: SQLite at `./data/ai_buddy.db` (dev/test)
- Production: PostgreSQL via `DATABASE_URL` env var
- Migrations managed by Alembic (run `alembic upgrade head` before server start)

**Chroma Vector Store:**
- Persistent directory: `./data/chroma/` (local filesystem)
- Per-project collections (one Chroma collection per `project_id`)
- Chunk settings: `RAG_CHUNK_SIZE` (1024 tokens), `RAG_CHUNK_OVERLAP` (128 tokens)

## Platform Requirements

**Development:**
- Python 3.10+ (tested on 3.12)
- Node.js 20+ (tested on Node 20)
- Git
- Optional: Docker & Docker Compose (for full stack)

**Production:**
- Docker & Docker Compose (or container orchestration platform)
- PostgreSQL 12+ (swap from SQLite)
- AWS credentials (if using Bedrock) or Anthropic API key (if using Anthropic)
- S3 or persistent volume (for `/app/data` mount: uploads, Chroma indexes)

**Deployment Target:**
- Container-based (Docker image for both backend and frontend)
- AWS Bedrock (optional, default LLM provider) — requires AWS account + credentials
- Anthropic API (optional alternative) — requires `ANTHROPIC_API_KEY`
- Can run on any platform supporting Docker (AWS ECS, Kubernetes, local Docker, etc.)

## Environment Variables (Critical)

| Variable | Type | Required | Notes |
|----------|------|----------|-------|
| `LLM_PROVIDER` | string | No (default: `bedrock`) | `bedrock` or `anthropic` |
| `AWS_REGION` | string | Yes if `LLM_PROVIDER=bedrock` | e.g. `eu-central-1` |
| `AWS_ACCESS_KEY_ID` | string | Yes if `LLM_PROVIDER=bedrock` | AWS credentials |
| `AWS_SECRET_ACCESS_KEY` | string | Yes if `LLM_PROVIDER=bedrock` | AWS credentials |
| `ANTHROPIC_API_KEY` | string | Yes if `LLM_PROVIDER=anthropic` | Anthropic API key |
| `DATABASE_URL` | string | No (default: SQLite) | `postgresql://...` for production |
| `CHROMA_PERSIST_DIR` | string | No (default: `./data/chroma`) | Vector store location |
| `UPLOAD_DIR` | string | No (default: `./data/uploads`) | File upload location |
| `MAX_UPLOAD_MB` | int | No (default: `50`) | Upload size limit |

## Notable Versions

- Python: 3.12 (slim base image)
- Node.js: 20 (Alpine base image)
- FastAPI: 0.135+ (latest)
- Next.js: 14.2+ (App Router)
- React: 18.3+
- TypeScript: 5
- SQLAlchemy: 2.0+ (async-first)
- Alembic: 1.18+ (migration management)
- LlamaIndex: 0.14+ (latest workflow API with context.store.set/get)
- Vitest: 4.0+ (modern, Vite-native test runner)

---

*Stack analysis: 2026-03-27*
