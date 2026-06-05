# SDIE v3.3 — Code Guide

Where to read and edit the semantic component intelligence implementation.

---

## 1. Entry points

| Entry | File | Role |
|-------|------|------|
| CLI | `scripts/run_pipeline.py` | Default: semantic v3.3; `--legacy-geometry` for v2 |
| Orchestrator | `src/sdie/semantic_pipeline.py` | **`run_semantic_pipeline()`** |
| Router | `src/sdie/pipeline.py` | Delegates when `use_semantic_pipeline=True` |
| Atlas CLI | `scripts/build_atlas.py` | Epic 1 — build `data/atlas/component_atlas.json` |
| API | `src/sdie/api/app.py` | FastAPI `POST /drawings/process` |

```python
# Default v3.3 run
config = PipelineConfig(
    structural_layers=("S-BEAM",),
    use_semantic_pipeline=True,
)
result = run_pipeline(dxf_path, output_dir, config)
# result["semantic_building_model"], result["benchmark"]
```

---

## 2. Configuration (`config.py`)

| Field | Purpose |
|-------|---------|
| `use_semantic_pipeline` | Enable v3.3 (default True) |
| `project_id` | INIZIO project tag for atlas/model |
| `atlas_path` | Atlas JSON for classifier lookup |
| `component_confidence_threshold` | Ambiguous if confidence below (default 65%) |
| `enable_deepseek_component_classification` | `--component-llm` |
| `enable_deepseek_refinement` | `--llm` slab bay filter |
| `detection_mode` | `auto`, `semantic`, `beam_grid`, `region`, `beam_frame` |

---

## 3. Entity extraction

**File:** `ingestion/entity_extractor.py`  
**Function:** `extract_drawing_entities(msp, layers=..., bounds_y=...)`

Returns `DrawingEntity` list — primitives for classification.

---

## 4. Component classifier

**Files:** `classification/features.py`, `classification/classifier.py`

```python
classified = classify_entities(entities, atlas=load_atlas())
```

Priority order:
1. Void keywords → Stair/Lift/Shaft Core  
2. THK annotation → Slab tag  
3. Layer hints (`S-BEAM`, `S-COLS`, …)  
4. Geometry (beam line aspect ratio, column compactness)  
5. Atlas sample vote  

---

## 5. Structural graph

**File:** `graph/engine.py`  
**Function:** `build_structural_graph(classified)`

NetworkX graph with edges: `supports`, `frames`, `touches`, `contains`, `adjacent`.

---

## 6. Semantic building model

**File:** `model/building.py`  
**Function:** `build_semantic_model(...)`

Exported to `*_building_model.json` and embedded in `*_results.json` under `semantic_building_model`.

---

## 7. Slab Intelligence Engine

**File:** `detection/slab_intelligence.py`  
**Function:** `detect_slabs_after_classification(...)`

Key logic:
- `_classified_exclusion_geoms()` — buffer cores/walls/columns from classified components  
- Merge with `build_exclusion_catalog()`  
- Delegate to `detect_beam_grid_slabs` + `detect_label_merged_slabs`

**Do not add slab heuristics here without first improving classification** (per FINAL DIRECTIVE).

---

## 8. Confidence scoring

**File:** `confidence/scorer.py`

```python
score_confidence(geometry_score=0.85, topology_score=0.6, graph_score=0.5, deepseek_score=0.0)
```

---

## 9. DeepSeek component classification

**File:** `reasoning/component_classification.py`  
**Function:** `refine_ambiguous_components(...)`

Only updates `component_type`, `confidence`, `evidence` — never quantities.

---

## 10. Benchmark

**File:** `benchmark/metrics.py`  
**Function:** `compute_benchmark_report(totals, ground_truth)`

Auto-loads `data/ground_truth/<stem>.json` when present. Target: 95% accuracy.

---

## 11. Atlas

| File | Role |
|------|------|
| `atlas/schema.py` | `AtlasSample` dataclass |
| `atlas/builder.py` | `build_atlas_samples_from_dxf()` |
| `atlas/store.py` | `load_atlas()`, `save_atlas()` |

---

## 12. Database & API (scaffold)

| Module | Role |
|--------|------|
| `database/models.py` | SQLAlchemy models — Projects, Drawings, Components, AtlasSamples, Quantities |
| `api/app.py` | FastAPI health, process, building model GET |

Run API:
```powershell
$env:PYTHONPATH="src"
uvicorn sdie.api.app:app --reload
```

---

## 13. Tests

| File | Covers |
|------|--------|
| `tests/test_floor_zone.py` | Floor zone cluster |
| `tests/test_v33_classifier.py` | THK→Slab, STAIR→Core, beam line |

```powershell
$env:PYTHONPATH="src"
python -m pytest tests/ -q
```

---

## 14. Where to edit for common tasks

| Task | Edit |
|------|------|
| New component type rules | `classification/features.py`, `classifier.py` |
| Atlas from new tagged DXF | Run `build_atlas.py` |
| Slab exclusion after classification | `detection/slab_intelligence.py` |
| Graph relationships | `graph/engine.py` |
| Benchmark tolerance | `data/ground_truth/*.json` `regression_config` |
| Disable v3.3 temporarily | `--legacy-geometry` |

---

## Read next

- [02_ARCHITECTURE.md](./02_ARCHITECTURE.md)  
- [Prompt_extracted.txt](./Prompt_extracted.txt)  
- [SESSION_PROGRESS.md](./SESSION_PROGRESS.md)
