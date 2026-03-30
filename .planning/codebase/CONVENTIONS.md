# Coding Conventions

**Analysis Date:** 2026-03-27

## Naming Patterns

### Files

**Backend Python:**
- Modules: `snake_case.py` (e.g., `context_builder.py`, `document_parser.py`)
- Classes: PascalCase inside modules
- Routes: `routes/chat.py`, `routes/projects.py` — route files organized by domain

**Frontend TypeScript/React:**
- Components: PascalCase with `.tsx` extension (e.g., `TopBar.tsx`, `ModeInputBox.tsx`)
- Hooks: `use*` prefix with `.ts` extension (e.g., `useAIBuddyChat.ts`, `useProjectOps.tsx`)
- Utilities: `camelCase.ts` (e.g., `mindMapLayout.ts`, `parseRelatedTerms.ts`)
- Tests: `Component.test.tsx` or `hook.test.ts` (co-located with implementation or in `tests/` directory)

### Functions and Methods

**Python:**
- Functions: `snake_case` (e.g., `_extract_requirements()`, `build_with_sources()`)
- Private functions: `_leading_underscore()` (e.g., `_has_m1_context()`)
- Async functions: `async def function_name()`
- Class methods: follow same `snake_case` pattern with `self` as first parameter

**TypeScript:**
- Functions: `camelCase` (e.g., `addMessage()`, `resetStreamTimeout()`)
- Async functions: `async function name()` or `const name = async () => {}`
- Hooks: `useHookName()` returning object with properties (e.g., `useAIBuddyChat()` returns `{ messages, progress, send, isLoading }`)
- Event handlers: `handleEventName()` (e.g., `handleCreate()`, `handleKeyDown()`)

### Variables

**Python:**
- Local variables: `snake_case` (e.g., `test_cases`, `rag_context`, `project_id`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `_DUPE_CERTAIN_THRESHOLD = 0.98`, `SSE_DONE = "data: [DONE]\n\n"`)
- Module-level singletons: `_embed_model_singleton` (leading underscore, snake_case)

**TypeScript:**
- Local variables: `camelCase` (e.g., `messages`, `projectId`, `filePaths`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `STORAGE_KEY = (projectId: string) => ...`)
- React state: `camelCase` (e.g., `const [isLoading, setIsLoading] = useState(false)`)
- Record/object keys: `snake_case` when matching backend JSON (e.g., `project_id`, `created_at`)

### Types and Interfaces

**TypeScript:**
- Interfaces: PascalCase (e.g., `ChatMessage`, `AuditData`, `ModeInputBoxProps`)
- Type aliases: PascalCase (e.g., `type MessageRole = "user" | "assistant" | "system"`)
- Enum-like objects: PascalCase key, UPPERCASE value names (e.g., `const MODE_LABELS: Record<Mode, string>`)
- Generic type parameters: SingleLetter (e.g., `<T>`, `<K, V>`)

**Python:**
- Pydantic models: PascalCase (e.g., `ChatRequest`, `Settings`)
- TypedDicts: PascalCase (e.g., `ChatSource`)
- ORM models: PascalCase (e.g., `Project`, `ProjectFile`, `AuditSnapshot`)

## Code Style

### Formatting

**Python:**
- 4-space indentation (PEP 8)
- Line length: no strict limit, but aim for readability (typically under 100 chars for code, longer acceptable for URLs/comments)
- No explicit formatter configured (eslint/prettier not used); code follows implicit PEP 8 standards

**TypeScript/React:**
- 2-space indentation (Next.js/React convention)
- Line length: no strict limit; pragmatic wrapping for readability
- No explicit formatter configured; code follows Tailwind CSS utility conventions and Next.js style

### Comments and Documentation

**Python:**
- Module-level docstrings: triple-quoted with purpose and usage (e.g., `"""Parse an in-memory .docx and verify the returned structure."""`)
- Function docstrings: brief description of what the function does; no param/return annotations in docstrings (types are in signatures)
- Inline comments: rare; code is self-documenting; comments explain "why" not "what"
- Section comments: `# ─── Section Name ────────────────────` (dashes for visual separation)

