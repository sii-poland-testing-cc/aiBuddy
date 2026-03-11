# AI Buddy — QA Agent Platform

> **Test Suite Audit & Optimization**, powered by LlamaIndex Workflows + Amazon Bedrock

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      Frontend (Next.js 14)               │
│  Sidebar: Projects + Files │ Chat UI │ Pipeline Steps    │
└──────────────────────┬──────────────────────────────────┘
                       │  SSE Stream  (POST /api/chat/stream)
┌──────────────────────▼──────────────────────────────────┐
│                   Backend (FastAPI)                       │
│                                                           │
│  /api/chat     →  LlamaIndex Workflow dispatcher          │
│  /api/projects →  Project CRUD                            │
│  /api/files    →  Upload + RAG indexing                   │
│                                                           │
│  ┌─────────────────────────────────────────────────┐     │
│  │         LlamaIndex Workflows                    │     │
│  │  Tier 1: AuditWorkflow       ✅ implemented     │     │
│  │  Tier 2: OptimizeWorkflow    ✅ implemented     │     │
│  │  Tier 3: RegenerateWorkflow     coming soon     │     │
│  └──────────────────────────┬──────────────────────┘     │
│                             │                             │
│  ┌──────────────────────────▼──────────────────────┐     │
│  │  RAG / ContextBuilder                           │     │
│  │  • Chroma (local dev)                           │     │
│  │  • pgvector (production)                        │     │
│  │  • BedrockEmbedding (titan-embed-text-v2)       │     │
│  └─────────────────────────────────────────────────┘     │
│                                                           │
│  DB: SQLite/aiosqlite (dev) · PostgreSQL/asyncpg (prod)   │
│  LLM: Amazon Bedrock (Claude 3.5 Sonnet by default)       │
└───────────────────────────────────────────────────────────┘
```

## Three-Tier Service Model

| Tier | Workflow | Input | Output |
|------|----------|-------|--------|
| 1 — **Audit** | `AuditWorkflow` | `.xlsx/.csv/.feature` test suite | Gap report, duplicates, coverage % |
| 2 — **Optimize** | `OptimizeWorkflow` | Audit report + original files | Deduplicated suite with LLM-assigned tags & priorities |
| 3 — **Regenerate** | `RegenerateWorkflow` *(soon)* | Confluence docs / requirements | New test cases in Gherkin / table format |

### Workflow event flow

```
Tier 1 — Audit
  StartEvent → ParsedEvent → AuditResultEvent → StopEvent
  progress events: AnalysisProgressEvent (0.2 → 0.9)

Tier 2 — Optimize
  StartEvent → PreparedEvent → DeduplicatedEvent → StopEvent
  progress events: OptimizeProgressEvent (0.15 → 0.95)
```

Both tiers stream `{ type: "progress" | "result" | "error", data: {...} }` SSE events.

---

## Quick Start

### Prerequisites
- Python 3.12+
- Node.js 20+
- AWS credentials with Bedrock access (`claude-3-5-sonnet`, `titan-embed-text-v2`)

### 1. Clone & setup

```bash
git clone <your-repo>
cd ai-buddy
```

### 2. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Copy and fill in your AWS credentials
cp .env.example .env

python app/main.py   # or: uvicorn app.main:app --reload
```

The SQLite database (`data/ai_buddy.db`) and upload directory (`data/uploads/`) are created automatically on first boot.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Enter a project ID to start a chat session.

### 4. Docker (full stack)

```bash
docker compose up --build
```

---

## Project Structure

