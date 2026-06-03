# SDIE Phase 2 — Session Progress (resume checkpoint)

**Last updated:** 2026-06-03  
**Project root:** `P2_SlabVersion1/`

---

## Goal

Build **SDIE** (Structural Drawing Intelligence Engine): read consultant DXF slab/framing drawings → explainable slab area, concrete m³, shuttering m². **Not** a black-box estimator; deterministic quantity engine + detection strategies.

**Design reference:** `docs/MODEL_DESIGN.md`, `docs/Prompt_extracted.txt`

---

## What is implemented

| Component | Path | Notes |
|-----------|------|--------|
| DXF ingestion + mm units | `src/sdie/ingestion/` | Auto-mm when coords are large |
| Region polygonize (Strategy A) | `src/sdie/detection/region.py` | Small closed loops only on framing plans |
| Beam-frame bbox (fallback) | `src/sdie/detection/beam_frame.py` | Single expanded bbox |
| **Beam-grid bays (Strategy B)** | `src/sdie/detection/beam_grid.py` | **Primary for S_FRAMES plans** |
| Thickness parser | `src/sdie/thickness/parser.py` | General note + local THK |
| Pipeline + CLI | `src/sdie/pipeline.py`, `scripts/run_pipeline.py` | `--mode auto\|region\|beam_frame\|beam_grid` |
| Compare script | `scripts/compare_to_ground_truth.py` | Area/concrete/shuttering + slab count |
| SVG overlay | `src/sdie/validation/overlay.py` | Visual QA |

**Default CLI layers:** `S_FRAMES STR-CUTOUT`  
**Default min slab area:** 10 m² (use `--min-area 0.4` for Slab-02 family tests)

---

## Test drawings — status

| Drawing | Input DXF | Expected BOQ | Last run (auto) | Regression |
|---------|-----------|----------------|-----------------|------------|
| Slab-04 | `Data Source/Slab Test/Slab -04 test 01_Layer_Test.dxf` | Yes (estimator) | ~60.5 m², 1 slab, STR-BEAM beam_frame | ~−1.6% area (pass) |
| Terrace | `Data Source/Slab Test/Slab-02_Terrace_LayerTest.dxf` | `Expected Output/Slab-02_Terrace_ExpectedOutput.xlsx` | **45 slabs**, 298.7 m², beam_grid | **Pass ±5%** vs `data/ground_truth/Slab-02_Terrace_LayerTest.json` (42 slabs expected; count ±3 OK) |
| **First Floor** | `Data Source/Slab Test/Slab-02_FirstF_LayerTest.dxf` | **None yet** | **52 slabs**, 322.3 m², beam_grid | Pending BOQ |
| LGF (multi-floor file) | `Data Source/Slab Test/Slab-02_Layer_Try.dxf` | `data/ground_truth/Slab-02_Layer_Try.json` (scaled polygons) | **Deferred** | Needs real Strategy B, not area scaling |

### First Floor outputs (saved, no estimator compare)

```
Output/Slab Test/
  Slab-02_FirstF_LayerTest_results.json
  Slab-02_FirstF_LayerTest_summary.txt
  Slab-02_FirstF_LayerTest_overlay.svg
```

- Detection: `beam_grid_bay` (197 H + 179 V lines on `S_FRAMES`)
- Thickness: 150 mm from general note
- Hypothetical wrong strategies: region 20 slabs / 111 m²; beam_frame bbox 1 slab / 382 m²

### Terrace outputs

```
Output/Slab Test/
  Slab-02_Terrace_LayerTest_*.{json,svg,summary}
```

Ground truth: `data/ground_truth/Slab-02_Terrace_LayerTest.json`  
Excel BOQ concrete uses **200 mm**; model uses drawing note **150 mm** for concrete compare.

---

## Known issues (for generic model work tomorrow)

1. **Slab count vs estimator** — Grid often finds **45–52 bays** vs estimator **42** (Terrace): edge slivers / merge rules not aligned with manual BOQ.
2. **Area ~3–4% under** Terrace total (298.7 vs 310.4 m²) — face expansion / void rules may need tuning.
3. **No per-slab ID matching** — S1…S42 in Excel not mapped to `SLAB-001…` polygons yet.
4. **LGF still open** — `Slab-02_Layer_Try.dxf` has 5 floors in one file; floor zone split + bay detection not done.
5. **Drawing-specific configs** — Span thresholds (3000/2000 mm), axis cluster tol (300 mm), void radius (2000 mm) tuned on Terrace; may need profiles per drawing type.

---

## Commands to resume

```powershell
cd C:\Users\nishanth.h\Phase2_Concrete_Estimation\P2_SlabVersion1

# Re-run First Floor (outputs already saved)
python scripts/run_pipeline.py "Data Source/Slab Test/Slab-02_FirstF_LayerTest.dxf" -o "Output/Slab Test" --mode auto --layers S_FRAMES STR-CUTOUT --min-area 0.4

# Terrace + compare (when validating)
python scripts/run_pipeline.py "Data Source/Slab Test/Slab-02_Terrace_LayerTest.dxf" -o "Output/Slab Test" --mode auto --layers S_FRAMES STR-CUTOUT --min-area 0.4
python scripts/compare_to_ground_truth.py "Output/Slab Test/Slab-02_Terrace_LayerTest_results.json" data/ground_truth/Slab-02_Terrace_LayerTest.json
```

---

## Suggested next session

1. Obtain **First Floor estimator BOQ** (Excel) → add `data/ground_truth/Slab-02_FirstF_LayerTest.json` + compare.
2. Visual QA: `Slab-02_FirstF_LayerTest_overlay.svg` vs plan.
3. Before generic model changes: document **3–5 failure modes** across Terrace + FirstF + Slab-04 (layer choice, strategy choice, voids, thickness).
4. Implement incremental improvements: void/cutout polygons, merge micro-bays, floor zone split for `Slab-02_Layer_Try.dxf`.

---

## Key paths quick reference

| What | Where |
|------|--------|
| DXF tests | `Data Source/Slab Test/` |
| Outputs | `Output/Slab Test/` |
| Expected BOQ (Terrace) | `Expected Output/Slab-02_Terrace_ExpectedOutput.xlsx` |
| Ground truth | `data/ground_truth/` |
| Audits | `data/audits/` |
