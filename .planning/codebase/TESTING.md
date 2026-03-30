# TESTING.md — Test Structure & Practices

## Overview

The project has two separate test suites: **pytest** for the backend (Python) and **Vitest** for the frontend (TypeScript/React).

---

## Backend — pytest

### Running Tests

```bash
cd backend

# All tests
pytest

# Specific file
pytest tests/test_m1_context.py -v

# Specific test function
pytest tests/test_m1_context.py::test_context_builder_build -v

# With coverage
pytest --cov=app --cov-report=html
```

### Framework & Config

- **Framework**: pytest + pytest-asyncio
- **HTTP client**: `httpx.AsyncClient` with FastAPI's `ASGITransport` (not TestClient)
- **Config**: `conftest.py` — env var overrides set *before* any app module imports
- **DB**: Isolated temp SQLite per test session (`sqlite+aiosqlite:///tmp/.../test.db`)
- **Vector store**: Isolated temp Chroma dir per test session
- **Upload dir**: Isolated temp dir per test session

### Test Organization

```
backend/tests/
├── conftest.py                      — Shared fixtures + env bootstrap
├── mapping_helpers.py               — Shared helpers for mapping tests
├── fixtures/
│   ├── sample_domain.docx           — Minimal QA domain doc for M1 unit tests
│   ├── sample_tests.csv             — 5 fake test cases
│   └── synthetic_docs/              — Rich synthetic QA corpus for integration tests
│       ├── srs_payment_module.docx  — 12 FRs, glossary, domain actors
│       ├── test_plan_payment.docx   — Scope, environments, risk register
│       └── qa_process.docx          — Defect lifecycle, severity, roles
├── test_m1_context.py               — 13 unit + endpoint tests (M1 pipeline)
├── test_m1_e2e.py                   — 5 e2e tests + 1 skipped (needs real API key)
├── test_m1_manual.py                — M1 pipeline manual/integration test
├── test_m1_m2_integration.py        — Full M1→M2 integration: audit, RAG chat, coverage, snapshots
├── test_audit_integration.py        — M2 audit integration tests
├── test_projects.py                 — Project CRUD endpoint tests
├── test_snapshots.py                — 11 tests: snapshots + audit-selection endpoints
├── test_rag_ready_isolation.py      — 4 regression tests for rag_ready flag correctness
├── test_reflection.py               — 15 tests: reflection loop (M1 + Faza 2)
├── test_requirements.py             — Faza 2 extraction tests
├── test_requirements_extended.py    — Extended Faza 2 edge cases
├── test_requirements_rag_quality.py — RAG retrieval quality for requirements extraction
├── test_mapping.py                  — Faza 5+6 mapping + scoring tests
└── test_mapping_extended.py         — Extended mapping edge cases
```

### Fixtures Pattern (`conftest.py`)

```python
# Env vars set BEFORE any app module import (critical ordering)
os.environ["CHROMA_PERSIST_DIR"] = os.path.join(_TEST_TMP, "chroma")
os.environ["UPLOAD_DIR"] = os.path.join(_TEST_TMP, "uploads")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_TMP}/test.db"

@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_tmp():
    yield
    shutil.rmtree(_TEST_TMP, ignore_errors=True)

@pytest.fixture
def sample_docx_path():
    return str(Path(__file__).parent / "fixtures" / "sample_domain.docx")
```

### HTTP Client Pattern

```python
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/projects/")
        assert response.status_code == 200
```

### SSE Testing Pattern

```python
async with client.stream("POST", f"/api/context/{project_id}/build", ...) as resp:
    async for line in resp.aiter_lines():
        if line.startswith("data:"):
            event = json.loads(line[5:])
            if event["type"] == "result":
                result = event["data"]
```

### Mocking Strategy

- **LLM calls**: `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY=test-key-placeholder` → workflows use mock/fallback paths when API key is invalid
- **Chroma**: Real Chroma instance in isolated temp dir (no mocking)
- **DB**: Real async SQLite in isolated temp dir (no mocking)
- **File system**: Real temp dirs managed by session-scoped fixture

### Test Categories

| File | Category | Count |
|------|----------|-------|
| `test_m1_context.py` | Unit + endpoint | 13 |
| `test_m1_e2e.py` | E2E | 5 (+1 skipped) |
| `test_m1_m2_integration.py` | Integration | ~10 |
| `test_snapshots.py` | Endpoint | 11 |
| `test_rag_ready_isolation.py` | Regression | 4 |
| `test_reflection.py` | Unit | 15 |

---

## Frontend — Vitest

### Running Tests

```bash
cd frontend

# All tests (watch mode)
npm test

# Single run
npm test -- --run

# Specific file
npm test -- tests/MindMapModal.test.tsx --run
```

### Framework & Config

- **Framework**: Vitest + React Testing Library + `@testing-library/jest-dom`
- **Environment**: `jsdom` (simulates browser DOM)
- **Config**: `frontend/vitest.config.ts`
- **Setup**: `frontend/tests/setup.ts` — imports `@testing-library/jest-dom`
- **Module alias**: `@` → project root (mirrors tsconfig)

