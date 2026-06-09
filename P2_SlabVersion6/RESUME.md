# P2_SlabVersion6 — resume checkpoint

**Last saved:** 2026-06-09

## What's working

- **Generic inference** — default `--project-id GENERIC`
- **Slab + beam quantities** — semantic pipeline, Excel export
- **Plan-copy dedup** — drops side-by-side duplicate bays/beams on wide consultant sheets
- **Tower min slab area** — 5 m² filter removes grid slivers
- **Overlay verification** — slab + beam ID labels, click-to-inspect sidebar
- **Web UI** — `scripts/start_web.bat` → http://127.0.0.1:8765

## Reference run (corrected)

| Input | Output | Slabs | Beams | Total m³ |
|-------|--------|-------|-------|----------|
| `Inizio_63F_Raw_Layer_Revised1.dxf` | `Output/Inizio_63F_Beam_Output/` | **15** / 280 m² | **134** / 128 m³ | **195** |

**Before dedup fix:** 49 slabs, 275 beams, 368 m³ (inflated by ~6 duplicate plan copies).

**Verify:** `Inizio_63F_Raw_Layer_Revised1_overlay.html` + `*_Beamquantities.xlsx`

## Quick commands

```powershell
cd P2_SlabVersion6
$env:PYTHONPATH="src"
python scripts/run_pipeline.py "Data Source/TestInput/Inizio_63F_Raw_Layer_Revised1.dxf" -o Output/Inizio_63F_Beam_Output
scripts\start_web.bat
```

**DeepSeek:** `DEEPSEEK_API_KEY` in repo root `.env`

## Pick up next

1. **Full raw INIZIO run** — `Revised Project Knowledge/Raw File/Inizio - Slab beam_Raw_Revised1.dxf`
2. **Layer alias normalization** — `STR-BEAM` ↔ `S-BEAM`
3. **Column/wall quantities**
4. **Per-beam mark linking** from `S-BEAM-IDEN`
5. **Update** `docs/Prompt_extracted_V6.txt`

## Key modules (latest changes)

- `src/sdie/detection/slab_intelligence.py` — `_dedupe_plan_copy_slabs`
- `src/sdie/quantity/beam.py` — `dedupe_plan_copy_beams`
- `src/sdie/validation/overlay.py` — beam labels + inspect list
- `src/sdie/config.py` — `tower_min_slab_area_m2`, `dedupe_plan_copies_x`
- `scripts/_inspect_slabs.py` — slab duplicate analysis helper
