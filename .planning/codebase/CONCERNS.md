# Codebase Concerns

**Analysis Date:** 2026-03-27

## Tech Debt

### 1. RAG Context Deduplication by Filename Only
**Issue:** In `build_with_sources()`, sources are deduplicated by filename only. Multiple chunks from the same file are collapsed to one excerpt.
- **Files:** `backend/app/rag/context_builder.py:90-97`
- **Impact:** When users view RAG sources in audit results, they see one representative excerpt per file, losing detail about which specific sections were retrieved. For large documents with multiple relevant sections, this is lossy.
- **Fix approach:** Implement chunk-level deduplication with excerpt diversity. Track chunk offsets and return up to N distinct excerpts per file weighted by retrieval score.

### 2. Embedding Dimension Mismatch Handling
**Issue:** When an embedding model changes (e.g., different `EMBED_MODEL_NAME`), Chroma throws an error. The code logs a warning and returns "(Context index is stale...)" but doesn't provide a programmatic recovery path.
- **Files:** `backend/app/rag/context_builder.py:101-111`
- **Impact:** Users must manually delete and rebuild context via the UI. On large corpora with M1_WORKFLOW_TIMEOUT_SECONDS=1800, this is time-consuming.
- **Fix approach:** Add automatic rebuild trigger in backend when dimension mismatch detected, or expose a `/api/context/{project_id}/rebuild-embedding-model` endpoint.

### 3. PDF Parser Fallback Chain Lacks Error Context
**Issue:** PDF parsing tries pdfplumber first, then pypdf, then returns empty content. No persistent record of what failed.
- **Files:** `backend/app/parsers/document_parser.py:72-118`
- **Impact:** Silent failures. A corrupted PDF returns `{"text": "", ...}` with no visible error to users. M1 workflow proceeds with empty context, producing low-quality extractions.
- **Fix approach:** Log detailed errors with file size + page count to help diagnose parse failures. Return structured error in result so M1 can detect and warn.

### 4. M1 Batch Extraction Depth=1 Split Recursion Uncapped
**Issue:** In `_extract_entities_batch`, when a truncated JSON response is detected at `_depth=0`, the batch is split in half recursively. But if the batch is still too large after split, recursion continues without a maximum depth guard.
- **Files:** `backend/app/agents/context_builder_workflow.py:343-358`
- **Impact:** Pathological case: a single sentence with a very long embedded table could split infinitely, exhausting memory. Current code has `_EXTRACT_MAX_RETRIES=2` but retries the whole batch, not the depth.
- **Fix approach:** Add a `_depth < 3` guard; if max depth exceeded, log error and return partial results instead of crashing.

### 5. Chroma Collection Exists Check Not Defensive
**Issue:** `collection.count()` is called without catching exceptions. If Chroma is in an inconsistent state, it can raise exceptions that are not caught at call site.
- **Files:** `backend/app/rag/context_builder.py:212-214`, `context_builder.py:80`
- **Impact:** Unhandled exceptions can crash the request. Currently wrapped in try-except at call site, but the pattern is fragile.
- **Fix approach:** Add exception handling inside `_get_collection()` to return a safe empty collection on failure.

### 6. Snapshot Auto-Prune Logic Vulnerable to Race Conditions
**Issue:** `save_snapshot()` in `services/snapshots.py` deletes oldest snapshot if count >= 5 using separate SELECT/DELETE queries.
- **Files:** `backend/app/services/snapshots.py` (referenced in CLAUDE.md)
- **Impact:** If two concurrent audit requests insert snapshots simultaneously, both may read 4 existing, insert, and neither deletes—exceeding the max-5 limit.
- **Fix approach:** Use database trigger or lock the project row during snapshot count check + insert.

## Known Bugs

