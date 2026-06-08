# P2_SlabVersion6 — resume checkpoint

**Forked from:** `P2_Slabversion5` @ `b3ee8c0`  
**Date:** 2026-06-06  
**Focus:** Drawing-driven layer discovery (V6)

## Done in this folder

- Lean copy of V5 source, data, scripts, tests, two test DXFs
- `layer_discovery.py` — scan entities per layer, project-profile boost, auto frame/annotation split
- `run_pipeline.py` — `--auto-layers` / `--no-auto-layers`, optional `--layers` override
- Pipeline writes `layer_discovery` notes to results JSON

## Next experiments

- Tune frame scoring for terrace / multi-copy sheets
- Layer-table + block-reference inheritance
- Compare V6 auto-layers vs V5 manual `--layers` on Inizio + Trust Office GT

## Quick run

```powershell
cd P2_SlabVersion6
$env:PYTHONPATH="src"
python scripts/run_pipeline.py "Data Source/TestInput/Inizio_B2_LayerTest_V5.dxf" -o Output/Inizio_TestOutput --project-id INIZIO --no-deepseek
```
