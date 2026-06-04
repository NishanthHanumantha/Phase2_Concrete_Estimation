# SDIE — Important Code Guide

Explanation of the **main source files and functions** that implement the slab model.  
Read with: [01_SIMPLE_OVERVIEW.md](./01_SIMPLE_OVERVIEW.md) · [02_ARCHITECTURE.md](./02_ARCHITECTURE.md) · [03_PIPELINE_FLOW.md](./03_PIPELINE_FLOW.md)

---

## 1. Where execution starts

| Entry | File | Role |
|-------|------|------|
| CLI | `scripts/run_pipeline.py` | Parses args, builds `PipelineConfig`, calls `run_pipeline()` |
| Orchestrator | `src/sdie/pipeline.py` | **`run_pipeline()`** — entire job |
| Compare | `scripts/compare_to_ground_truth.py` | Checks JSON totals vs `data/ground_truth/*.json` |

```python
# scripts/run_pipeline.py (simplified)
config = PipelineConfig(
    structural_layers=tuple(args.layers),
    detection_mode=args.mode,
    min_slab_area_m2=args.min_area,
    enable_deepseek_refinement=args.llm,
    deepseek_model=args.deepseek_model,
)
result = run_pipeline(dxf_path, output_dir, config)
```

---

## 2. Configuration — all tunables in one place

**File:** `src/sdie/config.py`  
**Class:** `PipelineConfig` (dataclass)

| Field | What it controls |
|-------|------------------|
| `structural_layers` | DXF layers for beam lines (`S-BEAM`, `S_FRAMES`, …) |
| `detection_mode` | `auto` \| `beam_grid` \| `region` \| `beam_frame` |
| `floor_zone_mode` | `cluster` (default) \| `legacy` \| `manual` |
| `floor_bounds_y` | Manual `(ymin, ymax)` when mode is `manual` |
| `merge_slabs_by_thk_labels` | Group grid cells per `*THK` tag |
| `min_thk_labels_for_merge` | Minimum tags before merge runs (default 25) |
| `grid_slab_face_expand_mm` | Expand bay to clear span between beams (default 55) |
| `apply_slab_exclusions` | Subtract columns / hatches from bays |
| `exclude_beam_footprints_from_quantity` | If `True`, beams only on red overlay |
| `column_exclusion_layers` | e.g. `S-COLS`, `S-COL HATCH` |
| `enable_deepseek_refinement` | Set by `--llm` |
| `deepseek_model` | `auto` \| `deepseek-chat` \| `deepseek-reasoner` |

---

## 3. Core data type — `SlabCandidate`

**File:** `src/sdie/detection/region.py`

Every detection strategy returns a list of these:

```python
@dataclass
class SlabCandidate:
    slab_id: str              # "SLAB-001"
    polygon_wkt: str          # Shapely polygon, WKT, mm coords
    area_m2: float            # Net area after exclusions
    centroid_cm: list[float]  # [x, y] for thickness lookup
    bounds_cm: list[float]    # [xmin, ymin, xmax, ymax]
    strategy: str             # e.g. "label_merged_bay"
    thickness_mm: int | None  # Set when merged from THK label
```

**Important:** `area_m2` is trusted for BOQ. After label merge, it is the **sum of grid cell areas**, not only the union polygon area (avoids double-count when union overlaps).

---

## 4. Pipeline orchestrator (`pipeline.py`)

### 4.1 `run_pipeline(dxf_path, output_dir, config)`

**Phase A — Load and annotations**

```python
doc, meta = load_drawing(dxf_path)
msp = doc.modelspace()
default_mm, note_text = extract_default_thickness_mm(msp, config.annotation_layers)
thk_labels = extract_thk_labels(msp, config.annotation_layers)
area_factor = meta.area_to_m2_factor  # cm² → m² typically 1e-6
```

**Phase B — Beam grid path** (when `auto` sees enough frame lines)

1. `resolve_floor_zone(...)` → `FloorZone` with `bounds_y` + `label_bounds_y`
2. `build_exclusion_catalog(...)` → `ExclusionCatalog`
3. `detect_beam_grid_slabs(..., bounds_y=floor_bounds_y, exclusions=...)`
4. `detect_label_merged_slabs(..., bounds_y=label_bounds_y, grid_cells=...)`
5. Optional `refine_slabs_with_deepseek(...)`
6. Pick `geometric_selected` or LLM result

