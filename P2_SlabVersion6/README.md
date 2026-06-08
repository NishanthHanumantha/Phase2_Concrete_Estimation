# P2_SlabVersion6 — SDIE v6 Layer-Aware Pipeline

Lean fork of **P2_Slabversion5** with **drawing-driven layer discovery** instead of hard-coded `--layers` defaults.

## V6 change: how layers are read

| V5 | V6 |
|----|-----|
| CLI `--layers S_FRAMES STR-CUTOUT` (wrong for Inizio `S-BEAM` sheets) | **`--auto-layers`** (default): scan modelspace + boost from `layer_profiles.json` |
| Fixed `annotation_layers` in config | Text/IDEN/FLOR layers picked from entities present in the DXF |
| Same list used for classify + grid + exclusions | **`frame_layers`**: top 1–2 line-heavy structural layers for beam-grid / floor zone |

Override framing when needed:

```powershell
python scripts/run_pipeline.py drawing.dxf -o Output/Run --layers S-BEAM --no-auto-layers
```

Inspect discovery without a full run:

```powershell
python scripts/analyze_dxf.py "Data Source/TestInput/Inizio_B2_LayerTest_V5.dxf" --project-id INIZIO
```

## What is included

Same lean bundle as V5 — see `MANIFEST.md`. No generated `Output/` runs copied from V5.

## Setup

```powershell
cd C:\Users\nishanth.h\Phase2_Concrete_Estimation\P2_SlabVersion6
pip install -r requirements.txt
$env:PYTHONPATH="src"
```

## Run (auto layers)

**Inizio** — discovers `S-BEAM` automatically:

```powershell
python scripts/run_pipeline.py `
  "Data Source/TestInput/Inizio_B2_LayerTest_V5.dxf" `
  -o "Output/Inizio_TestOutput" `
  --project-id INIZIO --min-area 0.4 --no-deepseek
```

**Trust Office**:

```powershell
python scripts/run_pipeline.py `
  "Data Source/TestInput/TrustOffice_FF_LayerTest_RAG.dxf" `
  -o "Output/TestRun" `
  --project-id TRUST_OFFICE --min-area 0.4 --no-deepseek
```

Check `layer_discovery` in `*_results.json` for resolved layer sets.

## Prompt / spec

| File | Purpose |
|------|---------|
| `docs/Prompt_extracted_V6.txt` | **Active** — V5 docx + V5/V6 + Revised Inizio Project Knowledge |
| `Revised Project Knowledge/` | INIZIO teach (Tagged files) + raw inference input |
| `docs/Prompt_extracted_V5_docx.txt` | Verbatim extraction from the V5 Word spec |
| `docs/Prompt_extracted_V4.txt` | V4 archive |
| `SDIE Version 5 – DeepSeek Structural Reasoning Engine.docx` | Source document |

## Parent versions

- **V5:** `../P2_Slabversion5` — frozen checkpoint (podium + shear-wall exclusions)
- **V6 (this):** layer discovery experiments
