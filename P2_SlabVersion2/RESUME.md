# P2_SlabVersion2 — Frozen (resume in V3)

**Frozen:** 2026-06-04  
**Active project:** `../P2_SlabVersion3/` — see `RESUME.md` there  
**Frozen baselines:** `P2_SlabVersion1/`, `P2_SlabVersion2/` (do not edit for new work)

---

## Quick start

```powershell
cd C:\Users\nishanth.h\Phase2_Concrete_Estimation\P2_SlabVersion2
pip install -r requirements.txt
$env:PYTHONPATH="src"

# Smoke test (Inizio B2 — should match V1: 73 slabs, ~1935 m²)
python scripts/run_pipeline.py "Data Source/Slab Test/Inizio_B2_LayerTest1.dxf" `
  -o "Output/Slab Test" --mode auto --layers S-BEAM --min-area 0.4

python scripts/compare_to_ground_truth.py `
  "Output/Slab Test/Inizio_B2_LayerTest1_results.json" `
  data/ground_truth/Inizio_B2_LayerTest1.json
```

Open overlay: `Output/Slab Test/Inizio_B2_LayerTest1_overlay.html`

---

## What to do next

1. Place **new drawing** DXF in `Data Source/Slab Test/`
2. Run pipeline with correct `--layers` (see [docs/NEW_DRAWING_GUIDE.md](docs/NEW_DRAWING_GUIDE.md))
3. Add `data/ground_truth/<name>.json` if you have estimator BOQ
4. Implement changes only under `P2_SlabVersion2/src/sdie/`

---

## Documentation (read in order)

| # | File |
|---|------|
| 1 | [docs/01_SIMPLE_OVERVIEW.md](docs/01_SIMPLE_OVERVIEW.md) |
| 2 | [docs/02_ARCHITECTURE.md](docs/02_ARCHITECTURE.md) |
| 3 | [docs/03_PIPELINE_FLOW.md](docs/03_PIPELINE_FLOW.md) |
| 4 | [docs/04_CODE_GUIDE.md](docs/04_CODE_GUIDE.md) |
| Index | [docs/README.md](docs/README.md) |

---

## Last known good (Inizio B2)

| Metric | Model | BOQ |
|--------|-------|-----|
| Slabs | 73 | 73 |
| Area | 1935.5 m² | 1943.3 m² |
| Concrete | 431.7 m³ | 410.8 m³ (+5%) |

Strategy: `label_merged_bay` + `floor_zone` cluster mode.

---

## API key

`DEEPSEEK_API_KEY` in `C:\Users\nishanth.h\Phase2_Concrete_Estimation\.env` (optional `--llm`).

---

## Import manifest

See [MANIFEST.md](MANIFEST.md) for what was copied from Version 1.
