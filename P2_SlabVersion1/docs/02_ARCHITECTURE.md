# SDIE — System Architecture

**Engine:** Structural Drawing Intelligence Engine (SDIE) v0.1  
**Scope (Phase 2):** Slab detection and quantity only — beams support boundaries, not beam BOQ.  
**Design authority:** `docs/Prompt_extracted.txt`, `docs/MODEL_DESIGN.md`

---

## 1. Architectural principles

| Principle | Implementation |
|-----------|----------------|
| Raw DXF in | No required slab polylines or manual CAD prep |
| Deterministic quantities | Shapely polygons + arithmetic in `quantity/` |
| AI for ambiguity only | `reasoning/` — classify, never multiply area × thickness |
| Strategy consensus | `auto` tries grid → region → beam frame |
| Explainability | `detection_notes`, `calculation_trace`, overlay, JSON per slab |
| Generic floor isolation | `floor_zone.py` — data-driven, not drawing-specific constants |

---

## 2. High-level layer model

Aligns with Prompt_extracted “Target System Architecture”:

```text
┌─────────────────────────────────────────────────────────────┐
│  STAGE 10 — Visual validation (overlay SVG/HTML)            │
├─────────────────────────────────────────────────────────────┤
│  STAGE 9  — Quantity engine (area, concrete, shuttering)    │
├─────────────────────────────────────────────────────────────┤
│  STAGE 8  — Semantic slab list (SlabCandidate → JSON)     │
├─────────────────────────────────────────────────────────────┤
│  STAGE 6  — AI reasoning (optional DeepSeek refinement)     │
├─────────────────────────────────────────────────────────────┤
│  STAGE 4  — Slab detection (grid / region / frame + merge) │
│  STAGE 5  — Thickness (notes + local THK)                   │
├─────────────────────────────────────────────────────────────┤
│  STAGE 2  — Floor zone + exclusions (non-slab geometry)   │
├─────────────────────────────────────────────────────────────┤
│  STAGE 1  — DXF ingestion (ezdxf → normalized mm model)   │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Repository map (`src/sdie/`)

```text
sdie/
├── config.py                 # PipelineConfig — layers, thresholds, LLM flags
├── pipeline.py               # Orchestrator: run_pipeline()
│
├── ingestion/
│   ├── dxf_reader.py         # load_drawing(), DrawingMeta (units, extents)
│   └── units.py              # cm/mm → m² factor
│
├── detection/
│   ├── floor_zone.py         # FloorZone, resolve_floor_zone() [cluster mode]
│   ├── beam_grid.py          # Strategy B — orthogonal bays between beams
│   ├── slab_by_label.py      # Merge grid cells per *THK label
│   ├── exclusions.py         # Columns, hatches, void keywords
│   ├── region.py             # Strategy A — polygonize closed loops
│   └── beam_frame.py         # Fallback — single expanded bbox
│
├── geometry/
│   └── segments.py           # LINE/LWPOLYLINE → Shapely segments
│
├── thickness/
│   └── parser.py             # THK labels, default note, nearest match
│
├── quantity/
│   └── slab.py               # compute_slab_quantity()
│
├── reasoning/                # Optional — Prompt §6
│   ├── env.py                # DEEPSEEK_API_KEY from .env
│   ├── deepseek_client.py    # chat_json(), model auto/chat/reasoner
│   ├── context.py            # Drawing summary for LLM prompt
│   └── slab_refinement.py    # exclude/merge decisions → filter candidates
│
└── validation/
    └── overlay.py            # SVG + HTML viewer, exclusion styling