```typescript
// vitest.config.ts
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, ".") },
  },
});
```

### Test Organization

```
frontend/tests/
├── setup.ts                    — Global test setup (@testing-library/jest-dom)
├── TopBar.test.tsx             — 11 tests: renders, RAG indicator, panel toggle
├── ModeInputBox.test.tsx       — 19 tests: mode pills, file chips, send/stop
├── MindMapModal.test.tsx       — 21 tests: visibility, toolbar, node rendering, cycle-safety
├── UtilityPanel.test.tsx       — 37 tests: panel sections, mode-specific content
├── RequirementsView.test.tsx   — 36 tests: header stats, filter, cards, collapse
├── ProjectPage.test.tsx        — 13 tests: page renders per mode, hook wiring
├── ProjectList.test.tsx        — 8 tests: list, create, empty state, navigation
├── ProjectSettingsPage.test.tsx — 11 tests: form, save, error, navigation
├── MindMap.test.tsx            — 9 tests: SVG nodes/edges, pan/zoom, empty state
├── Glossary.test.tsx           — 10 tests: filter, empty state, term click, hover
├── MessageList.test.tsx        — 5 tests: bubbles, related terms chips, term click
├── AuditHistory.test.tsx       — 5 tests: snapshots, coverage badge colors, trend chart
├── mindMapLayout.test.ts       — 13 tests: layoutModalNodes + cycle-safety
├── parseRelatedTerms.test.ts   — 3 tests: term splitting logic
├── useAIBuddyChat.test.ts      — 27 tests: localStorage, SSE streaming, per-project isolation
├── useAuditPipeline.test.ts    — 12 tests: pipeline orchestration, guards, sequential order
└── useRequirements.test.ts     — 8 tests: fetch, SSE extract, patch, re-mount after navigation
```

Total: **248 tests across 17 files**

### Component Test Pattern

```typescript
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import TopBar from "@/components/TopBar";

describe("TopBar", () => {
  it("renders project name", () => {
    render(<TopBar projectId="123" projectName="My Project" ragReady={false} />);
    expect(screen.getByText("My Project")).toBeInTheDocument();
  });
});
```

### Hook Test Pattern

```typescript
import { renderHook, act } from "@testing-library/react";
import { useRequirements } from "@/lib/useRequirements";

it("fetches requirements on mount", async () => {
  const { result } = renderHook(() => useRequirements("project-123"));
  await act(async () => { /* wait for effects */ });
  expect(result.current.requirements).toHaveLength(3);
});
```

### Mocking Strategy (Frontend)

- **fetch / API calls**: `vi.fn()` replacing `global.fetch` per test
- **SSE streams**: Mock `ReadableStream` with encoded event chunks
- **localStorage**: Real jsdom localStorage (isolated per test via `vi.clearAllMocks()`)
- **React Router / Next.js**: `useSearchParams`, `useRouter` mocked via `vi.mock("next/navigation", ...)`
- **Recharts**: Partially mocked where SVG rendering fails in jsdom

### SSE Mock Pattern (Frontend)

```typescript
global.fetch = vi.fn().mockResolvedValue({
  ok: true,
  body: new ReadableStream({
    start(controller) {
      const enc = new TextEncoder();
      controller.enqueue(enc.encode('data: {"type":"progress","data":{"message":"Processing...","progress":0.5}}\n\n'));
      controller.enqueue(enc.encode('data: {"type":"result","data":{...}}\n\n'));
      controller.close();
    }
  })
});
```

### data-testid Conventions

Components use `data-testid` for test targeting:
- `data-testid="mode-pill-{mode}"` — ModeInputBox mode pills
- `data-testid="mm-node-{id}"` — MindMapModal nodes
- `data-testid="req-module-group"` — RequirementsView module groups

---

## Coverage Areas

### What is tested
- All API route handlers (via ASGI test client)
- M1 pipeline steps individually (parser, context builder, workflow)
- M2 audit + optimize workflow result shapes
- Faza 2 requirements extraction + review + persist
- Faza 5+6 mapping + coverage scoring
- Snapshot persistence, diff computation, max-5 pruning
- `rag_ready` isolation (regression: M2-only files must not set rag_ready=True)
- Reflection loop: no-llm passthrough, disabled via env, max-iterations cap, failure fallback
- All React components (render, interaction, conditional display)
- All custom hooks (state transitions, SSE streaming, navigation re-mount)
- Mind map cycle safety (direct cycles, multi-hop cycles, LLM-style numeric IDs)
- `layoutModalNodes` dagre layout function

### What is NOT tested (known gaps)
- Bedrock LLM provider path (requires real AWS credentials)
- Real Anthropic API calls (test key is invalid; e2e test `test_m1_e2e.py::f` skipped)
- Confluence/Jira connector ingestion (not yet implemented)
- Regenerate workflow (Tier 3 — not yet implemented)
- Docker compose integration
- End-to-end browser tests (no Playwright/Cypress)
