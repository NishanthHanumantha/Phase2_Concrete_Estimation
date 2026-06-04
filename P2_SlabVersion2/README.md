# P2_SlabVersion2 — SDIE Slab Intelligence

Active development copy. **Frozen baseline:** `../P2_SlabVersion1/` (see `VERSION1_COMPLETE.md` there).

## What was imported from Version 1

| Included | Excluded (stay in V1 only) |
|----------|----------------------------|
| `src/sdie/` full package | `Output/` generated files |
| `scripts/*.py` | `.pytest_cache/`, `_tmp/` |
| `docs/` (all guides) | Large audit dumps (selected audits copied) |
| `data/ground_truth/` | |
| `tests/test_floor_zone.py` | |
| `requirements.txt` | |
| `Data Source/Slab Test/*.dxf` | |

See [MANIFEST.md](./MANIFEST.md) for the full file list.

## Setup

```powershell
cd P2_SlabVersion2
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

## Version 2 focus

- New consultant drawings
- Generic model improvements
- Do not edit `P2_SlabVersion1` for new experiments
