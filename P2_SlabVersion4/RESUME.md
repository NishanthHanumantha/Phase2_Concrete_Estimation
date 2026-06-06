# Resume here — P2_SlabVersion4 (SDIE v4)

**Active project:** `P2_SlabVersion4/`  
**Spec (updated):** [docs/Prompt_extracted_V4.txt](docs/Prompt_extracted_V4.txt)  
**Flowchart:** [docs/SDIE_V4_Flowchart.html](docs/SDIE_V4_Flowchart.html)  
**Frozen:** V1, V2, V3 — do not edit for new work

**Last session:** June 2026 — Phase A (rules & layer profiles) in progress; slab test + overlay done.

---

## Quick start

```powershell
cd C:\Users\nishanth.h\Phase2_Concrete_Estimation\P2_SlabVersion4
$env:PYTHONPATH="src"

# Rebuild teach corpus (if needed)
python scripts/ingest_estimator_workbooks.py --build-atlas --fresh-atlas --build-kb
python scripts/build_layer_profiles.py

# Run test drawing
python scripts/run_pipeline.py "Data Source/TestInput/TrustOffice_FF_LayerTest_RAG.dxf" `
  -o "Output/TestOutput_V4_merged" --project-id TRUST_OFFICE --min-area 0.4

# Component classification eval (fast: column only ~3 min)
python scripts/evaluate_component_classification.py --tagged-only --baseline --drawing "Colum"

# Slab GT check
python scripts/verify_test_gt.py --results "Output/TestOutput_V4_merged/TrustOffice_FF_LayerTest_RAG_results.json"
```

DeepSeek: `DEEPSEEK_API_KEY` in `C:\Users\nishanth.h\Phase2_Concrete_Estimation\.env`

**Diagnostic overlay:** `Output/TestOutput_V4_merged/TrustOffice_FF_LayerTest_RAG_overlay.html`

---

## v4 architecture

```
Raw DXF → entities → rules + layer profiles → RAG/atlas → DeepSeek (ambiguous only)
  → graph → slab intelligence (bay merge) → quantities → validation overlay
```

**Four business calculators:** Slab, Beam, Column, Shear Wall (classified separately).

---

## What was completed this session

### Slab detection (Trust Office FF test)
- Estimator bay merge (`src/sdie/detection/bay_merge.py`)
- `min_slab_area_m2 = 0.4`, `merge_beam_grid_to_estimator_bays = true`
- **60 slabs, 560 m² (~99.5% of GT area)** vs 62 GT slabs

### Validation & overlay
- Diagnostic overlay: GT colors, layer toggles, click-to-inspect (`validation/overlay.py`)
- `validation/gt_match.py` — slab GT matching for overlay + `verify_test_gt.py`
- Auto TestGT Excel resolve for `*_LayerTest_RAG` drawings

### Component intelligence (Phase A — started)
- **Supervised atlas** from manifest `tagged_beam` / `tagged_column` / `tagged_shearwall`
- **Per-project layer profiles:** `data/layer_profiles.json` via `scripts/build_layer_profiles.py`
- **Rule stack:** hard layers, soft layers (`S_FRAMES`), geometry-first, atlas layer-index
- **Entity-level eval:** `scripts/evaluate_component_classification.py`
- **Docs:** `docs/Prompt_extracted_V4.txt` revised with implementation status

### Teach corpus (rebuilt)
- Atlas: **107,708 samples** (supervised labels on component-tagged DXFs)
- KB rebuilt with layer profiles

---

## Component classification metrics (latest)

| Eval | Accuracy | Notes |
|------|----------|--------|
| Column baseline (pre Phase A) | **9%** | Most predicted as Beam |
| Column Phase A (`component_eval_column_phaseA2.json`) | **56.3%** | P=100%, R=56.3% |
| Trust Office column file | Good | `S_FRAMES` profile works |
| Inizio column file | Weak | `S-BEAM`, `S-BEAM-IDEN`, `A-FLOR-IDEN` on column DXF |

**Not run yet:** beam tagged eval (`--drawing "Beam"`), shearwall eval, full `--tagged-only` (slow: 90k+ entities on shearwall DXF).

---

## Phase roadmap (agreed)

| Phase | Status | Action |
|-------|--------|--------|
| **A** Rules & layer profiles | **In progress** | Fix Inizio column rules → target ≥75% on tagged files |
| **B** Add 2 new project folders | Pending | After Phase A stabilizes |
| **C** DeepSeek re-teach | Pending | Only when ambiguous rate drops |

---

## Next steps when you resume

1. **Inizio column tuning** — hard-match `S-COLS`/`S-COL HATCH`; handle `S-BEAM-IDEN` on column-tagged drawing (1,168 Column→Beam errors)
2. **Beam eval:** `python scripts/evaluate_component_classification.py --tagged-only --baseline --drawing "Beam"`
3. **Optional:** graph-aware second pass for soft layers
4. **Phase B:** add Project4/5 to `projects_manifest.json`, re-ingest + profiles
5. **Commit** uncommitted work when ready (see git status below — not committed this session)

---

## Key paths

| Item | Path |
|------|------|
| Manifest | `Data Source/projects_manifest.json` |
| Layer profiles | `data/layer_profiles.json` |
| Atlas | `data/atlas/component_atlas.json` (~58 MB) |
| KB | `data/knowledge_base/structural_kb.json` |
| Test input | `Data Source/TestInput/TrustOffice_FF_LayerTest_RAG.dxf` |
| Test GT | `Data Source/Ground Truths/TestGT/TrustOffice_FF_ExpectedOutput.xlsx` |
| Column eval output | `Output/component_eval_column_phaseA2.json` |

---

## Estimator projects

| Project | ID | Folder |
|---------|-----|--------|
| Inizio | `INIZIO` | `Data Source/Project1 - Inizio/` |
| Trust Office | `TRUST_OFFICE` | `Data Source/Project2 - TrustOffice/` |
| Manohar | `MANOHAR` | `Data Source/Project3 - Manohar/` (0 entities — layer mismatch) |

Tagged teaching DXFs: beam, column, shearwall per project (see manifest).

---

## Epic status

| Epic | Status |
|------|--------|
| 1 Knowledge Base (RAG) | Done |
| 2 Atlas (+ supervised labels) | Done |
| 3 Classification (rules + DeepSeek) | In progress — 56% column recall |
| 4 Graph | Done |
| 5 Building model | Done |
| 6 Slab intelligence (+ bay merge) | Done (tuning edge bays) |
| 7 Quantity engine | Done |
| 8 Validation | Partial — overlay + eval scripts |

---

## Uncommitted changes (save point)

Modified/new under `P2_SlabVersion4/`: overlay, classifier, layer_profiles, component_gt/eval, gt_match, bay_merge (prior), ingest scripts, eval scripts, atlas, KB, Prompt_extracted_V4.txt, test outputs.

Run `git status` from repo root before commit.
