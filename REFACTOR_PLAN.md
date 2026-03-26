# Refactoring Review Plan

Run these prompts one at a time. Each is self-contained — paste it directly.
Complete each before moving to the next; fixes in earlier modules unblock later ones.

---

## Pass 0 — Cross-Cutting Duplicates (start here)

```
Perform a cross-cutting duplication audit on the ai-buddy backend.

Find every case where substantially the same logic appears in more than one file.
For each duplicate, identify: what files contain it, how divergent the copies are,
and what the right extraction point would be.

Focus on these known suspects:

1. `_strip_fences()` / JSON fence removal — appears in at least:
   - backend/app/agents/context_builder_workflow.py
   - backend/app/agents/requirements_workflow.py
   Check if audit_workflow.py and mapping_workflow.py also have ad-hoc versions.

2. `_stream_with_keepalive()` / SSE keepalive pattern — appears in at least:
   - backend/app/api/routes/context.py
   - backend/app/api/routes/requirements.py
   - backend/app/api/routes/mapping.py
   Are they identical? Does chat.py have its own SSE helpers?

3. File parsing helpers (`_parse_file`, `_parse_spreadsheet`, `_parse_json`,
   `_parse_gherkin`) — appears in at least:
   - backend/app/agents/audit_workflow.py
   - backend/app/agents/mapping_workflow.py
   How much do the two copies diverge? What would a shared parser module look like?

4. `_sse()` event formatter — in chat.py. Is it also inlined elsewhere?

5. JSON recovery helpers (`_recover_truncated_array`, etc.) — any duplication?

For each duplicate: read both copies in full, diff them mentally, and propose a
concrete extraction: file path, function signature, and which call sites change.
Do NOT make changes yet — output a findings report only.
```

---

## Pass 1 — `context_builder_workflow.py`

```
Perform a refactoring review of:
  backend/app/agents/context_builder_workflow.py  (~859 lines)

Read the entire file first. Then analyse:

**Structure**
- List every method and its line count. Flag any method over 40 lines.
- Does the class have too many responsibilities? Could extraction helpers live
  outside the class (module-level functions)?
- Is `self._llm_sem` the right place to hold concurrency state, or does it bleed
  workflow-run state into the reusable object?

**Reflection loop**
- The producer-critic-refine loop also appears in requirements_workflow.py.
  Is there enough shared logic to extract a generic `ReflectionLoop` helper?
  Or are the two loops too different (different issue shapes, different refine logic)?

**JSON recovery**
- `_strip_fences()` and `_recover_truncated_array()` are utility functions.
  Should they live in a shared `backend/app/utils/json_utils.py`?
- Is `_recover_truncated_array` actually used after the two-phase glossary rewrite,
  or is it now dead code?

**Two-phase glossary extraction**
- `_extract_glossary_batch` → `_enumerate_term_names` → `_define_term_group`.
  Is the flow easy to follow? Are the method names accurate?
- `TERMS_PER_DEFINITION_GROUP = 15` is a class constant. Should it be in settings?

**Naming consistency**
- Are the step method names (`parse`, `embed`, `extract`, `review`, `assemble`)
  consistently named vs. the SSE event stage strings they emit?
- `_llm_call()` is a generic wrapper — is the name specific enough?

**Error handling**
- Where do exceptions surface? Are they caught too broadly or too narrowly?
- What happens if `_enumerate_term_names` returns an empty list?

**Append vs. rebuild mode**
- Is the mode=append / mode=rebuild branching clean, or is it scattered?

Output: a prioritised list of specific changes (not general advice).
For each: what to change, why, and estimated risk (low/medium/high).
```

---

## Pass 2 — `requirements_workflow.py`