**TypeScript:**
- JSDoc/TSDoc: Used for exported functions and hooks (e.g., `/** useAIBuddyChat – Custom hook ... */`)
- Component props: documented inline with `/** comment */` above prop in interface
- Inline comments: minimal; prefer descriptive names and clear logic
- Section comments: `// ── Section Name ──────────────────────` (dashes for visual separation)

## Import Organization

### Python

**Order:**
1. Standard library imports (`import os`, `import json`, `import logging`)
2. Third-party imports (`from fastapi import ...`, `from pydantic import ...`, `from sqlalchemy import ...`)
3. Local imports (`from app.core.config import settings`, `from app.db.models import Project`)

**Pattern:** Explicit imports preferred (e.g., `from app.api.sse import SSE_DONE, sse_event` not `from app.api import sse`)

### TypeScript

**Order:**
1. Next.js imports (`import { useRouter } from "next/navigation"`)
2. React imports (`import { useState, useCallback } from "react"`)
3. Third-party imports (`import { describe, it } from "vitest"`)
4. Local component/lib imports (`import TopBar from "../components/TopBar"`, `import { useProjects } from "../lib/useProjects"`)
5. Style imports (Tailwind via `className`, no separate CSS imports in most cases)

**Path Aliases:**
- `@/*` → root directory (configured in `tsconfig.json`)
- Usage: `import { useProjects } from "@/lib/useProjects"` (works from any depth)

## Error Handling

### Python

**Patterns:**
- Try/except with specific exception types, not bare `except:` (e.g., `except ImportError:`, `except Exception as exc:`)
- Logging errors with context: `logger.warning("message: %s", variable)`
- Graceful fallback: functions return `None` or empty list on error, don't crash
- Example from `core/llm.py`:
  ```python
  try:
      from llama_index.llms.anthropic import Anthropic
      return Anthropic(...)
  except ImportError:
      logger.warning("llama-index-llms-anthropic not installed; LLM disabled")
      return None
  ```

**Workflow Error Handling:**
- LlamaIndex Workflows yield `AnalysisProgressEvent` for intermediate updates
- Final `StopEvent` contains result data or error flag
- Workflows don't raise exceptions; they capture and report via events
- Example: audit workflow logs warning if M1 context not found, continues with fallback

### TypeScript/React

**Patterns:**
- Try/catch in SSE fetch: `catch { setError("message") }`
- Silent catches for non-critical operations (e.g., `catch { /* quota exceeded — ignore */ }`)
- Error state management: `const [error, setError] = useState<string | null>(null)`
- User-facing errors: Polish messages (e.g., `"Odpowiedź trwa zbyt długo. Spróbuj ponownie."`)
- Console errors avoided in production code; logging to stderr via SSE events

**Validation:**
- Guard clauses: `if (!text.trim() && filePaths.length === 0) return;`
- Null checks with optional chaining: `const name = project?.name ?? "Unknown"`

## Logging

### Python

**Framework:** Built-in `logging` module (no external logger)

**Setup:**
```python
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai_buddy.module_name")
```

**Levels:**
- `logger.info()` — workflow progress, startup messages
- `logger.warning()` — optional path, feature disabled gracefully
- `logger.error()` — expected failures (not exceptions, just errors in logic)
- `logger.debug()` — rarely used; add when debugging

**Patterns:**
- Include context in log messages: `logger.info("project=%s — skipping RAG", project_id)`
- Use `%s` formatting, not f-strings: `logger.warning("Failed to load: %s", exc)`

### TypeScript

**Framework:** No external logger; uses `console` for server logging, SSE events for client progress

**Frontend:**
- No console.log in production code (tests use mocks)
- Progress reported via `setProgress({ message: "...", progress: 0.5 })`
- Errors displayed to user via `setError("...")`

**Backend (edge cases):**
- `console` not used; all logs via Python logger
- Status messages passed to client via SSE `AnalysisProgressEvent`

