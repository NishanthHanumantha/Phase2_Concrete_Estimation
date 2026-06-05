# P2_SlabVersion3 — Import manifest

Copied from `P2_SlabVersion2` on 2026-06-04.

## Source code (`src/sdie/`)

```
sdie/
├── __init__.py
├── config.py
├── pipeline.py
├── ingestion/
│   ├── dxf_reader.py
│   └── units.py
├── detection/
│   ├── beam_grid.py
│   ├── beam_frame.py
│   ├── region.py
│   ├── floor_zone.py
│   ├── slab_by_label.py
│   └── exclusions.py
├── geometry/
│   └── segments.py
├── thickness/
│   └── parser.py
├── quantity/
│   └── slab.py
├── reasoning/
│   ├── __init__.py
│   ├── env.py
│   ├── deepseek_client.py
│   ├── context.py
│   └── slab_refinement.py
└── validation/
    └── overlay.py
```

## Scripts

- `run_pipeline.py` — main CLI (v3.3 semantic default)
- `build_atlas.py` — Epic 1 atlas builder
- `extract_docx.py` — extract Prompt_extracted.txt from docx
- `compare_to_ground_truth.py` — regression
- `analyze_dxf.py` — DXF audit helper
- `validate_ground_truth_totals.py`
- `generate_ground_truth_slabs.py`

## v3.3 modules (added)

- `src/sdie/semantic_pipeline.py`
- `src/sdie/atlas/`, `classification/`, `graph/`, `model/`, `confidence/`, `benchmark/`
- `src/sdie/api/`, `database/`
- `src/sdie/detection/slab_intelligence.py`
- `src/sdie/ingestion/entity_extractor.py`
- `data/atlas/component_atlas.json` (generated)

## Data

- `data/ground_truth/*.json` — all regression targets
- `data/audits/Inizio_B2_LayerTest1_audit.json`
- `data/audits/Slab-02_Terrace_audit.json`

## Data Source (full copy)

- `Data Source/Slab Test/Inizio_B2_LayerTest1.dxf`
- `Data Source/Slab Test/Slab-02_Terrace_LayerTest.dxf`
- `Data Source/Slab Test/Slab-02_FirstF_LayerTest.dxf`
- `Data Source/Slab Test/Slab -04 test 01_Layer_Test.dxf`
- `Data Source/Slab Test/Slab-02_Layer_Try.dxf`

## Docs

All files under `docs/` including `01`–`04` guides, `MODEL_DESIGN.md`, `Prompt_extracted.txt`, `SESSION_PROGRESS.md`.

## Tests

- `tests/test_floor_zone.py`

## Not copied

- `Output/Slab Test/*` (regenerate in V3)
- `.pytest_cache/`
- `Output/Slab Test/_tmp/`
- `Cursor AI Prompt – Phase 2 SDIE V2.docx`
- Most `data/audits/` except two key JSON audits