### 1. Glossary Term Search Escaping Missing
**Issue:** In `frontend/components/Glossary.tsx`, search filter uses `toLowerCase().includes()` on raw term/definition strings. No regex escaping or special character handling.
- **Symptoms:** Searching for `.` or `*` will not return results even if term contains them; special chars are treated as substring match.
- **Files:** `frontend/components/Glossary.tsx`
- **Trigger:** User types special character in glossary search box
- **Workaround:** None; search by substring of alphanumeric terms only

### 2. RequirementTCMapping Query N+1 Potentia on Coverage Heatmap
**Issue:** `GET /api/mapping/{project_id}/heatmap` loads all requirements, then for each requirement, loads mappings (lazy=noload by default but called in loop).
- **Symptoms:** Heatmap loads slowly (100+ requirements = 100+ DB queries). No eager loading specified.
- **Files:** `backend/app/api/routes/mapping.py` (referenced in CLAUDE.md)
- **Trigger:** User navigates to heatmap with 50+ requirements
- **Workaround:** None; performance degrades linearly

### 3. Frontend localStorage Quota Exceeded Silent Fail
**Issue:** In `useAIBuddyChat`, `localStorage.setItem()` is wrapped in try-catch that silently ignores quota exceeded errors.
- **Symptoms:** Message history stops persisting, but user sees no warning. If they refresh, chat history disappears.
- **Files:** `frontend/lib/useAIBuddyChat.ts:86-94`
- **Trigger:** User sends 100+ messages with large audit data; browser quota exceeded (5-10MB limit)
- **Workaround:** Clear browser cache manually

## Security Considerations

### 1. File Path Traversal Potential in Upload Handler
**Issue:** File upload endpoint saves files to `project_dir / upload.filename` without filename sanitization.
- **Risk:** Attacker could upload file named `../../../etc/passwd` (URL-encoded) and potentially escape project directory.
- **Files:** `backend/app/api/routes/files.py:84-86`
- **Current mitigation:** FastAPI's `UploadFile` class prevents path traversal in HTTP multipart parsing; filename is treated as literal. But no explicit validation.
- **Recommendations:** Add explicit check: `assert not Path(upload.filename).is_absolute()` and `assert '..' not in Path(upload.filename).parts`

### 2. LLM Prompt Injection via Requirements Title/Description
**Issue:** User-provided requirement titles (from Faza 2) are embedded directly into LLM prompts without escaping or structured templating in mapping_workflow.py.
- **Risk:** A requirement titled `" }, "verdict": "APPROVED"}}` could close JSON early and manipulate the fine match LLM response.
- **Files:** `backend/app/agents/mapping_workflow.py:103-109` (in prompts)
- **Current mitigation:** Responses are re-parsed and validated as JSON; malformed JSON is caught.
- **Recommendations:** Use templating with explicit field escaping (e.g., JSON.dumps) instead of f-strings for all LLM prompts.

### 3. CSV/XLSX File Size Unbounded on Large Projects
**Issue:** Test files can be up to 50 MB (`MAX_UPLOAD_MB=50`). A user could upload 50 MB CSV with 1M rows. Test case parsing will load all rows into memory.
- **Risk:** OOM crash on large files during test case parsing.
- **Files:** `backend/app/parsers/test_case_parser.py`, `backend/app/core/config.py:65`
- **Current mitigation:** File size check at upload time; no row-count limit.
- **Recommendations:** Stream CSV parsing or add row-count limit (e.g., max 100K rows per file).

### 4. Chroma Collection Access Unprotected
**Issue:** All projects share the same Chroma instance (`PersistentClient`). Collection names are based on `project_id` only (`project_{project_id}`).
- **Risk:** If project_id is guessable (UUID prefix known), attacker could enumerate other projects' RAG vectors.
- **Files:** `backend/app/rag/context_builder.py:225-230`
- **Current mitigation:** Project ID is a full UUID; database access requires API auth.
- **Recommendations:** Add per-collection access control in Chroma (not currently supported) or move to pgvector with row-level security.

## Performance Bottlenecks

