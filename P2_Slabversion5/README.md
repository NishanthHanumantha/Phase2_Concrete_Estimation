# P2_SlabVersion5 — SDIE v5 Structural Reasoning Engine

Lean runtime from **P2_SlabVersion4** with the **v5 DeepSeek structural reasoning** pipeline (estimator-style multi-evidence classification).

## What is included

| Path | Purpose |
|------|---------|
| `src/sdie/` | Full pipeline (ingestion → RAG → classify → graph → slabs → quantities → overlay) |
| `data/atlas/` | Component atlas (~58 MB) |
| `data/knowledge_base/` | Structural KB |
| `data/layer_profiles.json` | Per-project layer rules (Phase A) |
| `data/ground_truth/` | Workbook-derived GT JSON (benchmark) |
| `Data Source/TestInput/` | Trust Office FF regression DXF |
| `Data Source/Ground Truths/TestGT/` | Slab GT Excel |
| `Data Source/projects_manifest.json` | Project manifest (teach paths; DXFs not bundled) |
| `scripts/` | `run_pipeline`, teach, ingest, eval, verify |
| `docs/Prompt_extracted_pdf.txt` | V5 spec (from SDIE Version 5 PDF/docx) |
| `docs/Prompt_extracted_V4.txt` | V4 spec (archive) |

## What is omitted (stay in V4)

- All `Output/` results (regenerate locally)
- Full teach DXFs (`Project1–3` folders, ~200 MB)
- Docs PDFs, audits, tests, API deployment extras
- Copy teach DXFs from V4 when running `teach_all_projects.py`

## Setup

```powershell
cd C:\Users\nishanth.h\Phase2_Concrete_Estimation\P2_SlabVersion5
pip install -r requirements.txt
$env:PYTHONPATH="src"
```

**DeepSeek API:** uses `C:\Users\nishanth.h\Phase2_Concrete_Estimation\.env`  
(`DEEPSEEK_API_KEY` — resolved automatically via `src/sdie/reasoning/env.py`)

## Run pipeline (test drawing)

```powershell
python scripts/run_pipeline.py `
  "Data Source/TestInput/TrustOffice_FF_LayerTest_RAG.dxf" `
  -o "Output/TestRun" `
  --project-id TRUST_OFFICE `
  --layers S_FRAMES STR-CUTOUT `
  --min-area 0.4
```

Add `--no-deepseek` for rule+topology scoring without API calls.  
Add `--v4-only` to fall back to the v4 RAG classifier.

Outputs: `*_results.json`, `*_building_model.json`, `*_overlay.html`, `*_summary.txt`, `*_review_queue.json` (v5 low-confidence entities)

## Verify slab GT

```powershell
python scripts/verify_test_gt.py --results "Output/TestRun/TrustOffice_FF_LayerTest_RAG_results.json"
```

## Component classification eval

Requires component-tagged DXFs — copy from V4 `Data Source/Project*` folders first, then:

```powershell
python scripts/evaluate_component_classification.py --tagged-only --baseline --drawing "Colum"
```

## Rebuild teach corpus (after adding project DXFs)

```powershell
python scripts/ingest_estimator_workbooks.py --build-atlas --fresh-atlas --build-kb
python scripts/build_layer_profiles.py
```

## Parent repo

- **V4 (full):** `../P2_SlabVersion4` — frozen reference + all data
- **V5 (this):** lean workspace for major model changes
