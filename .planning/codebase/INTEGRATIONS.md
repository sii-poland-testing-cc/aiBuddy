# External Integrations

**Analysis Date:** 2026-03-27

## APIs & External Services

**LLM Services:**
- **AWS Bedrock (default)** - Claude LLM inference via API
  - SDK: `llama-index-llms-bedrock-converse` 0.14+
  - Model: `anthropic.claude-3-5-sonnet-20241022-v2:0` (configurable via `BEDROCK_MODEL_ID` env var)
  - Max tokens: 16000 (hard-coded in `backend/app/core/llm.py`)
  - Auth: AWS IAM credentials (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`)
  - Fallback: `llm = None` when credentials missing (workflows still work heuristically)

- **Anthropic Claude API** - Alternative LLM provider
  - SDK: `llama-index-llms-anthropic` 0.11+
  - Model: `claude-sonnet-4-6` (configurable via `ANTHROPIC_MODEL_ID` env var)
  - Max tokens: 16000 (hard-coded)
  - Auth: `ANTHROPIC_API_KEY` env var
  - Activation: Set `LLM_PROVIDER=anthropic` in `.env`
  - Usage: M1 context extraction, M2 audit analysis, Faza 2 requirements extraction

**Embedding Models:**
- **HuggingFace BAAI/bge-m3** - Multilingual sentence embeddings (non-Bedrock default)
  - SDK: `llama-index-embeddings-huggingface` 0.7+
  - Model: `BAAI/bge-m3` (100+ languages, ~560 MB, first download only)
  - Cache: Stored in HuggingFace cache directory (`~/.cache/huggingface/hub/`)
  - Override: `EMBED_MODEL_NAME` env var
  - Activation: Auto-selected when `LLM_PROVIDER != bedrock`

- **AWS Bedrock Titan** - Embedding service when using Bedrock
  - SDK: `llama-index-embeddings-bedrock` 0.8+
  - Model: `amazon.titan-embed-text-v2:0` (configurable via `BEDROCK_EMBED_MODEL_ID`)
  - Auth: Same AWS credentials as Bedrock LLM

## Data Storage

**Databases:**
- **SQLite (development)** - Default relational database
  - Connection: `sqlite+aiosqlite:///./data/ai_buddy.db` (default `DATABASE_URL`)
  - Driver: `aiosqlite` 0.22+ (async SQLite)
  - Tables: `projects`, `project_files`, `audit_snapshots`, `requirements`, `requirement_tc_mappings`, `coverage_scores`
  - Migrations: Alembic (`backend/migrations/versions/001_initial_schema.py`)
  - Foreign keys: Enabled per-connection via PRAGMA in `backend/app/db/engine.py`

- **PostgreSQL (production)** - Swap from SQLite
  - Connection: Override `DATABASE_URL` in `.env` to `postgresql://user:pass@host/dbname`
  - Driver: SQLAlchemy built-in PostgreSQL support
  - Same schema as SQLite (managed by Alembic)

**Vector Store (RAG):**
- **Chroma** - Vector database for semantic search
  - SDK: `llama-index-vector-stores-chroma` 0.5+
  - Storage: Persistent on disk at `./data/chroma/` (configurable via `CHROMA_PERSIST_DIR`)
  - Collections: Per-project (one collection per `project_id` for M1 context + M2 audit files)
  - Index size: Tuned by `RAG_CHUNK_SIZE` (1024 tokens), `RAG_CHUNK_OVERLAP` (128 tokens)
  - Retrieval: `RAG_TOP_K` (10 nodes per query), `RAG_MAX_CONTEXT_CHARS` (60000 hard cap)
  - Manager: `backend/app/rag/context_builder.py` - `build_with_sources()`, `index_files()`, `retrieve_nodes()`

**File Storage:**
- **Local filesystem** - Uploaded test files and M1 context documents
  - Location: `./data/uploads/{project_id}/` (configurable via `UPLOAD_DIR`)
  - Subdirectories: `./data/uploads/{project_id}/context/` for M1 docs
  - Max size: 50 MB per file (configurable via `MAX_UPLOAD_MB`)
  - Allowed types: `.xlsx .csv .json .pdf .feature .txt .md .docx` (configurable)
  - Note: Production should use cloud storage (S3, GCS) or persistent volume

**Caching:**
- **In-memory write-through cache** - Artefacts (mind map, glossary, context stats)
  - Singleton dict: `_context_store` in `backend/app/api/routes/context.py`
  - Lifespan: Server session (survives DB restarts)
  - Fallback: DB query on cache miss (warm cache on hit)

## Authentication & Identity

**Auth Provider:**
- **Custom (none implemented)** - No user authentication layer
  - All endpoints are public
  - Projects are scoped by `project_id` (UUID), not user identity
  - Frontend stores selected project in URL (`/project/[projectId]`)
  - Each project isolated by UUID (weak security without auth; suitable for single-user or trusted team)

## Monitoring & Observability

**Error Tracking:**
- **Not detected** - No Sentry/error reporting integration
  - Errors logged to stdout/stderr via Python logging

**Logging:**
- **Python logging module** - Standard library
  - Root logger name: `ai_buddy` (configured in `backend/app/main.py`)
  - Level: `INFO` (development can override)
  - Output: Console (stdout/stderr via uvicorn)
  - No persistent log storage (relogs lost on container restart)

**Observability:**
- **OpenTelemetry (transitive)** - Imported but not actively used
  - Packages: `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-grpc`
  - Likely inherited from LlamaIndex dependencies
  - Not instrumented in codebase

## CI/CD & Deployment

**Hosting:**
- **Docker Compose (development/local)** - Full-stack orchestration
  - Config: `docker-compose.yml`
  - Services: Backend (FastAPI on 8000), Frontend (Next.js on 3000)
  - Volumes: Bind-mount source for hot-reload, named volume for data persistence
  - Environment vars: Passed from host `.env` file

- **Docker (containerized)** - Deployable anywhere
  - Backend image: `python:3.12-slim` with uvicorn
    - Build: `backend/Dockerfile`
    - Expose: Port 8000
  - Frontend image: `node:20-alpine` with npm
    - Build: `frontend/Dockerfile`
    - Expose: Port 3000
  - Recommended platforms: AWS ECS, Kubernetes, Railway, Fly.io, Heroku

**CI Pipeline:**
- **Not detected** - No GitHub Actions, GitLab CI, or other CI config
  - Tests exist but no automated test pipeline found
  - Run locally: `pytest` (backend), `npm test` (frontend)

## Webhooks & Callbacks

**Incoming:**
- **Not detected** - No webhook endpoints for external services

**Outgoing:**
- **Not detected** - No outbound webhooks or event notifications
  - Note: Jira/Confluence connectors planned (schema fields exist but not implemented) - would be outbound integrations

## Environment Configuration

**Required env vars (Bedrock):**
```bash
LLM_PROVIDER=bedrock
AWS_REGION=eu-central-1
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
```

**Required env vars (Anthropic):**
```bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

**Optional env vars:**
```bash
DATABASE_URL=sqlite+aiosqlite:///./data/ai_buddy.db   # Swap to PostgreSQL in prod
CHROMA_PERSIST_DIR=./data/chroma
UPLOAD_DIR=./data/uploads
MAX_UPLOAD_MB=50
M1_WORKFLOW_TIMEOUT_SECONDS=1800
M2_WORKFLOW_TIMEOUT_SECONDS=300
REQUIREMENTS_WORKFLOW_TIMEOUT_SECONDS=1800
REFLECTION_MAX_ITERATIONS=2
RAG_CHUNK_SIZE=1024
RAG_CHUNK_OVERLAP=128
RAG_TOP_K=10
RAG_MAX_CONTEXT_CHARS=60000
```

**Secrets location:**
- `.env` file (not committed, created from `.env.example`)
- For production: Use CI/CD secrets or container orchestration secret management (Kubernetes Secrets, AWS Secrets Manager, etc.)

## Data Processing Pipelines

**Document Ingestion (M1):**
- **Input formats**: `.docx` (python-docx), `.pdf` (pdfplumber or pypdf)
- **Output**: Text chunks + table rows indexed into Chroma
- **Location**: `backend/app/parsers/document_parser.py`

**Test File Ingestion (M2):**
- **Input formats**: `.xlsx` (openpyxl), `.csv` (pandas), `.json`, `.pdf`, `.feature`, `.txt`, `.md`
- **Output**: Parsed test cases indexed into Chroma
- **Location**: `backend/app/parsers/test_case_parser.py`

**LLM Batch Processing:**
- **Concurrent calls**: Capped at `LLM_CONCURRENT_CALLS=4` (prevents API rate limiting)
- **Workflow timeouts**:
  - M1: 1800 seconds (30 min for large document corpora)
  - M2: 300 seconds (5 min for test audit)
  - Faza 2: 1800 seconds (with reflection loops)

## API Client Libraries

**HuggingFace Hub:**
- `huggingface-hub[inference]` 1.7+ - Model download + caching
  - Used by `sentence-transformers` to fetch BAAI/bge-m3 embedding model
  - No API key required (public models)

**AWS SDK:**
- `boto3` 1.40+ - AWS API client
- `aioboto3` 15.5+ - Async wrapper (transitive)
- `botocore` 1.40+ - Low-level AWS service library

**HTTP Clients:**
- `httpx` 0.28+ - Modern async HTTP library (used by LlamaIndex)
- `requests` 2.32+ - Fallback HTTP library (transitive)

## Third-Party UI Components

**LlamaIndex Chat UI:**
- `@llamaindex/chat-ui` 0.6+ - Pre-built React chat component
  - Location: `frontend/lib/useAIBuddyChat.ts` (hooks for SSE streaming)
  - Rendering: Custom implementation in `frontend/components/MessageList.tsx`

## Known Integration Gaps

- **Jira connector** — Schema field exists (`source_type="jira"`) but no ingestion pipeline
- **Confluence connector** — Schema field exists (`source_type="confluence"`) but only planned (M1.2.3 roadmap)
- **Regenerate workflow** — M2 Tier 3 not implemented (Audit + Optimize complete)
- **Error tracking** — No Sentry/Rollbar integration
- **Persistent logging** — No centralized log aggregation
- **S3/cloud storage** — File uploads stored locally only (fine for dev, needs cloud swap for prod)

---

*Integration audit: 2026-03-27*
