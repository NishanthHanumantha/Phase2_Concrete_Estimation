# P2_SlabVersion2 — SDIE Slab Intelligence

**Frozen baseline** (see `VERSION2_COMPLETE.md`). **Active development:** `../P2_SlabVersion3/`. Also frozen: `../P2_SlabVersion1/` (`VERSION1_COMPLETE.md`).

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

## Version 2 status

Frozen as of 2026-06-04. Use **P2_SlabVersion3** for new drawings and model changes.
