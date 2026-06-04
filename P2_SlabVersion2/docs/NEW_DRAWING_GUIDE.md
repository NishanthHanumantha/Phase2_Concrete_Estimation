# SDIE — Testing a New Drawing

Quick guide for running the slab model on a consultant DXF not yet in the test set.

---

## 1. Prerequisites

```powershell
cd P2_SlabVersion1
pip install -r requirements.txt
$env:PYTHONPATH="src"
```

Optional LLM: set `DEEPSEEK_API_KEY` in `Phase2_Concrete_Estimation/.env`.

---

## 2. Identify drawing type

| Signal on plan | CLI `--layers` | Notes |
|----------------|----------------|--------|
| `S-BEAM` framing (Inizio-style) | `S-BEAM` | Beam-grid + *THK merge |
| `S_FRAMES` + `STR-CUTOUT` (Slab-02 family) | `S_FRAMES STR-CUTOUT` | Beam-grid; may have no *THK |
| `STR-BEAM` small tests | `STR-BEAM` | May fall back to beam_frame |

Check for **`*THK` MTEXT** on `A-FLOR-IDEN` — enables label-merge and cluster floor zone.

---

## 3. Run pipeline

```powershell
python scripts/run_pipeline.py "Data Source/Slab Test/YOUR_FILE.dxf" `
  -o "Output/Slab Test" `
  --mode auto `
  --layers S-BEAM `
  --min-area 0.4
```

Review:

- `Output/Slab Test/YOUR_FILE_results.json` → `totals`, `detection_notes`
- `Output/Slab Test/YOUR_FILE_overlay.html` → visual QA

---

## 4. Read `detection_notes`

| Field | Healthy sign |
|-------|----------------|
| `floor_zone.method` | `thk_cluster` or `frame_structure` |
| `thk_labels_in_floor` | Close to estimator slab count |
| `selected` | `label_merged_bay` when many *THK tags |
| `beam_grid_cell_count` | >> final slab count before merge |
| `label_merged_count` | ≈ physical slab / tag count |

If area is **>10% high**: stacked plan repeat — check `floor_zone.notes.grid_ymax_capped`.  
If count is **>> BOQ**: micro-bays — ensure label merge is on and exclusions apply.

---

## 5. Regression (optional)

Create `data/ground_truth/YOUR_FILE.json`:

```json
{
  "drawing_id": "YOUR_FILE",
  "expected_total": {
    "area_m2": 0.0,
    "concrete_m3": 0.0,
    "shuttering_m2": 0.0,
    "slab_count": 0
  },
  "regression_config": {
    "area_tolerance_pct": 5,
    "slab_count_tolerance": 20
  }
}
```

```powershell
python scripts/compare_to_ground_truth.py `
  "Output/Slab Test/YOUR_FILE_results.json" `
  data/ground_truth/YOUR_FILE.json
```

---

## 6. Overrides (rare)

| Need | Flag / config |
|------|----------------|
| Force one floor Y band | `PipelineConfig(floor_bounds_y=(ymin, ymax), floor_zone_mode="manual")` |
| Old floor band behaviour | `floor_zone_mode="legacy"` |
| LLM semantic pass | `--llm` |
| Finer bays | Lower `--min-area` (e.g. `0.4`) |

---

## 7. Architecture reminder

Per `Prompt_extracted.txt`:

- **Geometry** detects bays and computes m² / m³.
- **AI** only resolves ambiguity (voids, artifacts, naming).
- **Confidence** and evidence belong in JSON for engineer review.

See `docs/SESSION_PROGRESS.md` for full improvement history and Inizio B2 metrics.