```
Perform a refactoring review of:
  backend/app/agents/requirements_workflow.py  (~1054 lines)
  — the largest file in the backend.

Read the entire file first. Then analyse:

**Reflection loop vs. M1**
- Compare the reflection loop here to the one in context_builder_workflow.py.
  What is structurally identical? What genuinely differs?
- Could a shared `run_reflection_loop(extract_fn, critic_fn, refine_fn, max_iter)`
  coroutine reduce both files without sacrificing flexibility?

**RAG query fan-out**
- How many separate RAG queries does the extraction step make?
  Are they all necessary, or is there overlap?
- Is the combined_context assembly readable? Could it be a named method?

**Rule-based post-processing**
- `_apply_validation` / rule-based pass runs after every reflection cycle.
  Is it clearly separated from LLM logic? Is it testable in isolation?

**Prompt management**
- Are prompts inlined as f-strings, or extracted to constants/templates?
  Long inline prompts hurt readability and make A/B testing hard.
- Are prompt strings duplicated or varied between extract / refine calls?

**Persist step**
- `_persist_requirements()` and `_persist_gaps()` — are these in the workflow
  or delegated to a DB helper? Should they be?

**Method size**
- List every method over 40 lines. For each, identify the natural split point.

**_strip_fences duplication**
- This file has its own `_strip_fences`. After Pass 0, this should be the
  shared version. Confirm it was removed and replaced with the import.

Output: prioritised list of specific changes with risk levels.
```

---

## Pass 3 — `audit_workflow.py` + `optimize_workflow.py`

```
Perform a refactoring review of:
  backend/app/agents/audit_workflow.py   (~600 lines)
  backend/app/agents/optimize_workflow.py (~312 lines)

Read both files in full. Then analyse:

**File parsing duplication (critical)**
- audit_workflow.py has `_parse_file`, `_parse_spreadsheet`, `_parse_json`,
  `_parse_gherkin`. So does mapping_workflow.py.
- After Pass 0, a shared parser module should exist. Confirm audit_workflow.py
  can safely adopt it, or flag any divergence that prevents direct substitution.

**Duplicate detection algorithm**
- `_find_duplicate_candidates` + `_judge_candidates_with_llm`: is the cosine
  similarity threshold (0.85? check actual value) well-named? Is the two-step
  approach (fast filter then LLM judge) clear from the code?
- Is there a risk of O(n²) performance on large test suites?

**Requirement coverage**
- `_extract_requirements` + `_requirements_in_tests` implement the legacy
  coverage path. After audit_workflow_integration.py added the three-tier chain,
  is the legacy path still clearly the fallback, or has the logic become tangled?
- Is `_extract_requirements` dead code when Faza 2 data is present?

**JSON parse helpers**
- `_parse_json_object` and `_parse_json_array` — are these the same as
  `_strip_fences` / `_recover_truncated_array` from other agents, or different?
  Flag any third variant of the same pattern.

**optimize_workflow.py**
- Is it using the same file parsing helpers as audit_workflow? If not, why not?
- Are there any methods that belong in audit_workflow but were copied here?

**Method cohesion**
- The `analyse` step appears to be very long. What are its natural sub-steps?
  Would named private methods make the intent clearer?

Output: prioritised list of specific changes with risk levels.
```

---

## Pass 4 — `mapping_workflow.py`

```
Perform a refactoring review of:
  backend/app/agents/mapping_workflow.py  (~891 lines)

Read the entire file first. Then analyse:

**Three-level matching pipeline**
- Pattern match → embedding similarity → LLM fine-match.
  Is each level a self-contained method, or do they share state through the class?
- Are the confidence thresholds (0.65, 0.78, 0.95) named constants or magic numbers?
- What happens when the embedding model is unavailable?

**Scoring model**
- `_compute_score()` implements: base_coverage + depth_coverage + quality_weight
  + confidence_penalty + crossref_bonus.
  Is each component independently testable? Are the weight caps (40, 30, 20, -10, 10)
  named constants or hardcoded?
- Is there a risk of the formula drifting out of sync with the CLAUDE.md docs?

**File parsing (duplication)**
- After Pass 0 established the shared parser module, confirm all `_parse_*`
  methods here have been replaced with calls to the shared module.
  Flag any parse logic unique to mapping that cannot be shared.

**Auto-loading files**
- `_auto_load_files()` queries the DB for project files. Is this logic the same
  as or divergent from the file selection logic in files.py / chat.py?
  If divergent, which is authoritative?

**Embedding management**
- `_embed_items()` is called for both requirements and test cases.
  Is there a risk of embedding the same content twice across workflow runs?
  Is there a caching layer, or is it re-computed every time?

**5-step workflow overhead**
- LoadData → CoarseMatch → FineMatch → Score → Persist: are events passed between
  steps lean (IDs + metadata) or do they carry full data payloads? Large payloads
  in ctx.store can cause memory issues.

Output: prioritised list of specific changes with risk levels.
```

