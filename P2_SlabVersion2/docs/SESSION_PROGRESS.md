# SDIE Phase 2 — Session Progress (resume checkpoint)

**Last updated:** 2026-06-04 (paused — resume in Version 2)  
**Project root:** `P2_SlabVersion2/` — **active**  
**Baseline (frozen):** `../P2_SlabVersion1/` — see `VERSION1_COMPLETE.md`  
**Resume file:** `../RESUME.md`  
**Design reference:** `docs/MODEL_DESIGN.md`, `docs/Prompt_extracted.txt`

---

## Goal

Build **SDIE** (Structural Drawing Intelligence Engine): read consultant DXF → explainable slab area, concrete m³, shuttering m².

- **Deterministic geometry** computes all quantities (Prompt §6).
- **DeepSeek** (optional `--llm`) only classifies keep/exclude/merge — never area math.
- **Generic floor zone** for multi-stack sheets (no per-drawing hardcoding).

---

## Pipeline flow (current)

```text
DXF → floor zone (Y-cluster + stack cap)
    → beam grid bays (S-BEAM / S_FRAMES) + exclusions
    → merge cells by nearest A-FLOR-IDEN *THK label
    → [optional] DeepSeek validation
    → thickness (local THK + default note)
    → quantities + overlay (SVG + HTML pan/zoom)
```

---

## What is implemented

| Component | Path | Notes |
|-----------|------|--------|
| DXF ingestion + mm units | `src/sdie/ingestion/` | `area_to_m2_factor` from INSUNITS |
| **Floor zone (generic)** | `src/sdie/detection/floor_zone.py` | `cluster` mode: THK Y-clusters, satellite merge, sub-panel pick, **stack-repeat cap** |
| Beam-grid bays | `src/sdie/detection/beam_grid.py` | Strategy B; void centroid skip |
| **Exclusions** | `src/sdie/detection/exclusions.py` | Columns, sunk slab; beam footprints overlay-only by default |
| **Label merge** | `src/sdie/detection/slab_by_label.py` | One slab per *THK tag; sum net cell areas |
| Thickness | `src/sdie/thickness/parser.py` | 200/275 THK + default note |
| **DeepSeek reasoning** | `src/sdie/reasoning/` | `auto` = chat then reasoner on failure |
| Pipeline + CLI | `scripts/run_pipeline.py` | `--llm`, `--deepseek-model auto` |
| Compare | `scripts/compare_to_ground_truth.py` | ±5% default on area/concrete |
| Overlay | `src/sdie/validation/overlay.py` | Blue slabs, red exclusions, HTML viewer |
| Tests | `tests/test_floor_zone.py` | Inizio cluster vs legacy band |

**API key:** `Phase2_Concrete_Estimation/.env` → `DEEPSEEK_API_KEY`

---

## Benchmark: Inizio B2 (primary validation)

| Item | Value |
|------|--------|
| DXF | `Data Source/Slab Test/Inizio_B2_LayerTest1.dxf` |
| Structural layer | `S-BEAM` |
| Ground truth | `data/ground_truth/Inizio_B2_LayerTest1.json` |
| Estimator BOQ | 1943.34 m², 410.76 m³, **73 slabs** |

### Latest run (geometry only, `floor_zone_mode=cluster`)

| Metric | Model | BOQ | Δ |
|--------|-------|-----|---|
| Slab count | **73** | 73 | 0 |
| Area / shuttering | **1935.5 m²** | 1943.3 m² | −0.4% |
| Concrete | **431.7 m³** | 410.8 m³ | +5.1% |

**Strategy:** `label_merged_bay`  
**Floor zone:** 73 THK labels in band; grid Y capped below stacked plan repeat (~53330 mm)  
**Outputs:** `Output/Slab Test/Inizio_B2_LayerTest1_*.{json,svg,html,summary}`

### Improvement timeline (Inizio)

| Stage | Slabs | Area m² | Issue |
|-------|-------|---------|--------|
| Raw beam grid | ~284 | ~2019 | Micro-bays; beams/walls counted as slab |
| Grid + exclusions | ~284 | ~1935 | Area OK; count wrong |
| Label merge (legacy Y-band) | 51 | ~1935 | Missed 22 THK tags (truncated ymax) |
| Full Y-band (no stack cap) | 73 | ~2340 | Double-counted vertical plan copy |
| **Cluster + stack cap + dual bounds** | **73** | **~1936** | **Current best** |

---

## Other test drawings

