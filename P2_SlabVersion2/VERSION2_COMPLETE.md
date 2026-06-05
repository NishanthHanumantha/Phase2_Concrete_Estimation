# P2_SlabVersion2 — Frozen baseline

**Status:** Complete through 2026-06-04  
**Next work:** `P2_SlabVersion3/` (clean copy of required assets only)

## Delivered in Version 2

- Same SDIE slab pipeline as V1 (beam grid, exclusions, THK label merge, cluster floor zone)
- Optional DeepSeek refinement (`--llm`)
- Inizio B2 benchmark verified: 73 slabs, ~1935 m² (−0.4% vs BOQ)
- Resume checkpoint and verification outputs in `Output/Slab Test/`

## Run (Version 2)

```powershell
cd P2_SlabVersion2
$env:PYTHONPATH="src"
python scripts/run_pipeline.py "Data Source/Slab Test/Inizio_B2_LayerTest1.dxf" -o "Output/Slab Test" --mode auto --layers S-BEAM --min-area 0.4
```

## Do not modify Version 2 for new experiments

Use **P2_SlabVersion3** for new drawings and model changes.