**Phase C — Fallbacks** if no grid candidates

- `detect_closed_regions()` — polygonize
- `detect_beam_frame_slab()` — single bbox

**Phase D — Quantities and export**

For each `SlabCandidate`:

```python
thk_mm, thk_src, thk_dist, thk_conf = nearest_thickness_mm(...)
qty = compute_slab_quantity(cand.area_m2, thk_mm, ...)
# → append to slabs[] dict, write JSON, overlay, summary
```

**Key branching** (grid path):

```134:211:src/sdie/pipeline.py
            label_bounds_y = floor_bounds_y
            if floor_zone is not None:
                label_bounds_y = floor_zone.thk_filter_bounds_y
            # ... thk_in_floor filtered by label_bounds_y ...
            grid_candidates = detect_beam_grid_slabs(
                msp,
                ...
                bounds_y=floor_bounds_y,
                exclusions=exclusions,
            )
            # ... label_merged = detect_label_merged_slabs(..., grid_cells=grid_candidates) ...
            if label_merged:
                geometric_selected = label_merged
                detection_notes["selected"] = "label_merged_bay"
            elif grid_candidates:
                geometric_selected = grid_candidates
                detection_notes["selected"] = "beam_grid_bay"
```

---

## 5. Ingestion

### 5.1 `load_drawing(path)` — `ingestion/dxf_reader.py`

- Opens DXF with **ezdxf**
- `resolve_units(doc)` → internal **mm**, `area_to_m2_factor` for m²
- Returns `(doc, DrawingMeta)` used everywhere for unit-safe math

### 5.2 `resolve_units` — `ingestion/units.py`

Maps `$INSUNITS` (often cm on Slab-02 / Inizio) to:

- `coordinate_unit` — `"mm"` for geometry
- `area_to_m2_factor` — multiply Shapely `.area` to get m²

---

## 6. Floor zone — which floor on the sheet

**File:** `src/sdie/detection/floor_zone.py`  
**Main API:** `resolve_floor_zone(msp, ...) → FloorZone`

### `FloorZone` fields

| Field | Meaning |
|-------|---------|
| `bounds_y` | Y range for **beam grid** (area takeoff) |
| `label_bounds_y` | Wider Y range for **THK tags** (slab count) |
| `thk_filter_bounds_y` | Property: `label_bounds_y or bounds_y` |
| `method` | `thk_cluster`, `frame_structure`, `floor_title`, `manual` |

### Important functions

| Function | Purpose |
|----------|---------|
| `_cluster_labels_by_y` | Split THK tags into Y-clusters (gap > 6 m) |
| `_count_frame_lines_in_band` | Score cluster by beam H/V line count |
| `_split_cluster_subpanels` | Split one cluster at large internal gaps |
| `_pick_best_subpanel` | Choose sub-panel with most structure |
| `_cap_grid_ymax_for_stacked_plan` | Stop grid below repeated plan copy on sheet |
| `infer_bounds_from_frame_structure` | Fallback when no THK tags (Terrace) |

**Why two bounds?** On Inizio, 73 tags span a tall sheet; counting area on the full height **double-counts** a repeated plan. Grid uses capped `bounds_y`; merge still sees all 73 tags via `label_bounds_y`.

---

## 7. Beam grid — slab bays between beams

**File:** `src/sdie/detection/beam_grid.py`  
**Main API:** `detect_beam_grid_slabs(msp, ...) → list[SlabCandidate]`

### Steps inside

1. **`_collect_grid_axes`** — Scan `LINE` on structural layers; cluster into horizontal Y axes and vertical X axes (only lines in `bounds_y`).
2. **Nested loops** over axis intervals → rectangle `box(xmin, ymin, xmax, ymax)`.
3. **Expand** each cell by `slab_face_expand_mm` (~55 mm) so the bay reaches **clear span** between beam centerlines.
4. **`exclusions.difference(raw_poly)`** — subtract column/sunk regions.
5. **Void skip** — if centroid near TEXT containing STAIR, LIFT, RAMP, skip cell.
6. Emit `SlabCandidate` per cell (`strategy="beam_grid_bay"`).

Core loop:

```225:271:src/sdie/detection/beam_grid.py
    for i in range(len(axes_x) - 1):
        for j in range(len(axes_y) - 1):
            xmin = axes_x[i] - expand
            xmax = axes_x[i + 1] + expand
            ymin = axes_y[j] - expand
            ymax = axes_y[j + 1] + expand
            raw_poly = box(xmin, ymin, xmax, ymax)
            if apply_exclusions and exclusions is not None:
                poly = exclusions.difference(raw_poly, area_to_m2_factor)
            # ... bounds_y filter, void_points skip ...
            candidates.append(SlabCandidate(..., strategy="beam_grid_bay"))
```

**Auto trigger:** `count_orthogonal_frame_lines` — if H ≥ 80 and V ≥ 60, `auto` uses grid (Inizio: 141 H, 89 V).

---

## 8. Exclusions — non-slab geometry

**File:** `src/sdie/detection/exclusions.py`  
**Main API:** `build_exclusion_catalog(msp, ...) → ExclusionCatalog`

### `ExclusionCatalog.difference(slab_poly, area_to_m2_factor)`

```python
net = slab_poly.difference(self.union)
# Returns largest polygon piece if MultiPolygon; None if fully removed
```

| Built from | Quantity | Overlay |
|------------|----------|---------|
| Column layers, hatches | Subtracted | Red |
| Beam footprints (optional) | Usually **not** subtracted | Red via `build_beam_footprint_overlay` |
| Void TEXT | Used in beam_grid skip radius | — |

`VOID_KEYWORD_RADIUS_MM` maps keywords (STAIR, LIFT, …) to skip radius in `_collect_void_points` inside `beam_grid.py`.

---

## 9. Label merge — one slab per THK tag

**File:** `src/sdie/detection/slab_by_label.py`

### `merge_grid_cells_by_label(grid_cells, labels, ...)`

1. For each grid cell, find **nearest** `ThicknessLabel` by centroid distance.
2. **`_assign_orphan_labels`** — if a label has no cell, steal nearest cell from a label that has ≥2 cells.
3. For each non-empty group:
   - `area_m2 = sum(c.area_m2 for c in cell_group)` ← BOQ area
   - `unary_union` of cell polygons for **display** WKT
   - `thickness_mm = label.value_mm` from parsed `200 THK` / `275 THK`

```75:116:src/sdie/detection/slab_by_label.py
    for cell in grid_cells:
        best = min(range(len(labels)), key=lambda i: hypot(cx - label[i].x, cy - label[i].y))
        groups[best].append(cell)
    _assign_orphan_labels(labels, groups, grid_cells)
    for label, cell_group in zip(labels, groups):
        area_m2 = sum(c.area_m2 for c in cell_group)
        piece = unary_union([wkt.loads(c.polygon_wkt) for c in cell_group])
        candidates.append(SlabCandidate(..., strategy="label_merged_bay", thickness_mm=label.value_mm))
```

### `detect_label_merged_slabs(...)`

- Filters labels with `_labels_in_band(..., bounds_y)` — uses **label_bounds_y** from pipeline.
- Reuses pre-built `grid_cells` from pipeline (same exclusions already applied).

---

## 10. Thickness

**File:** `src/sdie/thickness/parser.py`

| Function | Purpose |
|----------|---------|
| `extract_thk_labels` | Regex `(\d+)\s*THK` on `A-FLOR-IDEN` TEXT/MTEXT |
| `extract_default_thickness_mm` | General note `ALL SLABS ARE xxx mm THK` |
| `nearest_thickness_mm` | Per-slab fallback if `thickness_mm` not on candidate |

**Distance fix:** `max_label_distance_mm` is in **mm** (was wrongly scaled earlier).

---

## 11. Quantity engine

**File:** `src/sdie/quantity/slab.py`

```python
def compute_slab_quantity(area_m2, thickness_mm, *, shuttering_equals_soffit=True):
    concrete_m3 = area_m2 * (thickness_mm / 1000.0)
    shuttering_m2 = area_m2  # MVP
```

No other module should compute volume for export — keeps LLM boundary clean.

---

## 12. Optional AI layer

| File | Role |
|------|------|
| `reasoning/env.py` | Load `DEEPSEEK_API_KEY` from repo `.env` |
| `reasoning/deepseek_client.py` | `chat_json()`, `resolve_model("auto")` |
| `reasoning/context.py` | `build_slab_reasoning_context()` — compact JSON for prompt |
| `reasoning/slab_refinement.py` | `refine_slabs_with_deepseek()` |