---

## Pass 5 — `audit_workflow_integration.py`

```
Perform a refactoring review of:
  backend/app/agents/audit_workflow_integration.py  (~248 lines)

Read the entire file first. Then analyse:

**Three-tier priority chain**
- Faza 5+6 scores → Faza 2 requirements → legacy extraction.
  Is the priority clearly expressed? Could a guard-clause pattern make the
  branching order more explicit?

**Coupling**
- This module touches: requirements_models.py, audit_workflow.py (legacy path),
  and the mapping DB tables. Is it the right abstraction boundary, or is it
  doing DB access that should live in a repository layer?

**`compute_registry_coverage()` complexity**
- Is this one function doing too much? (Load data, compute coverage, reconcile
  with snapshot, return result.) Would splitting into named phases help?

**Test coverage gap**
- Does a dedicated test file exist for this module, or is it only tested
  indirectly through test_m1_m2_integration.py?
  Flag any paths through the priority chain that have no test coverage.

**Dead code**
- If Faza 5+6 scores are always present for recent projects, is the legacy
  extraction path in the fallback still reachable in practice?

Output: prioritised list of specific changes with risk levels.
```

---

## Pass 6 — API Routes: `context.py` + `chat.py`

```
Perform a refactoring review of:
  backend/app/api/routes/context.py  (~404 lines)
  backend/app/api/routes/chat.py     (~310 lines)

Read both files in full. Then analyse:

**`_run_workflow()` in chat.py**
- This function is ~165 lines. List every distinct responsibility it has.
  Which belong in the route handler, which in the workflow, which in a helper?
- The `wyjaśnij termin:` prefix detection lives here. Should it be a dedicated
  handler or at least a named function?
- Auto-file selection logic: is the SQL query here the same logic as in
  audit-selection endpoint in files.py? If yes, flag as duplication.

**`_context_store` cache in context.py**
- Module-level dict as a write-through cache. Is this approach documented?
  What happens on multi-worker deployments? Is there a comment explaining why
  this exists vs. just querying the DB each time?

**`_merge_mind_maps()` + `_merge_glossaries()`**
- Are these pure functions (no side effects, testable)?
  Do they have unit tests? If not, flag as a gap.

**`_stream_with_keepalive()` duplication**
- After Pass 0, a shared keepalive utility should exist. Confirm both files
  use it, or flag any remaining inline version.

**SSE formatting**
- `_sse()` in chat.py — is the same formatter used everywhere, or are there
  inline `f"data: {json.dumps(...)}\n\n"` strings scattered around?

**`save_snapshot()` placement**
- This function lives in chat.py but it's a DB operation with business logic
  (diff computation, max-5 pruning). Should it live in a service/repository
  layer instead?

**Error responses**
- Are HTTP error shapes consistent across both files?
  (HTTPException vs. inline SSE error events vs. returning {"error": "..."})

Output: prioritised list of specific changes with risk levels.
```

---

## Pass 7 — API Routes: `files.py` + `projects.py` + `snapshots.py` + `requirements.py` + `mapping.py`

```
Perform a refactoring review of the remaining API route files:
  backend/app/api/routes/files.py          (~214 lines)
  backend/app/api/routes/projects.py       (~132 lines)
  backend/app/api/routes/snapshots.py      (~115 lines)
  backend/app/api/routes/requirements.py   (~450 lines)
  backend/app/api/routes/mapping.py        (~444 lines)

Read all five files. Then analyse:

**`_stream_with_keepalive()` in requirements.py and mapping.py**
- After Pass 0, confirm the shared version is used. Flag any remainder.

**`_persist_requirements()` / `_persist_gaps()` in requirements.py**
- Are these DB helpers that belong in the route file, or should they be
  in a service layer? How long are they?

**Sorting logic in files.py**
- The audit-selection sort (new files first, used files last) — is the
  sort logic readable? Is it duplicated in chat.py's auto-load query?

**Response shape consistency**
- Do all routes return consistent shapes for errors and paginated lists?
  Are there routes returning bare lists where an object with metadata
  would be more future-proof?

**`_req_to_dict()` in requirements.py**
- Is this a serialiser that should be a Pydantic schema / SQLAlchemy
  `as_dict()` method, not an ad-hoc function in a route file?

**mapping.py coverage endpoint**
- `GET /coverage` accepts sort parameters. Is the sort applied in Python
  or in SQL? For large projects, Python-side sort is a scalability risk.

**Dependency injection**
- Are DB sessions obtained consistently via `Depends(get_db)` in all routes,
  or are there any that open sessions directly?

Output: prioritised list of specific changes with risk levels.
```