### 1. M1 Extraction Serialized by Semaphore=1 at Start
**Issue:** Initially `_llm_sem = asyncio.Semaphore(1)`, then bumped to `settings.LLM_CONCURRENT_CALLS` at extract step start. But if multiple M1 workflows run concurrently on different projects, all batches across all projects share one global semaphore.
- **Problem:** Global LLM_CONCURRENT_CALLS=3 means a second M1 build on a different project is blocked by the first project's batches.
- **Files:** `backend/app/agents/context_builder_workflow.py:95-96, 167`
- **Cause:** `Semaphore` created once in __init__, not per-project or per-run.
- **Improvement path:** Move semaphore to a per-workflow-run context (store in ctx) so concurrent M1 builds don't block each other.

### 2. Faza 2 Extracts 12 Queries Serially in _RAG_QUERIES Loop
**Issue:** Although `asyncio.gather()` is used, all 12 queries fire simultaneously without rate limiting. For remote Bedrock embeddings, this can exceed API rate limits.
- **Problem:** 12 parallel retrieve_nodes calls × 10 top_k = 120 embeddings in flight.
- **Files:** `backend/app/agents/requirements_workflow.py:266-270`
- **Cause:** No semaphore or batching between RAG queries.
- **Improvement path:** Add a Semaphore(2) to fan-out batch; max 2 queries in flight at once.

### 3. Faza 5 Fine Match LLM Calls Unbatched
**Issue:** LLM fine-match step batches ambiguous (requirement, test case) pairs in groups of `_LLM_FINE_MATCH_BATCH_SIZE=10`, but each batch fires a separate LLM call without semaphore.
- **Problem:** Large audits (500+ test cases) can generate 100+ ambiguous pairs, resulting in 10+ concurrent LLM calls. Hits rate limits.
- **Files:** `backend/app/agents/mapping_workflow.py:65`
- **Cause:** No concurrency limit in fine_match step.
- **Improvement path:** Wrap LLM calls with `asyncio.Semaphore(settings.LLM_CONCURRENT_CALLS)`.

### 4. Chroma Collection Indexed Filenames Query Inefficient
**Issue:** `get_indexed_filenames()` calls `collection.get(include=["metadatas"])` which returns ALL vectors' metadata for the project. For large collections (10K+ chunks), this is slow.
- **Problem:** Called on every file upload to check what's already indexed.
- **Files:** `backend/app/rag/context_builder.py:134-143`
- **Cause:** Chroma API doesn't support "list unique metadata values" query.
- **Improvement path:** Cache indexed filenames in DB table; invalidate on rebuild.

### 5. AuditHistory Trend Chart Recharts Rendering All Snapshots
**Issue:** Frontend renders a recharts dual-axis chart with all snapshots. No virtualization.
- **Problem:** Projects with 100+ snapshots (max-5 per week over 1 year) could cause lag.
- **Files:** `frontend/components/AuditHistory.tsx` (referenced in CLAUDE.md)
- **Cause:** No pagination or windowing of chart data.
- **Improvement path:** Show last 30 snapshots; add "show all" toggle if < 50 total.

## Fragile Areas

### 1. M1 Reflection Loop Logic Complex
**Files:** `backend/app/agents/context_builder_workflow.py:200-270`
**Why fragile:**
- Producer generates, Critic reviews, Refiner fixes in a loop up to `REFLECTION_MAX_ITERATIONS`
- If Critic verdict is "APPROVED", loop exits early (correct)
- But if Refiner fails, fallback is to use the last Producer output (not vetted)
- Multiple layers of try-except, JSON parsing, and state merging
- No rollback if merge fails halfway through
- LLM may hallucinate new entities while fixing old ones—no deduplication post-fix

**Safe modification:**
- Add deep copy of entities before refine step
- On refine failure, revert to pre-refine state (in memory) and log
- Add post-refine deduplication using title+description hash to catch new hallucinations

