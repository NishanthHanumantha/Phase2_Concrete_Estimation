# P2_SlabVersion1 — Frozen baseline

**Status:** Complete through 2026-06-04  
**Next work:** `P2_SlabVersion2/` (clean copy of required assets only)

## Delivered in Version 1

- SDIE slab pipeline: beam grid, exclusions, THK label merge, cluster floor zone
- Optional DeepSeek refinement (`--llm`)
- Inizio B2 benchmark: 73 slabs, ~1935 m² (−0.4% vs BOQ)
- Documentation: `docs/01`–`04`, README, SESSION_PROGRESS, NEW_DRAWING_GUIDE

## Run (Version 1)

```powershell
cd P2_SlabVersion1
$env:PYTHONPATH="src"
python scripts/run_pipeline.py "Data Source/Slab Test/Inizio_B2_LayerTest1.dxf" -o "Output/Slab Test" --mode auto --layers S-BEAM --min-area 0.4
```

## Do not modify Version 1 for new experiments

Use **P2_SlabVersion2** for new drawings and model changes.