```

**CLI:** `scripts/run_pipeline.py` → `run_pipeline()`  
**Regression:** `scripts/compare_to_ground_truth.py`

---

## 4. Core data object: `SlabCandidate`

Defined in `detection/region.py`, used everywhere:

| Field | Meaning |
|-------|---------|
| `slab_id` | e.g. `SLAB-042` |
| `polygon_wkt` | Shapely polygon as WKT (mm coordinates) |
| `area_m2` | Net bay area after exclusions |
| `centroid_cm` | Label / reporting position |
| `strategy` | `beam_grid_bay`, `label_merged_bay`, `label_merged_bay_llm`, … |
| `thickness_mm` | Optional — set from THK label at merge time |

Pipeline exports JSON slabs with thickness source, confidence, and trace.

---

## 5. Floor zone — dual bounds

`FloorZone` (`floor_zone.py`) solves **multi-floor-on-one-sheet**:

| Field | Role |
|-------|------|
| `label_bounds_y` | Wide band — all `*THK` tags for this takeoff (slab **count**) |
| `bounds_y` | Tighter band — beam grid extent with **stack-repeat cap** (slab **area**) |

**Cluster algorithm (default `floor_zone_mode=cluster`):**

1. Cluster label Y positions (adaptive gap).  
2. Score clusters by tag count + beam line density.  
3. Attach small satellite clusters (few stray tags).  
4. Sub-split primary cluster; pick sub-panel with most frame lines.  
5. Cap grid `ymax` below large upper Y-gap (repeated plan copy).

Fallbacks: `frame_structure`, `floor_title`, manual `floor_bounds_y`.

---

## 6. Detection strategies

### Strategy B — Beam grid (primary)

`beam_grid.py`:

- Collect horizontal / vertical beam centerlines from structural layer.  
- Cluster into axes; form rectangular cells.  
- Expand cell slightly (`grid_slab_face_expand_mm`) for clear span between beams.  
- Subtract `ExclusionCatalog`.  
- Skip cells near void annotation centroids (STAIR, LIFT, RAMP, …).

### Label merge

`slab_by_label.py`:

- Assign each grid cell to nearest `*THK` label in `label_bounds_y`.  
- Union cell polygons per label; **sum cell areas** (no double count).  
- One `SlabCandidate` per label → physical slab count tracks tags.

### Strategy A — Region

`region.py` + `geometry/segments.py` — polygonize closed polylines when grid is inappropriate.

### Fallback — Beam frame

`beam_frame.py` — one slab from frame bounding box.

### Auto selection (`pipeline.py`)

```text
if frame lines ≥ thresholds → beam grid path
elif region viable         → region
else                       → beam frame
```

---

## 7. Exclusions (`exclusions.py`)

| Source | Quantity | Overlay |
|--------|----------|---------|
| Columns (`S-COLS`, hatches) | Subtracted | Red |
| Sunk slab hatches | Subtracted | Red |
| Void text (STAIR, LIFT, …) | Cell skip / LLM | — |
| Beam footprints | **Not** subtracted by default | Red (QA only) |

Rationale: BOQ slab area is **between** beam centerlines, not minus full beam width.

---

## 8. Thickness engine (`thickness/parser.py`)

Priority per slab centroid:

1. `thickness_mm` on candidate from label merge.  
2. Nearest `*THK` within `thk_label_max_distance_mm`.  
3. Default from general note (`ALL SLABS ARE xxx mm THK`).

---

## 9. Quantity engine (`quantity/slab.py`)

```text
concrete_m3     = area_m2 × (thickness_mm / 1000)
shuttering_m2   = area_m2   (MVP: soffit = plan area)
```

All values rounded in export; `calculation_trace` string for audit.

---

## 10. AI boundary (`reasoning/`)

| Allowed | Forbidden |
|---------|-----------|
| `exclude_merged_slab_ids` | Computing area or volume |
| `exclude_cell_ids` (capped) | Inventing geometry |
| `merge_groups`, evidence, confidence | Replacing floor zone |

**Guards:** Reject LLM result if area drops >3% or too many exclusions.  
**Model:** `auto` → `deepseek-chat`, retry with `deepseek-reasoner`.

---

## 11. Configuration surface

`PipelineConfig` (`config.py`) — key fields:

```python
structural_layers          # e.g. ("S-BEAM",) or ("S_FRAMES", "STR-CUTOUT")
detection_mode             # auto | beam_grid | region | beam_frame
floor_zone_mode            # cluster | legacy | manual
merge_slabs_by_thk_labels  # True on tagged plans
apply_slab_exclusions      # True
enable_deepseek_refinement # CLI --llm
deepseek_model             # auto | deepseek-chat | deepseek-reasoner
min_slab_area_m2           # filter tiny artifacts
```

---

## 12. External dependencies

| Package | Use |
|---------|-----|
| ezdxf | DXF read |
| shapely | Polygons, difference, union |
| httpx | DeepSeek API |
| python-dotenv | API key from repo `.env` |

---

## 13. Benchmark wiring

| Drawing | Ground truth | Typical strategy |
|---------|--------------|------------------|
| Inizio_B2_LayerTest1 | `data/ground_truth/Inizio_B2_LayerTest1.json` | grid + label merge + cluster zone |
| Slab-02_Terrace | `data/ground_truth/Slab-02_Terrace_LayerTest.json` | grid, frame zone |

---

## Read next

- [01_SIMPLE_OVERVIEW.md](./01_SIMPLE_OVERVIEW.md) — non-technical summary  
- [03_PIPELINE_FLOW.md](./03_PIPELINE_FLOW.md) — flowcharts  
- [SESSION_PROGRESS.md](./SESSION_PROGRESS.md) — metrics and changelog  