## Parameter and Return Patterns

### Python Functions

**Parameters:**
- Keyword arguments for optional values: `def parse(self, path: str, format: str = "docx")`
- Type hints always present: `def process(items: List[Dict[str, Any]]) -> Dict`
- Context managers preferred for resource cleanup: `async with AsyncSessionLocal() as db:`

**Return values:**
- Tuple unpacking for multiple returns: `rag_context, rag_sources = await builder.build_with_sources(...)`
- Optional returns: `Optional[Dict]` with explicit `None` on error paths
- Exception-as-tuple pattern rare; prefer logging + None return

### TypeScript Functions

**Parameters:**
- Destructured props in React components: `function TopBar({ projectId, onTogglePanel }: TopBarProps)`
- Default parameters: `tier: "audit" | "optimize" = "audit"`
- Callback functions often include options: `send(text: string, filePaths: string[] = [], opts: { skipUserMessage?: boolean } = {})`

**Return values:**
- Objects over tuples: `return { messages, progress, send, isLoading }`
- Promises always typed: `async () => Promise<Project | null>`
- Union types for nullable returns: `Optional<Dict> → Dict | null` in TypeScript

## Async Patterns

### Python

**LlamaIndex Workflows:**
- All steps are `async def step_name(self, ctx: Context, ev: EventType)`
- Context store accessed via `await ctx.store.set/get("key", value)`
- Events written via `ctx.write_event_to_stream(ProgressEvent(...))`
- Concurrent operations: `asyncio.gather(*tasks)` for parallel calls

**Database:**
- All DB operations use `AsyncSessionLocal()`: `async with AsyncSessionLocal() as db:`
- Queries use `await db.execute(stmt)` then `.scalars().all()`
- No synchronous database calls

### TypeScript/React

**Hooks:**
- `useCallback` for memoized function definitions
- `useEffect` for side effects with dependency arrays: `useEffect(() => {...}, [value, resizeTextarea])`
- SSE streaming: `fetch().then(res => res.body?.getReader())`

**Async operations:**
- `const result = await fetch(...)` pattern
- Error handling: `catch` blocks with cleanup (`abortRef.current?.abort()`)
- Abort controller for request cancellation

## Module Design and Exports

### Python

**Barrel files:**
- `__init__.py` imports main exports: `from app.db.models import Project, ProjectFile`
- Routes included in main app: `app.include_router(chat.router, prefix="/api/chat")`
- Single responsibility: each module handles one concern (parsers, routes, workflows)

**Public vs. Private:**
- Leading underscore for internal helpers: `_has_m1_context()`, `_make_minimal_pdf()`
- Public functions/classes: no prefix
- Internal imports: `from app.agents import AuditWorkflow` (public), `from app.rag.context_builder import _build_embed_model` (avoid)

### TypeScript

**Export patterns:**
- Named exports for components: `export default function TopBar({ ... })`
- Named exports for utilities: `export function useAIBuddyChat() {...}`
- Type exports: `export interface ChatMessage { ... }`, `export type MessageRole = ...`
- No barrel files (no `index.ts` re-exporting); imports are direct

**React conventions:**
- `"use client"` directive at top for client components (all interactive components)
- Hooks exported from `lib/` directory; components from `components/`
- Context providers wrap children: `<ProjectOperationsProvider>{children}</ProjectOperationsProvider>`

## Naming Edge Cases

**Project IDs:**
- Always `project_id` (snake_case in Python, camelCase `projectId` in TypeScript)
- Type: string UUID, never numeric

**Timestamps:**
- Python: `datetime.now(timezone.utc)` (timezone-aware)
- TypeScript: `new Date()` (ISO string in JSON, converted to Date on client)
- Field name: `created_at` (snake_case in DB), `createdAt` (camelCase in some TS interfaces)

**Boolean prefixes:**
- `is_*` pattern: `is_indexed()`, `is_running`, `is_loading`
- `can_*` pattern: `can_send`
- `has_*` pattern: `has_m1_context()`

---

*Convention analysis: 2026-03-27*
