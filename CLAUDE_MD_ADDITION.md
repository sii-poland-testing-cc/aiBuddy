

---

## Faza 2/5/6: Coverage Analysis Pipeline

### Module Overview (extended)

```
M1: Context Builder  ──→  Faza 2: Requirements Extraction
    (prerequisite)              │
                                ▼
                         Faza 5+6: Mapping & Coverage Scoring
                                │
                                ▼
                         M2: Test Suite Analyzer (audit uses Faza 2/5/6 when available)
```

### Pipeline Flow

```
Faza 2: Requirements Reconstruction
  POST /api/requirements/{project_id}/extract  (SSE)
  Workflow: Extract → Validate → Persist
  Input:  M1 RAG context (multiple queries)
  Output: Hierarchical requirements registry in DB
  Tables: requirements (hierarchical, with confidence + human_reviewed)

Faza 5+6: Semantic Mapping & Coverage Scoring
  POST /api/mapping/{project_id}/run  (SSE)
  Workflow: LoadData → CoarseMatch → FineMatch → Score → Persist
  Input:  requirements (from Faza 2 DB) + test files (uploaded)
  Output: requirement↔TC mappings + multi-dimensional scores
  Tables: requirement_tc_mappings, coverage_scores
```

### Key Files (Faza 2/5/6)

- `backend/app/db/requirements_models.py` — `Requirement`, `RequirementTCMapping`, `CoverageScore` ORM models (share `Base` with `models.py`)
- `backend/app/agents/requirements_workflow.py` — Faza 2: LlamaIndex Workflow (Extract → Validate → Persist)
- `backend/app/agents/mapping_workflow.py` — Faza 5+6: LlamaIndex Workflow (Load → CoarseMatch → FineMatch → Score → Persist)
- `backend/app/agents/audit_workflow_integration.py` — Bridge: audit uses Faza 5+6 scores → Faza 2 registry → legacy extraction (3-tier priority)
- `backend/app/api/routes/requirements.py` — Faza 2 API: SSE extract, CRUD, stats, gaps, human review
- `backend/app/api/routes/mapping.py` — Faza 5+6 API: SSE run, mappings list, coverage scores, summary, heatmap, verify

### DB Schema (v5) — New Tables

#### `requirements`

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
| `source_references` | Text | JSON list of source filenames |
| `taxonomy` | Text | JSON `{module, risk_level, business_domain}` |
| `completeness_score` | Float | 0.0–1.0, nullable |
| `confidence` | Float | 0.0–1.0 — how certain the system is this requirement is real |
| `human_reviewed` | Boolean | default False |
| `needs_review` | Boolean | default False — flagged when confidence < 0.7 |
| `review_reason` | String | nullable |
| `created_at` | DateTime(tz) | |
| `updated_at` | DateTime(tz) | nullable |

#### `requirement_tc_mappings`

| Column | Type | Notes |
|--------|------|-------|
| `id` | String PK | UUID |
| `requirement_id` | String FK | → `requirements.id` ON DELETE CASCADE |
| `project_id` | String FK | → `projects.id` ON DELETE CASCADE |
| `tc_source_file` | String | filename of TC source |
| `tc_identifier` | String | TC ID or title |
| `mapping_confidence` | Float | 0.0–1.0 |
| `mapping_method` | String | `"pattern"` \| `"embedding"` \| `"llm"` \| `"human"` |
| `coverage_aspects` | Text | JSON `["happy_path", "negative", "boundary"]` |
| `human_verified` | Boolean | default False |
| `created_at` | DateTime(tz) | |

#### `coverage_scores`

| Column | Type | Notes |
|--------|------|-------|
| `id` | String PK | UUID |
| `requirement_id` | String FK | → `requirements.id` ON DELETE CASCADE |
| `snapshot_id` | String FK | nullable → `audit_snapshots.id` |
| `project_id` | String FK | → `projects.id` ON DELETE CASCADE |
| `total_score` | Float | 0–100, sum of components below |
| `base_coverage` | Float | 0–40: happy path covered? |
| `depth_coverage` | Float | 0–30: negative, boundary, edge cases |
| `quality_weight` | Float | 0–20: avg mapping confidence × 20 |
| `confidence_penalty` | Float | -10–0: penalty for low-confidence requirement |
| `crossref_bonus` | Float | 0–10: covered by TCs from multiple files |
| `matched_tc_count` | Integer | |
| `coverage_aspects_present` | Text | JSON array |
| `coverage_aspects_missing` | Text | JSON array |
| `created_at` | DateTime(tz) | |

### Audit Integration Priority Chain

When `compute_registry_coverage()` runs during an M2 audit:

1. **Faza 5+6 scores in DB?** → return persisted scores (best quality, no LLM calls)
2. **Faza 2 requirements in DB?** → load requirements, do live matching against TCs
3. **Neither?** → run legacy `_extract_requirements()` (original behavior)

### Matching Algorithm (Faza 5)

Three levels, merged:
- **Level 0 — Pattern**: TC text contains requirement ID literally (e.g. "FR-017"). Confidence: 0.95
- **Level 1 — Embedding**: cosine similarity > 0.58 between requirement and TC embeddings. Confident > 0.78, ambiguous 0.58–0.78
- **Level 2 — LLM**: evaluates ambiguous pairs. Returns COVERS/PARTIAL/NO + coverage_aspects

### Scoring Model (Faza 6)

```
total_score = min(100, base_coverage + depth_coverage + quality_weight + confidence_penalty + crossref_bonus)
```

Color coding: 🟢 80-100 | 🟡 60-79 | 🟠 30-59 | 🔴 0-29

### API Endpoints (Faza 2)

```
POST   /api/requirements/{project_id}/extract    — run Faza 2 pipeline (SSE)
GET    /api/requirements/{project_id}             — hierarchical list
GET    /api/requirements/{project_id}/flat        — flat list
GET    /api/requirements/{project_id}/stats       — summary statistics
GET    /api/requirements/{project_id}/gaps        — identified gaps
PATCH  /api/requirements/{project_id}/{req_id}    — human review update
DELETE /api/requirements/{project_id}             — wipe for re-extract
```

### API Endpoints (Faza 5+6)

```
POST   /api/mapping/{project_id}/run              — run mapping + scoring (SSE)
GET    /api/mapping/{project_id}                   — list all mappings
GET    /api/mapping/{project_id}/coverage          — per-requirement scores (sortable)
GET    /api/mapping/{project_id}/summary           — aggregate stats + distribution
GET    /api/mapping/{project_id}/heatmap           — module-level heatmap
PATCH  /api/mapping/{project_id}/{mapping_id}      — human verify mapping
DELETE /api/mapping/{project_id}                   — wipe mappings + scores
```

### SSE Event Format (same as M1/M2)

```json
{"type": "progress", "data": {"message": "string", "progress": 0.0–1.0, "stage": "extract|validate|persist|load|coarse|fine|score"}}
{"type": "result",   "data": { ... }}
{"type": "error",    "data": {"message": "string"}}
```

### Requirements Workflow Context API

Same pattern as existing workflows:
- `await ctx.store.set("key", value)` / `await ctx.store.get("key")`
- `ctx.write_event_to_stream(ProgressEvent(...))` for SSE
- Returns `StopEvent(result={...})`

### Testing (Faza 2/5/6)

```bash
# After integration, run from backend/
pytest tests/test_requirements.py -v      # Faza 2 tests
pytest tests/test_mapping.py -v           # Faza 5+6 tests
```