---

## Pass 8 — `context_builder.py` (RAG) + `document_parser.py`

```
Perform a refactoring review of:
  backend/app/rag/context_builder.py       (~197 lines)
  backend/app/parsers/document_parser.py   (~118 lines)

Read both files. Then analyse:

**`_build_embed_model()` factory**
- Is the Bedrock vs. HuggingFace branching readable?
  Is the model name override (`EMBED_MODEL_NAME`) clearly documented in code?
  Should this be in `core/llm.py` alongside `get_llm()` for consistency?

**`build()` vs. `build_with_sources()`**
- Two methods that overlap significantly. Is `build()` still used anywhere,
  or is it dead code since `build_with_sources()` replaced it?

**`is_indexed()` semantics**
- This returns True when Chroma count > 0. But it's called by the status
  endpoint as a proxy for M1 completion, when `context_built_at` is the
  real gate. Is the function name accurate? Should it be `has_vectors()`?

**DocumentParser**
- `parse()` returns a single dict. But the method accepts a path and might
  need to handle multiple files in the future. Is the interface future-proof?
- DOCX and PDF parsing are in the same method. Could they be `_parse_docx()`
  and `_parse_pdf()` sub-methods for testability?
- `_table_to_text()` — is this the right level of abstraction, or should
  tables be returned structured and left to the caller to stringify?

**Error handling in parsers**
- What happens if pdfplumber fails and pypdf also fails?
  Is there a clear error propagation path or silent empty returns?

Output: prioritised list of specific changes with risk levels.
```

---

## Pass 9 — DB Layer: `models.py` + `requirements_models.py` + `engine.py`

```
Perform a refactoring review of:
  backend/app/db/models.py                (~131 lines)
  backend/app/db/requirements_models.py   (~227 lines)
  backend/app/db/engine.py                (~54 lines)

Read all three files. Then analyse:

**Two model files**
- `models.py` has Project, ProjectFile, AuditSnapshot.
  `requirements_models.py` has Requirement, RequirementTCMapping, CoverageScore.
  Both share the same `Base`. Is the split by feature-area the right boundary?
  Are there import order issues (requirements_models imports Base from models)?

**JSON fields as Text columns**
- Project.mind_map, Project.glossary, Project.context_stats, Project.context_files,
  AuditSnapshot.files_used, etc. are all `Text` columns storing JSON strings.
  Is `json.dumps` / `json.loads` scattered across route files and workflows,
  or is it handled at the model layer (SQLAlchemy TypeDecorator / mapped column)?
  Flag every call site that manually serialises/deserialises these fields.

**CoverageScore scoring components**
- base_coverage, depth_coverage, quality_weight, confidence_penalty, crossref_bonus
  are Float columns with implied ranges (0-40, 0-30, etc.).
  Are the ranges enforced anywhere (check constraints, validators)?

**Cascade deletes**
- Are all FK relationships configured with `ondelete="CASCADE"` in the DB schema
  and `cascade="all, delete-orphan"` in the ORM where needed?
  A project delete should cascade to files → snapshots → requirements → mappings → scores.
  Verify the full chain.

**`init_db()` vs. Alembic**
- `init_db()` calls `create_all` — is this still referenced anywhere other than
  conftest.py / tests? Could it cause silent schema drift if called in production?

Output: prioritised list of specific changes with risk levels.
```

---

## Pass 10 — Frontend: `UtilityPanel.tsx`

