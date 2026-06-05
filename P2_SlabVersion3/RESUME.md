# Resume here — P2_SlabVersion3 (SDIE v3.3)

**Paused:** 2026-06-05  
**Active project:** `P2_SlabVersion3/`  
**Architecture:** Structural Component Intelligence (see `docs/Prompt_extracted.txt`)  
**Frozen baselines:** `../P2_SlabVersion1/`, `../P2_SlabVersion2/`

---

## Quick start

```powershell
cd C:\Users\nishanth.h\Phase2_Concrete_Estimation\P2_SlabVersion3
pip install -r requirements.txt
$env:PYTHONPATH="src"

# Regression (only where YOU provided ground truth)
python scripts/run_pipeline.py "Data Source/Slab Test/Inizio_B2_LayerTest1.dxf" `
  -o "Output/Slab Test" --mode auto --layers S-BEAM --min-area 0.4
python scripts/compare_to_ground_truth.py `
  "Output/Slab Test/Inizio_B2_LayerTest1_results.json" `
  data/ground_truth/Inizio_B2_LayerTest1.json
```

**Rule:** Do not compare new drawings to unrelated ground-truth JSON files. Add `data/ground_truth/<stem>.json` only when estimator BOQ is available.

---

## Verification runs (Output/SlabTest_V3)

| Drawing | Strategy | Slabs | Area | Concrete | BOQ provided? |
|---------|----------|-------|------|----------|---------------|
| `Slab -04 test 01_Layer_Test.dxf` | `beam_frame_bbox` | 1 | 60.5 m² | 12.1 m³ | Yes — 98.4% match |
| `Inizio_Terrace_LayerTest.dxf` | `semantic_label_merged_bay` | 12 | 169.2 m² | 33.8 m³ | **No** — model only |
| `TrustOffice_Terrace_Layer_Test.dxf` | `semantic_beam_grid_bay` | 122 | 642.0 m² | 96.3 m³ | **No** — model only |

Open overlays in `Output/SlabTest_V3/*_overlay.html` when resuming verification.

### TrustOffice config (when re-running)

```powershell
python scripts/run_pipeline.py "Data Source/TrustOffice_Terrace_Layer_Test.dxf" `
  -o "Output/SlabTest_V3" --mode auto --layers S_FRAMES --min-area 0.4
```

Default thickness: 150 mm (drawing note). Layer: `S_FRAMES` (not `S-BEAM`).

### Slab-04 config

```powershell
# Use beam_frame for small STR-BEAM drawings (via PipelineConfig or script)
# Layers: STR-BEAM, columns S-COLUMN, walls STR-RC WALL HATCH
```

---

## What to do next (when you return)

1. **Verify overlays** — TrustOffice, Inizio Terrace, Slab-04 in `Output/SlabTest_V3/`
2. Add ground truth JSON **only** when estimator BOQ is ready for a drawing
3. Fix terrace floor-zone stack cap (`grid_ymax_capped`) for `Inizio_Terrace` if engineer confirms under-count
4. Tune classification (`src/sdie/classification/`) before slab heuristics
5. Epic 7 Validation UI (future)

---

## Last known good (Inizio B2 — with BOQ)

| Metric | Model | BOQ |
|--------|-------|-----|
| Slabs | 73 | 73 |
| Area | 1935.5 m² | 1943.3 m² |
| Concrete | 431.7 m³ | 410.8 m³ (+5%) |

Strategy: `semantic_label_merged_bay` + `floor_zone` cluster.

---

## Atlas

`data/atlas/component_atlas.json` — **1986 samples** (merged from Inizio B2, Slab-04, Terrace, TrustOffice runs).

```powershell
python scripts/build_atlas.py "<new.dxf>" --merge
```

---

## Documentation

| # | File |
|---|------|
| 1 | [docs/01_SIMPLE_OVERVIEW.md](docs/01_SIMPLE_OVERVIEW.md) |
| 2 | [docs/02_ARCHITECTURE.md](docs/02_ARCHITECTURE.md) |
| 3 | [docs/03_PIPELINE_FLOW.md](docs/03_PIPELINE_FLOW.md) |
| 4 | [docs/04_CODE_GUIDE.md](docs/04_CODE_GUIDE.md) |
| Prompt | [docs/Prompt_extracted.txt](docs/Prompt_extracted.txt) |

---

## API key

`DEEPSEEK_API_KEY` in `C:\Users\nishanth.h\Phase2_Concrete_Estimation\.env` (optional `--llm`, `--component-llm`).
