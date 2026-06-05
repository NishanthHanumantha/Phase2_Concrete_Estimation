# P2_SlabVersion3 — SDIE v3.3 (Frozen)

**Frozen baseline** (`VERSION3_COMPLETE.md`). **Active development:** `../P2_SlabVersion4/`.  
Also frozen: `../P2_SlabVersion1/`, `../P2_SlabVersion2/`.

## What was imported from Version 2

| Included | Excluded (stay in V2 only) |
|----------|----------------------------|
| `src/sdie/` full package | `Output/` generated files |
| `scripts/*.py` | `.pytest_cache/`, `_tmp/` |
| `docs/` (all guides) | Cursor prompt `.docx` |
| `data/ground_truth/` | |
| `data/audits/` (key JSON audits) | |
| `tests/test_floor_zone.py` | |
| `requirements.txt` | |
| `Data Source/Slab Test/*.dxf` | |

See [MANIFEST.md](./MANIFEST.md) for the full file list.

## Setup

```powershell
cd P2_SlabVersion3
pip install -r requirements.txt
$env:PYTHONPATH="src"
```

DeepSeek (optional): `DEEPSEEK_API_KEY` in `../.env` at repo root.

## Run

```powershell
python scripts/run_pipeline.py "Data Source/Slab Test/Inizio_B2_LayerTest1.dxf" `
  -o "Output/Slab Test" --mode auto --layers S-BEAM --min-area 0.4
```

## Documentation

Start at [docs/README.md](./docs/README.md).

## v3.3 pipeline (default)

```powershell
python scripts/build_atlas.py "Data Source/Slab Test/Inizio_B2_LayerTest1.dxf" --merge
python scripts/run_pipeline.py "Data Source/Slab Test/Inizio_B2_LayerTest1.dxf" `
  -o "Output/Slab Test" --mode auto --layers S-BEAM --min-area 0.4
```

Outputs include `*_building_model.json` and `benchmark` section in results.

Use `--legacy-geometry` to run the pre-v3.3 geometry-first pipeline.

## Version 3 focus

- Structural component classification → semantic building model → slab quantities
- Do not edit `P2_SlabVersion1` or `P2_SlabVersion2` for new experiments
