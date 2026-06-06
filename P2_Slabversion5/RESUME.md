# Resume — P2_SlabVersion5

**Purpose:** Lean fork of V4 for major model changes. Full history in `../P2_SlabVersion4/RESUME.md`.

## Quick run

```powershell
cd C:\Users\nishanth.h\Phase2_Concrete_Estimation\P2_SlabVersion5
$env:PYTHONPATH="src"
python scripts/run_pipeline.py "Data Source/TestInput/TrustOffice_FF_LayerTest_RAG.dxf" `
  -o "Output/TestRun" --project-id TRUST_OFFICE --layers S_FRAMES STR-CUTOUT --min-area 0.4
```

## Carried from V4

- Bay merge, min_area 0.4, diagnostic overlay, supervised atlas, layer profiles
- Phase A column eval: **56.3%** recall (Trust Office OK; Inizio column file weak)

## Next work (V5)

1. Major model changes (user intent for V5 fork)
2. Phase A: Inizio column rules
3. Phase B/C: new projects + DeepSeek re-teach

## Teach DXFs

Not in V5 by default — copy `Data Source/Project*` from V4 before `teach_all_projects.py`.