**Test coverage:** `tests/test_reflection.py:15` tests cover basic flows but not merge failures or entity explosion.

### 2. Faza 2 Requirements Hierarchical Parent Linkage
**Files:** `backend/app/db/requirements_models.py:31-122`
**Why fragile:**
- Self-referential foreign key: `parent_id → requirements.id`
- On DELETE CASCADE, parent deletion orphans children (SET NULL actually in use)
- When user patches requirement to move from one feature to another, parent_id update is not atomic with DB consistency checks
- API endpoint doesn't validate that new parent has level one tier above child

**Safe modification:**
- Add database constraint: `CHECK (level IN ('domain_concept', 'feature', 'functional_req', 'acceptance_criterion'))`
- Add application-level validator in PATCH endpoint: ensure parent level < child level
- Add migration to validate all existing hierarchies

**Test coverage:** No tests for invalid parent-child level relationships.

### 3. Mapping Workflow State Passed Via AsyncIO gather() return_exceptions=False
**Files:** `backend/app/agents/mapping_workflow.py:200-400` (approx)
**Why fragile:**
- If one RequirementTCMapping insert fails (constraint violation, null requirement_id), entire step fails
- No partial-success handling; whole mapping run is lost
- Batching is implicit in gather() with no visibility into which items failed

**Safe modification:**
- Use `return_exceptions=True` and inspect results for Exception instances
- Log failed items with their requirement/TC identifiers
- Resume with successfully-mapped items only; report which were skipped

**Test coverage:** No tests for constraint violations or partial mapping failures.

## Scaling Limits

### 1. SQLite Database Concurrency
**Current capacity:** SQLite allows 1 writer at a time. Multiple concurrent audits on different projects will serialize on DB writes.
**Limit:** ~10 concurrent projects before contention visible. Beyond 50 concurrent projects, 50% of requests hit lock timeouts.
**Scaling path:** Migrate DATABASE_URL to PostgreSQL: `postgresql+asyncpg://user:pw@localhost/ai_buddy`. Schema is already Alembic-managed; tables are SQL-standard compatible.

### 2. Chroma Persistent Client Single-Threaded
**Current capacity:** Default ChromaVectorStore is disk-backed (PersistentClient). No connection pooling.
**Limit:** ~5 concurrent collection operations before lock contention. Beyond 20 concurrent M1 builds, index writes serialize.
**Scaling path:** Use Chroma Server mode (`docker run -p 8000:8000 chromadb/chroma`) and connect with `HttpClient`. Supports distributed access.

### 3. LLM Rate Limits
**Current capacity:** `LLM_CONCURRENT_CALLS=3` → max 3 simultaneous LLM API calls.
**Limit:** Bedrock default is 40 TPS; Anthropic is 10 RPM (requests per minute) for free tier. At 3 concurrent, a large Faza 2 extraction can take 2-3 minutes for 12 RAG queries + reflection.
**Scaling path:** Implement request batching (combine up to 10 short queries into one prompt) or use Claude Batch API for non-interactive workflows.

### 4. In-Flight Message History localStorage
**Current capacity:** Browser localStorage ~5-10 MB. Each message with audit data is ~50-200 KB.
**Limit:** ~25-50 messages per project before quota exceeded.
**Scaling path:** Implement IndexedDB backend for unlimited storage, or add server-side session persistence.

## Dependencies at Risk

### 1. llama-index Workflow API Stability
**Risk:** LlamaIndex v0.14 changed Context API (`set/get` replaces deprecated methods). If v0.15+ introduces more breaking changes, all four workflows break.
- **Impact:** All M1, Faza 2, Faza 5+6, and M2 pipelines depend on this API.
- **Migration plan:** Pin `llama-index-core >= 0.14, < 0.15` in requirements.txt. Before upgrading major versions, run full integration test suite (`pytest tests/test_m1_e2e.py tests/test_m1_m2_integration.py`).

