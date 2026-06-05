# New Drawing Guide — SDIE v3.3

How to process a new consultant DXF with the semantic component intelligence pipeline.

---

## 1. Place the DXF

Copy into:
```
P2_SlabVersion3/Data Source/Slab Test/<your_drawing>.dxf
```

---

## 2. Build or extend the Component Atlas (recommended)

If the drawing has tagged layers (beam, column, slab THK), add samples:

```powershell
cd P2_SlabVersion3
$env:PYTHONPATH="src"
python scripts/build_atlas.py "Data Source/Slab Test/<your_drawing>.dxf" --merge
```

This improves classification on future similar drawings.

---

## 3. Identify layers

Run audit helper:
```powershell
python scripts/analyze_dxf.py "Data Source/Slab Test/<your_drawing>.dxf"
```

Typical Inizio layers:
| Role | Layer examples |
|------|----------------|
| Beam frame | `S-BEAM`, `S_FRAMES` |
| Column | `S-COLS`, `S-COL HATCH` |
| Slab THK tags | `A-FLOR-IDEN` |
| Beam labels | `S-BEAM-IDEN` |
| Notes | `G-ANNO-TEXT` |

---

## 4. Run semantic pipeline (default)

```powershell
python scripts/run_pipeline.py "Data Source/Slab Test/<your_drawing>.dxf" `
  -o "Output/Slab Test" `
  --mode auto `
  --layers S-BEAM `
  --min-area 0.4
```

Optional flags:
| Flag | When to use |
|------|-------------|
| `--component-llm` | Many ambiguous / untagged entities |
| `--llm` | Suspected void bays still counted as slabs |
| `--legacy-geometry` | Compare against old geometry-first behaviour |

---

## 5. Review outputs

| File | Check |
|------|-------|
| `*_overlay.html` | Blue = slabs; verify stairs/lifts/columns excluded |
| `*_results.json` → `detection_notes.component_type_counts` | Beam/column/core counts sensible |
| `*_building_model.json` | Components and graph relationships |
| `*_results.json` → `benchmark` | Accuracy vs ground truth (if JSON exists) |

---

## 6. Add ground truth (if you have estimator BOQ)

Create `data/ground_truth/<stem>.json`:

```json
{
  "drawing": "<your_drawing>.dxf",
  "expected_total": {
    "slab_count": 73,
    "area_m2": 1943.3,
    "concrete_m3": 410.8,
    "shuttering_m2": 1943.3
  },
  "regression_config": {
    "area_tolerance_pct": 3,
    "slab_count_tolerance": 2
  }
}
```

Compare:
```powershell
python scripts/compare_to_ground_truth.py `
  "Output/Slab Test/<stem>_results.json" `
  data/ground_truth/<stem>.json
```

---

## 7. Tuning (if needed)

Edit only under `P2_SlabVersion3/src/sdie/`:

| Symptom | Where to tune |
|---------|---------------|
| Wrong component types | `classification/classifier.py`, `features.py` |
| Cores not excluded | `detection/slab_intelligence.py` buffer sizes |
| Wrong floor band | `config.py` `floor_zone_mode`, `floor_bounds_y` |
| Slab count off | `slab_by_label.py`, `min_thk_labels_for_merge` |

**Do not** patch slab detection without improving classification first (v3.3 directive).

---

## 8. API alternative

```powershell
$env:PYTHONPATH="src"
uvicorn sdie.api.app:app --reload
```

POST `/drawings/process` with JSON body (`dxf_path`, `layers`, `min_area`).