```
ai-buddy/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── audit_workflow.py      # Tier 1 — parse → analyse → report
│   │   │   └── optimize_workflow.py   # Tier 2 — prepare → deduplicate → tag
│   │   ├── api/routes/
│   │   │   ├── chat.py                # SSE streaming endpoint + workflow dispatcher
│   │   │   ├── projects.py            # Project CRUD (SQLAlchemy)
│   │   │   └── files.py               # Upload + RAG indexing (SQLAlchemy)
│   │   ├── core/
│   │   │   └── config.py              # Pydantic settings
│   │   ├── db/
│   │   │   ├── models.py              # Project + ProjectFile ORM models
│   │   │   └── engine.py              # Async engine, get_db dependency, init_db
│   │   ├── rag/
│   │   │   └── context_builder.py     # Chroma + Bedrock embeddings
│   │   └── main.py                    # FastAPI app + lifespan
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── app/
│   │   ├── page.tsx                   # Landing — project ID entry
│   │   └── chat/[projectId]/page.tsx  # Chat page
│   ├── components/
│   │   ├── Sidebar.tsx                # Project list + file upload + user footer
│   │   ├── MessageList.tsx            # Message bubbles + typing indicator
│   │   ├── ChatInputArea.tsx          # Textarea, file chips, send/stop
│   │   └── PipelineSteps.tsx          # Audit → Optimize → Regenerate badges
│   └── lib/
│       ├── useAIBuddyChat.ts          # SSE hook
│       ├── useChatAdapter.ts          # Adapter → @llamaindex/chat-ui interface
│       ├── useProjects.ts             # Project CRUD hook
│       └── useProjectFiles.ts         # File upload + list hook
│
└── docker-compose.yml
```

---

## API Reference

### `POST /api/chat/stream`

Runs a workflow and streams SSE events.

```json
{
  "project_id": "string",
  "message": "string",
  "file_paths": ["string"],
  "tier": "audit | optimize | regenerate",
  "audit_report": {}
}
```

`audit_report` is required when `tier = "optimize"` — pass the full result object from a prior Tier 1 run.

### `GET /api/projects` · `POST /api/projects`

```json
{ "name": "My Suite", "description": "optional" }
```

Response includes `project_id`, `name`, `description`, `created_at`, `file_count`.

### `POST /api/files/{project_id}/upload`

Multipart upload. Accepted extensions: `.xlsx .csv .json .pdf .feature .txt .md`. Max size: 50 MB per file. Files are indexed into the RAG vector store automatically.

### `GET /api/files/{project_id}`

Returns `filename`, `file_path`, `size_bytes`, `indexed`, `uploaded_at` for each uploaded file.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `bedrock` | `bedrock` or `anthropic` |
| `AWS_REGION` | `eu-central-1` | Bedrock region |
| `AWS_ACCESS_KEY_ID` | — | AWS key (required for `bedrock`) |
| `AWS_SECRET_ACCESS_KEY` | — | AWS secret (required for `bedrock`) |
| `BEDROCK_MODEL_ID` | `anthropic.claude-3-5-sonnet-20241022-v2:0` | Chat LLM (Bedrock) |
| `BEDROCK_EMBED_MODEL_ID` | `amazon.titan-embed-text-v2:0` | Embedding model (always Bedrock) |
| `ANTHROPIC_API_KEY` | — | API key (required for `anthropic`) |
| `ANTHROPIC_MODEL_ID` | `claude-sonnet-4-6` | Chat LLM (Anthropic) |
| `VECTOR_STORE_TYPE` | `chroma` | `chroma` or `pgvector` |
| `CHROMA_PERSIST_DIR` | `./data/chroma` | Chroma persistence path |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/ai_buddy.db` | Async SQLAlchemy URL |
| `UPLOAD_DIR` | `./data/uploads` | File upload root |
| `MAX_UPLOAD_MB` | `50` | Per-file upload limit |

---

## Adding a New Workflow Tier

1. Create `backend/app/agents/regenerate_workflow.py` — follow the event pattern in `audit_workflow.py` or `optimize_workflow.py`
2. Define a `*ProgressEvent` with `message: str` and `progress: float`
3. Register in `chat.py`: `workflow_map["regenerate"] = RegenerateWorkflow`
4. Update the `isinstance` check in `_run_workflow` to include the new progress event type

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Agent orchestration | LlamaIndex Workflows |
| LLM | Amazon Bedrock (Claude 3.5 Sonnet) |
| Embeddings | Amazon Bedrock Titan Embed v2 |
| Vector store | Chroma (dev) / pgvector (prod) |
| Backend | FastAPI + Uvicorn |
| Database | SQLite + aiosqlite (dev) / PostgreSQL + asyncpg (prod) |
| ORM | SQLAlchemy 2.0 async |
| Frontend | Next.js 14 + TypeScript + Tailwind CSS |
| Chat UI | `@llamaindex/chat-ui` |
| Streaming | Server-Sent Events (SSE) |
| Data parsing | pandas + openpyxl |