```
Perform a refactoring review of:
  frontend/components/UtilityPanel.tsx  (~955 lines)
  — the largest frontend file.

Read the entire file first. Then analyse:

**Component decomposition**
- List every named inner component / helper function defined inside this file.
- The panel renders fundamentally different content for three modes (context,
  requirements, audit). Should each mode be its own component file?
  Propose a file breakdown: what goes in ContextModePanel, RequirementsModePanel,
  AuditModePanel, and what stays in UtilityPanel as the shell.

**Exported types**
- `PanelFile` and `AuditSnapshot` are exported from UtilityPanel.tsx.
  Should they live in a dedicated types file (e.g. `lib/types.ts`) so other
  components can import them without coupling to UtilityPanel?

**`heatmapEmoji()` + `CovBadge()` + `DiffBadge()`**
- Coverage badge colours and emoji logic is also present in AuditHistory.tsx.
  Is it duplicated? Should it be extracted to a shared `lib/coverage.ts` utility?

**`PanelCard()` helper**
- Is this a local component that deserves its own file, or is it small enough
  to stay inline?

**Props surface area**
- How many props does UtilityPanel accept? List them.
  Are any props passed straight through to a child without being used by the
  panel itself? (prop drilling smell)

**Heatmap rendering**
- The heatmap table is rendered inline in UtilityPanel. How much logic does it
  contain? Should it be `<HeatmapTable>` from a separate component?

**Test coverage**
- UtilityPanel.test.tsx has 35 tests. After splitting, do the tests need
  restructuring? Flag any tests that would break from a structural split.

Output: concrete file-by-file split proposal + prioritised change list with risk levels.
```

---

## Pass 11 — Frontend: `ProjectPage.tsx`

```
Perform a refactoring review of:
  frontend/app/project/[projectId]/page.tsx  (~472 lines)

Read the entire file first. Then analyse:

**Inline hook definitions**
- Are `useSnapshots()` and `usePanelFiles()` defined inline in this file?
  If yes: do they belong in lib/ alongside the other hooks? What is the
  argument for keeping them inline vs. extracting them?

**Hook wiring complexity**
- List every hook called at the top of this component.
  Are any hook outputs passed to multiple children? Is the data flow readable?
- Is there a pattern of "fetch in page, pass down as props" that could be
  simplified with context or co-location?

**Mode switching**
- The `?mode=` search param drives three fundamentally different UIs.
  Is the mode branching clean (early returns / conditional renders),
  or is it scattered through the JSX?

**Render function size**
- How many JSX elements does the return statement contain?
  Would named sub-renders (e.g. `renderChatColumn()`, `renderArtifactPanel()`)
  reduce visual noise, or add indirection without benefit?

**File selection state**
- `usePanelFiles` / `selectedFilePaths` state — is this the same file
  selection state that AuditFileSelector manages, or is there a second copy?
  Flag any state that is duplicated between the page and a child component.

**Error states**
- Are loading/error states from all 8+ hooks handled consistently?
  Is there a risk of rendering partial data when some hooks are loading
  and others have resolved?

Output: prioritised list of specific changes with risk levels.
```

---

## Pass 12 — Frontend: `MindMapModal.tsx` + `MindMap.tsx`

```
Perform a refactoring review of:
  frontend/components/MindMapModal.tsx  (~649 lines)
  frontend/components/MindMap.tsx       (~205 lines)

Read both files. Then analyse:

**`layoutModalNodes()` extraction**
- This function is exported from MindMapModal.tsx and tested in MindMapModal.test.tsx.
  It's a pure layout algorithm — should it live in `lib/mindMapLayout.ts` instead
  of inside a component file?

**Duplication between MindMap.tsx and MindMapModal.tsx**
- Both files do dagre layout, SVG node rendering, cubic bezier edges, pan+zoom.
  How much code is duplicated? Is MindMap.tsx (inline panel) using a simplified
  version, or is it diverged in incompatible ways?
  What is the cost/benefit of a shared `<MindMapCanvas>` base component?

**Cluster collapse logic**
- The depth-based visibility (depth≥3 hidden at zoom<0.55, depth≥2 at zoom<0.30)
  is complex. Is it a pure function (testable without rendering), or is it
  tangled with React state?

**`getCluster()` cycle detection**
- The visited Set prevents infinite loops on cyclic LLM-generated edges.
  Is this the only place cycle detection is needed, or does the dagre layout
  also need protection?

**Pan + zoom implementation**
- Is the wheel event handler correctly using `{ passive: false }` with an
  explicit `addEventListener`, or does it rely on React's synthetic events
  (which are passive by default in React 17+)?
  Verify this is correctly implemented, not just the comment about it.

**TYPE_COLORS**
- Defined in MindMap.tsx. Also needed in MindMapModal.tsx?
  If so, is it duplicated or imported?

Output: prioritised list of specific changes with risk levels.
```

