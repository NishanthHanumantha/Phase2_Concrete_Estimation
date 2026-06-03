# Phase2 Concrete Estimation

Structural Drawing Intelligence Engine (SDIE) — Phase 2 slab quantity MVP from consultant DXF drawings.

## Project

All application code, test drawings, and run outputs live under:

**[`P2_SlabVersion1/`](P2_SlabVersion1/)**

- Design: `P2_SlabVersion1/docs/MODEL_DESIGN.md`
- Resume checkpoint: `P2_SlabVersion1/docs/SESSION_PROGRESS.md`
- Run pipeline: `P2_SlabVersion1/scripts/run_pipeline.py`

## Quick start

```powershell
cd P2_SlabVersion1
pip install -r requirements.txt
python scripts/run_pipeline.py "Data Source/Slab Test/Slab-02_Terrace_LayerTest.dxf" -o "Output/Slab Test" --mode auto --layers S_FRAMES STR-CUTOUT --min-area 0.4
```

## Repository

https://github.com/NishanthHanumantha/Phase2_Concrete_Estimation