### `refine_slabs_with_deepseek` logic

1. Build context: merged slabs, void texts, floor zone notes.
2. Call DeepSeek → JSON `{ exclude_merged_slab_ids, exclude_cell_ids, ... }`.
3. **`_apply_llm_result`** — filter slabs; optional regen merge from filtered cells.
4. **Guards:** reject if exclusions >15% of slabs or area drops >3% vs geometric.
5. Retry with `deepseek-reasoner` if `model=auto` and first attempt fails.

LLM **never** returns m² or m³ — only IDs to exclude.

---

## 13. Validation overlay

**File:** `src/sdie/validation/overlay.py`  
**API:** `write_overlay_outputs(stem, output_dir, slabs, extents, ...)`

- Writes SVG + HTML with pan/zoom
- Slabs: blue fill, thickness-based stroke color
- `excluded_wkt`: red hatch (columns + beam footprints for QA)

---

## 14. Call chain — Inizio B2 (happy path)

```text
run_pipeline
  └─ load_drawing
  └─ extract_thk_labels / extract_default_thickness_mm
  └─ count_orthogonal_frame_lines → try_grid=True
  └─ resolve_floor_zone (cluster)
       └─ infer_bounds_from_thk_clusters
  └─ build_exclusion_catalog
  └─ detect_beam_grid_slabs (bounds_y = grid band)
  └─ detect_label_merged_slabs (label_bounds_y, grid_cells)
       └─ merge_grid_cells_by_label
  └─ [optional] refine_slabs_with_deepseek
  └─ for each candidate:
       └─ nearest_thickness_mm (or use label thickness)
       └─ compute_slab_quantity
  └─ write JSON + overlay + summary
```

---

## 15. Output JSON shape (what to inspect)

`detection_notes` — debugging:

| Key | Meaning |
|-----|---------|
| `floor_zone` | Method, label count, stack cap notes |
| `floor_bounds_y_mm` | Grid band |
| `label_bounds_y_mm` | THK band (if wider) |
| `beam_grid_cell_count` | Micro-bays before merge |
| `label_merged_count` | Final slab count |
| `selected` | `label_merged_bay` or `label_merged_bay_llm` |
| `llm_refinement` | If `--llm` |

Each item in `slabs[]`:

- `polygon_wkt`, `area_m2`, `thickness_mm`, `thickness_source`
- `concrete_m3`, `shuttering_m2`, `calculation_trace`

---

## 16. Where to change behaviour

| Goal | File / function |
|------|-----------------|
| New structural layer name | `PipelineConfig.structural_layers` or CLI `--layers` |
| Fix wrong floor on sheet | `floor_zone.py` — `resolve_floor_zone` / manual `floor_bounds_y` |
| Too many micro-slabs | Ensure `merge_slabs_by_thk_labels=True`; lower `--min-area` only if needed |
| Area too high (stacked plans) | `floor_zone.py` — `_cap_grid_ymax_for_stacked_plan` |
| Columns still in slab area | `exclusions.py` — `column_exclusion_layers` |
| Stairs counted as slab | `beam_grid.py` — `_collect_void_points` keywords/radius |
| Thickness wrong | `thickness/parser.py` — regex / `thk_label_max_distance_mm` |
| Stricter LLM | `slab_refinement.py` — guards and `SYSTEM_PROMPT` |
| BOQ formulas | `quantity/slab.py` only |

---

## 17. Tests

| File | Covers |
|------|--------|
| `tests/test_floor_zone.py` | Inizio cluster includes ≥73 labels; cluster wider than legacy |

Run: `python -m pytest tests/test_floor_zone.py -q`

---

## 18. Related docs

| Document | Topic |
|----------|--------|
| [01_SIMPLE_OVERVIEW.md](./01_SIMPLE_OVERVIEW.md) | Concepts |
| [02_ARCHITECTURE.md](./02_ARCHITECTURE.md) | System design |
| [03_PIPELINE_FLOW.md](./03_PIPELINE_FLOW.md) | Diagrams |
| [SESSION_PROGRESS.md](./SESSION_PROGRESS.md) | Benchmark numbers |
| [NEW_DRAWING_GUIDE.md](./NEW_DRAWING_GUIDE.md) | New DXF checklist |