---

## Pass 13 — Frontend: `useAIBuddyChat.ts` + `useContextBuilder.ts` + `useRequirements.ts`

```
Perform a refactoring review of:
  frontend/lib/useAIBuddyChat.ts      (~297 lines)
  frontend/lib/useContextBuilder.ts   (~191 lines)
  frontend/lib/useRequirements.ts     (~231 lines)

Read all three files. Then analyse:

**SSE loop pattern**
- All three hooks contain an async SSE reader loop (fetch → ReadableStream →
  TextDecoder → line parsing → event dispatch). How much of this is duplicated?
  Would a shared `useSSEStream(url, options)` hook reduce all three,
  or do they diverge enough that extraction adds complexity without clarity?

**`ProjectOperationsContext` dual-write**
- All three hooks dual-write to context (local state + ops?.updateOp).
  Is the dual-write pattern consistent across all three?
  Are there any missing transitions (e.g. a `progress` update that writes local
  state but not context, or vice versa)?

**`useAIBuddyChat.ts` concerns**
- This hook handles: SSE streaming, localStorage serialisation, message formatting,
  snapshot fetching after audit, file attachment state.
  List each concern and whether it should stay or be extracted.
- `formatResult()` fetches the latest snapshot after an audit completes.
  Should this be a separate `useLatestSnapshot()` hook called from the page,
  rather than embedded in the chat hook?

**localStorage coupling**
- Chat history is persisted to localStorage inside the hook. Is the storage
  key stable across project renames? Is there a cleanup path for stale keys?

**Re-entry guards**
- Each hook has `if (isRunning) return` at the start of the trigger function.
  After the dual-write refactor, this guard uses the context-derived value.
  Verify: does the guard correctly prevent re-entry when the user navigates
  away and back (context says running, local state says not running)?

**`useRequirements` auto-fetchAll**
- The `useEffect` that calls `fetchAll()` when `isExtracting` transitions
  true→false. Is the dependency array correct? Could this fire spuriously?

Output: prioritised list of specific changes with risk levels.
```

---

## Pass 14 — Frontend: Remaining Components

```
Perform a refactoring review of the smaller frontend components:
  frontend/components/AuditHistory.tsx      (~457 lines)
  frontend/components/AuditResultCard.tsx   (~370 lines)
  frontend/components/AuditFileSelector.tsx (~202 lines)
  frontend/components/RequirementsView.tsx  (~457 lines)
  frontend/components/MessageList.tsx       (~189 lines)
  frontend/components/TopBar.tsx            (~289 lines)
  frontend/components/ModeInputBox.tsx      (~245 lines)

Read all seven files. For each, identify:

**AuditHistory.tsx**
- The trend chart (recharts) and snapshot row list are both large.
  Would `<TrendChart>` and `<SnapshotRow>` as extracted components help?
- Coverage badge logic: is `CovBadge` duplicated from UtilityPanel.tsx?
  (This is a direct question from Pass 10 — confirm or deny here.)

**AuditResultCard.tsx**
- Who renders this? Is it always in MessageList, or also elsewhere?
- Does it receive a raw API response shape, or a typed interface?
  Are there any `as any` casts or untyped fields?

**RequirementsView.tsx**
- `levelColor()`, `sourceColor()`, `moduleKey()`, `moduleLabel()` are helpers.
  Are any of these shared with the backend's requirement level/source enums?
  Is there a risk of the frontend label diverging from the DB enum values?

**MessageList.tsx**
- `renderAssistantContent` detects `**Powiązane terminy**` by string matching.
  Is this fragile? What happens if the LLM returns slightly different formatting?
  Should the detection be more robust (regex, structured response field)?

**TopBar.tsx**
- At ~289 lines, this is larger than expected for a header.
  What is driving the line count? List everything it renders beyond the basic bar.

**ModeInputBox.tsx**
- Mode pill state: does the component own mode selection state, or does it
  receive it as a controlled prop? If it owns it, is it in sync with the
  `?mode=` URL param in ProjectPage?

Output: prioritised list of specific changes with risk levels, cross-referencing
any duplications confirmed from earlier passes.
```