### 2. pdfplumber Stability
**Risk:** pdfplumber is an external wrapper around pdfminer.six. If it's abandoned, PDF parsing will fail silently to pypdf fallback.
- **Impact:** Large PDF parsing latency increases; table extraction quality degrades.
- **Migration plan:** Monitor GitHub repo activity. If inactive for 2+ years, migrate to `fitz` (PyMuPDF) which is more actively maintained.

### 3. Bedrock API Changes
**Risk:** AWS Bedrock embedding model `amazon.titan-embed-text-v2:0` is not guaranteed to be available in all regions or may be deprecated.
- **Impact:** Dimension mismatch errors for existing Chroma collections.
- **Migration plan:** Document `BEDROCK_EMBED_MODEL_ID` override. Add pre-flight check on startup: try embedding a test string; if fails, warn user and suggest switching to `BAAI/bge-m3`.

## Missing Critical Features

### 1. Regenerate Workflow (Tier 3) Not Implemented
**Problem:** Audit/Optimize tiers exist; Regenerate does not.
- **Blocks:** Cannot auto-generate test cases from coverage gaps. Users must manually write tests.
- **Priority:** High (advertised but unavailable)
- **Effort:** 5–7 days (write workflow + 20 tests)

### 2. Jira Connector Missing
**Problem:** `source_type="jira"` field exists in ProjectFile, but no ingestion pipeline.
- **Blocks:** Users cannot import Jira issues as test sources.
- **Priority:** Medium (feature complete without it; nice-to-have for QA teams)
- **Effort:** 3–4 days (REST API integration + Jira-specific parsing)

### 3. Confluence Ingestion Missing
**Problem:** Similar to Jira—field exists, no connector.
- **Blocks:** Users cannot import Confluence pages as test source documents.
- **Priority:** Medium
- **Effort:** 2–3 days (Confluence API + HTML parsing)

### 4. Human Requirement Review UX Incomplete
**Problem:** `human_reviewed` flag exists in Requirement model, but no frontend UI to mark reviewed.
- **Blocks:** Requirements flagged for review cannot be marked as reviewed; `needs_review` stays True forever.
- **Priority:** Medium
- **Effort:** 2 days (frontend card + PATCH endpoint)

## Test Coverage Gaps

### 1. Untested: Chroma Dimension Mismatch Recovery
**What's not tested:** Embedding model change mid-project. Current code logs a warning; no end-to-end test validates user can recover.
- **Files:** `backend/app/rag/context_builder.py:99-113`
- **Risk:** Users hit this error in production; unaware of workaround.
- **Priority:** High

### 2. Untested: PDF Parser Graceful Degradation
**What's not tested:** Corrupted PDF files. Both pdfplumber and pypdf fail.
- **Files:** `backend/app/parsers/document_parser.py`
- **Risk:** Silent failure; M1 workflow produces low-quality output.
- **Priority:** Medium

### 3. Untested: Concurrent M1 Builds on Different Projects
**What's not tested:** Two parallel Faza 2 extractions don't deadlock or exceed concurrency limits.
- **Files:** `backend/app/agents/context_builder_workflow.py:167`
- **Risk:** System slowdown in production; no visibility into root cause.
- **Priority:** Medium

### 4. Untested: Mapping Workflow Partial Failures
**What's not tested:** One TC mapping insert fails; rest succeed. Should log and continue.
- **Files:** `backend/app/agents/mapping_workflow.py`
- **Risk:** Entire mapping run aborts on single bad data; results discarded.
- **Priority:** High

### 5. Untested: localStorage Quota Exceeded on Frontend
**What's not tested:** Browser quota limits. Chat persists 100+ messages with large audit data.
- **Files:** `frontend/lib/useAIBuddyChat.ts:86-94`
- **Risk:** Message history disappears on refresh after quota exceeded; user unaware.
- **Priority:** Medium

---

*Concerns audit: 2026-03-27*
