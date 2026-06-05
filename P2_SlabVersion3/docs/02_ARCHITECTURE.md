# SDIE v3.3 — System Architecture

**Engine:** Structural Drawing Intelligence Engine (SDIE) v3.3  
**Architecture:** Structural Component Intelligence (semantics before geometry)  
**Design authority:** `docs/Prompt_extracted.txt`, `docs/MODEL_DESIGN.md`

---

## 1. Architectural shift (v3.3)

| v2 (geometry-first) | v3.3 (semantics-first) |
|---------------------|------------------------|
| DXF → beam grid → THK merge → quantity | DXF → **classify components** → graph → building model → slab intelligence → quantity |
| Exclusions from hatch/layer heuristics only | Exclusions from **classified** Beam/Column/Wall/Core + geometry |
| DeepSeek optional for slab bay filter | DeepSeek for **component classification** (and optional slab refinement) |
| JSON slab results only | JSON slabs + **`_building_model.json`** + benchmark report |

**Final directive:** Do not improve slab detection in isolation. Build component intelligence first; quantities run only after semantic model generation.

---

## 2. High-level layer model

```text
┌─────────────────────────────────────────────────────────────┐
│  STAGE 12 — Visual validation (overlay SVG/HTML)            │
├─────────────────────────────────────────────────────────────┤
│  STAGE 11 — Benchmark report (95% target vs ground truth)   │
├─────────────────────────────────────────────────────────────┤
│  STAGE 10 — Quantity engine (area, concrete, shuttering)    │
├─────────────────────────────────────────────────────────────┤
│  STAGE 9  — Slab Intelligence (after classification)      │
├─────────────────────────────────────────────────────────────┤
│  STAGE 8  — Semantic Building Model export                │
├─────────────────────────────────────────────────────────────┤
│  STAGE 7  — DeepSeek reasoning (classification only)        │
├─────────────────────────────────────────────────────────────┤
│  STAGE 6  — Structural graph (NetworkX)                     │
├─────────────────────────────────────────────────────────────┤
│  STAGE 5  — Component classifier + confidence scoring       │
├─────────────────────────────────────────────────────────────┤
│  STAGE 4  — Entity extraction + Atlas lookup                  │
├─────────────────────────────────────────────────────────────┤
│  STAGE 3  — Floor zone (cluster mode)                       │
├─────────────────────────────────────────────────────────────┤
│  STAGE 2  — DXF ingestion                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Repository map (`src/sdie/`)

```text
sdie/
├── config.py                    # PipelineConfig v3.3 flags
├── pipeline.py                  # Delegates to semantic_pipeline when enabled
├── semantic_pipeline.py         # v3.3 orchestrator
│
├── ingestion/
│   ├── dxf_reader.py
│   ├── units.py
│   └── entity_extractor.py      # DrawingEntity primitives
│
├── atlas/                       # Epic 1
│   ├── schema.py                # AtlasSample
│   ├── builder.py               # Auto-labelling from tagged DXF
│   └── store.py                 # JSON atlas persistence
│
├── classification/              # Epic 2 + 5
│   ├── types.py                 # ComponentType, ClassifiedComponent
│   ├── features.py              # Beam/column/wall/slab features
│   └── classifier.py            # Rule + atlas classifier
│
├── graph/                       # Epic 3
│   └── engine.py                # NetworkX structural graph
│
├── model/                       # Epic 4
│   └── building.py              # SemanticBuildingModel JSON
│
├── detection/
│   ├── slab_intelligence.py     # Epic 5 — classify first, slab second
│   ├── floor_zone.py, beam_grid.py, slab_by_label.py, exclusions.py, ...
│
├── confidence/                  # Epic 11
│   └── scorer.py
│
├── benchmark/                   # Epic 10
│   └── metrics.py
│
├── reasoning/
│   ├── component_classification.py  # DeepSeek component classifier
│   └── slab_refinement.py           # Optional slab bay filter
│
├── quantity/
│   └── slab.py
│
├── validation/
│   └── overlay.py
│
├── api/                         # Epic 12
│   └── app.py                   # FastAPI endpoints
│
└── database/                    # Epic 13
    └── models.py                # SQLAlchemy (SQLite/PostgreSQL)
```

**CLI:** `scripts/run_pipeline.py` (default semantic) · `scripts/build_atlas.py`  
**API:** `uvicorn sdie.api.app:app`

---

## 4. Component types

| Type | Detection signals |
|------|-------------------|
| Beam | Layer hint (`S-BEAM`, `S_FRAMES`), long slender LINE, beam size tags |
| Column | `S-COLS`, compact closed poly / hatch |
| Shear Wall / Structural Wall | Wall layers, long lines, wall keywords |
| Lift / Stair / Shaft | Void keywords (LIFT, STAIR, SHAFT, CORE) |
| Opening | STR-CUTOUT, SUNK SLAB, void keywords |
| Slab | `*THK` annotation on `A-FLOR-IDEN` |
| Unknown | Low confidence → optional DeepSeek |

---

## 5. Slab Intelligence Engine (Epic 5)

`detection/slab_intelligence.py`:

1. Build exclusion union from **classified** non-slab components (cores, walls, columns, openings).  
2. Merge with geometric exclusion catalog (columns, hatches).  
3. Run beam grid + THK label merge on **remaining** framed regions only.  
4. Export strategy: `semantic_label_merged_bay` or `semantic_beam_grid_bay`.

---

## 6. Confidence framework (Part 11)

```text
final = 0.35×geometry + 0.25×topology + 0.20×graph + 0.20×deepseek
```

Applied per `ClassifiedComponent` in `confidence/scorer.py`.

---

## 7. DeepSeek boundaries

| Allowed | Forbidden |
|---------|-----------|
| Component classification | Area / volume calculation |
| Ambiguity resolution | Quantity estimation |
| Missing annotation reasoning | Inventing geometry |

Slab refinement (`--llm`) remains optional and geometry-guarded.

---

## 8. Outputs

| File | Content |
|------|---------|
| `*_results.json` | Slabs, totals, detection_notes, semantic_building_model, benchmark |
| `*_building_model.json` | Standalone building model export |
| `*_overlay.html` | Visual QA |
| `data/atlas/component_atlas.json` | Atlas samples (built via `build_atlas.py`) |

---

## 9. Configuration (v3.3)

| Field | Default | Purpose |
|-------|---------|---------|
| `use_semantic_pipeline` | `True` | v3.3 flow; `--legacy-geometry` disables |
| `project_id` | `INIZIO` | Atlas / building model |
| `enable_deepseek_component_classification` | `False` | `--component-llm` |
| `component_confidence_threshold` | `65.0` | Below → ambiguous for LLM |
| `atlas_path` | `data/atlas/component_atlas.json` | Classifier training lookup |

---

## Read next

- [01_SIMPLE_OVERVIEW.md](./01_SIMPLE_OVERVIEW.md)  
- [03_PIPELINE_FLOW.md](./03_PIPELINE_FLOW.md)  
- [04_CODE_GUIDE.md](./04_CODE_GUIDE.md)  
- [SESSION_PROGRESS.md](./SESSION_PROGRESS.md)