---

## Pass 15 — Test Hygiene

```
Perform a test quality review across all test files:

Backend:
  backend/tests/test_m1_context.py
  backend/tests/test_m1_e2e.py
  backend/tests/test_m1_m2_integration.py  (1272 lines — the largest)
  backend/tests/test_reflection.py
  backend/tests/test_snapshots.py
  backend/tests/test_rag_ready_isolation.py
  backend/tests/test_requirements.py
  backend/tests/test_requirements_extended.py
  backend/tests/test_mapping.py
  backend/tests/test_mapping_extended.py
  backend/tests/conftest.py

Frontend:
  frontend/tests/useAIBuddyChat.test.ts
  frontend/tests/useRequirements.test.ts
  frontend/tests/useAuditPipeline.test.ts
  frontend/tests/UtilityPanel.test.tsx
  frontend/tests/ProjectPage.test.tsx

For each file, check:

**Mock fidelity**
- Are mock discriminators prompt-based (matching exact substrings) or
  position-based (call count)? Position-based mocks break silently when call
  order changes. Flag every remaining position-based mock.

**Test isolation**
- Do tests share state through module-level variables that could cause
  ordering-dependent failures?
- Does conftest.py correctly isolate Chroma and SQLite between test runs?

**Coverage gaps**
- Which code paths in the agents have no test coverage?
  Focus on: error branches, empty-input edge cases, mode=rebuild vs. mode=append.
- `test_m1_m2_integration.py` at 1272 lines may be doing too much.
  Should it be split by concern?

**`@pytest.mark.asyncio` on sync tests**
- The test runner reported warnings about asyncio marks on non-async functions
  in test_mapping.py and test_requirements.py. List every occurrence.

**Frontend mock depth**
- In ProjectPage.test.tsx, are all 8+ hooks mocked? Are the mocks typed, or
  are there `vi.mock()` calls returning untyped objects?
- Are there any tests that accidentally test mock behaviour rather than
  component behaviour?

Output: prioritised list of test fixes, split into "fix immediately" (could mask bugs)
and "clean up when touching the file" (style/consistency).
```

---

## Pass 16 — Final: Naming + Config Consistency

```
Perform a final naming and configuration consistency pass across the full codebase.

**Backend naming**
- Are workflow step names consistent between: SSE stage strings, event class names,
  method names, and CLAUDE.md documentation?
  (e.g. "assemble" step: is it called assemble/build/finalise in different places?)
- `context_built_at` vs. `rag_ready` vs. `artefacts_ready`: are these terms used
  consistently in code, API responses, and frontend display?
- `source_type` values ("file", "url", "jira", "confluence"): are they string
  literals scattered in code, or defined as an Enum/constant somewhere?

**Frontend naming**
- Mode names: "audit" / "context" / "requirements" — are these used consistently
  in URL params, component props, hook parameters, and UI labels?
- Are TypeScript interface names consistent (PascalCase), and do they match
  their backend Pydantic model names where applicable?

**Settings / constants**
- `TERMS_PER_DEFINITION_GROUP = 15` (workflow constant)
- Cosine similarity thresholds in mapping_workflow
- Score component caps (0-40, 0-30, etc.)
- SSE keepalive interval (5 seconds)
Which of these belong in `config.py` as env-overridable settings, and which
should stay as named constants close to their usage?

**CLAUDE.md accuracy**
- After all passes: does CLAUDE.md still accurately describe the architecture,
  file list, and API shapes? Flag any sections that have drifted from the code.

Output: a final change list, sorted by file, ready to execute as a single cleanup commit.
```