| Drawing | Layers (typical) | Status |
|---------|------------------|--------|
| Slab-02 Terrace | `S_FRAMES STR-CUTOUT` | ~273 m² vs 310 BOQ; no *THK tags — uses `frame_structure` zone |
| Slab-02 FirstF | `S_FRAMES STR-CUTOUT` | Pending full BOQ compare |
| Slab-04 | `STR-BEAM` | Small plan; beam_frame OK |
| Slab-02_Layer_Try (5 floors) | Multi-panel | Deferred — needs per-floor run |

---

## Configuration defaults (`PipelineConfig`)

| Setting | Default | Purpose |
|---------|---------|---------|
| `floor_zone_mode` | `cluster` | Generic THK clustering (`legacy` = old fixed span) |
| `merge_slabs_by_thk_labels` | `True` | Merge grid cells per *THK |
| `min_thk_labels_for_merge` | `25` | Auto-lowers on small floors |
| `exclude_beam_footprints_from_quantity` | `True` | Clear span between beam centerlines |
| `grid_slab_face_expand_mm` | `55` | Bay face between beams |
| `enable_deepseek_refinement` | `False` | Set via `--llm` |
| `deepseek_model` | `auto` | chat → reasoner on retry |

---

## Commands

### Inizio B2 (recommended)

```powershell
cd C:\Users\nishanth.h\Phase2_Concrete_Estimation\P2_SlabVersion1
$env:PYTHONPATH="src"

python scripts/run_pipeline.py "Data Source/Slab Test/Inizio_B2_LayerTest1.dxf" `
  -o "Output/Slab Test" --mode auto --layers S-BEAM --min-area 0.4

python scripts/compare_to_ground_truth.py `
  "Output/Slab Test/Inizio_B2_LayerTest1_results.json" `
  data/ground_truth/Inizio_B2_LayerTest1.json
```

### New drawing (S_FRAMES family)

```powershell
python scripts/run_pipeline.py "Data Source/Slab Test/YOUR_DRAWING.dxf" `
  -o "Output/Slab Test" --mode auto --layers S_FRAMES STR-CUTOUT --min-area 0.4
```

### Optional LLM refinement

```powershell
python scripts/run_pipeline.py "..." -o "Output/Slab Test" --mode auto --layers S-BEAM --min-area 0.4 --llm
```

### Dependencies

```powershell
pip install -r requirements.txt
# ezdxf shapely httpx python-dotenv
```

---

## Testing a new drawing (checklist)

1. **Audit layers** — Note structural frame layer (`S-BEAM`, `S_FRAMES`, etc.) and `A-FLOR-IDEN` for *THK.
2. **Run auto** — `python scripts/run_pipeline.py <dxf> -o "Output/Slab Test" --mode auto --layers <FRAME> --min-area 0.4`
3. **Check `detection_notes` in JSON** — `floor_zone`, `selected`, `thk_labels_in_floor`, `beam_grid_cell_count`, `label_merged_count`.
4. **Open overlay HTML** — Pan/zoom; blue = slab, red = exclusions.
5. **Compare BOQ** — Add `data/ground_truth/<stem>.json` and run `compare_to_ground_truth.py`.
6. **Tune only if needed** — `floor_bounds_y=(ymin,ymax)` manual override, or `--mode beam_grid` / `region`.

---

## Known limitations (next work)

1. **Concrete +5% on Inizio** — More 275 mm local THK vs estimator average; thickness mix not reconciled.
2. **Terrace / no-THK drawings** — Frame-structure zone; area still ~12% under BOQ.
3. **Per-slab ID vs estimator S1…Sn** — Not mapped yet.
4. **Multi-floor single DXF** — One floor per run; split by floor zone or title.
5. **LLM** — Use only for ambiguous voids; geometry path is default for production.

---

## Key paths

| What | Where |
|------|--------|
| DXF inputs | `Data Source/Slab Test/` |
| Outputs | `Output/Slab Test/` |
| Ground truth | `data/ground_truth/` |
| Progress doc | `docs/SESSION_PROGRESS.md` (this file) |
| New drawing guide | `docs/NEW_DRAWING_GUIDE.md` |
| Source | `src/sdie/` |

---

## Decisions log (2026-06-04)

| # | Decision | Choice |
|---|----------|--------|
| D8 | Floor zone | Y-cluster *THK + beam-scored sub-panel + stack cap |
| D9 | Slab count on Inizio | One merged bay per *THK label (73 tags) |
| D10 | Beam in quantity | Exclude footprints from area; show red on overlay |
| D11 | DeepSeek role | Semantic filter only; `auto` model |
| D12 | Quantity math | Always Shapely/grid sums, never LLM |
