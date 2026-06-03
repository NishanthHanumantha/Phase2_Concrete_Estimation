# SDIE Model Design — Phase 2 Slab (Locked for MVP)

**Project:** Structural Drawing Intelligence Engine (SDIE)  
**Benchmark drawing:** `Data Source/Slab Test/Slab-02_Layer_Try.dxf`  
**Status:** Draft v0.1 — engineer validation required on ground truth  
**Reference:** `docs/Prompt.docx`

---

## 1. Purpose

SDIE interprets **raw consultant DXF** drawings and produces **explainable slab quantities**:

- Slab area (m²)
- Concrete volume (m³)
- Shuttering area (m²)

Quantities are always computed by deterministic code from the **Semantic Building Model**. AI (DeepSeek) resolves ambiguity only; it never calculates quantities.

---

## 2. Golden benchmark: `Slab-02_Layer_Try.dxf`

### 2.1 Drawing profile (auto-audit)

| Property | Value |
|----------|--------|
| DXF version | AC1032 |
| Drawing units (`$INSUNITS`) | **4 = centimetres** |
| Length in engine | Store as **mm** internally (`cm × 10`) |
| Area | cm² in DXF → convert to **m²** (`area_cm2 / 10_000`) |
| Scale note | `SCALE 1:100` on `G-ANNO-TEXT` |
| Title (primary MVP floor) | **LOWER GROUND FLOOR FRAMING LAYOUT** (+102.0M LVL) |

**Important:** This file contains **five stacked floor layouts** in one model space (separated by Y). MVP processes **one floor at a time**, starting with **LGF**.

### 2.2 Floor zones (multi-panel layout)

| Floor ID | Title | Approx. heading Y | Default slab note |
|----------|--------|-------------------|-------------------|
| `LGF` | Lower Ground Floor | ~858 | ALL SLABS 200mm U.N.O |
| `GF` | Ground Floor | ~−27,211 | ALL SLABS 150mm U.N.O |
| `FF` | First Floor | ~−55,600 | ALL SLABS 150mm U.N.O |
| `TF` | Terrace Floor | ~−89,734 | ALL SLABS 150mm U.N.O |
| `SHR` | Staircase headroom & OHT | ~−131,795 | ALL SLABS 150mm U.N.O |

Zone splitter: detect `S-HEADING` TEXT entities → assign entities to nearest floor by Y.

### 2.3 Layer signals (do not hard-depend on names)

| Layer | Role in MVP | Entity mix |
|-------|-------------|------------|
| `S_FRAMES` | Beam/column frame — **slab boundary source** | 1123 LINE, 370 LWPOLYLINE |
| `S-BEAM-IDEN` | Beam labels, **local THK** tags, room names | 625 TEXT |
| `STR-CUTOUT` | Opening / cutout linework | 206 LINE |
| `S-COLS` | Column footprints | LWPOLYLINE |
| `S-SUNKEN HATCH` | Sunken slab zones | HATCH |
| `G-ANNO-TEXT` | General notes (default thickness) | MTEXT |

There are **no dedicated slab polylines** — validates Prompt requirement; primary strategy is **beam-framed bay detection (Strategy B)**, not closed slab polygons.

### 2.4 Thickness rules (deterministic)

**Priority (highest wins):**

1. Local `*THK` TEXT on `S-BEAM-IDEN` within **5 m** of slab centroid (configurable `thickness_label_radius_m`)
2. Floor-specific general note (`ALL SLABS ARE ###mm THK. U.N.O`)
3. Project default in ground truth (fallback only)

**LGF local overrides detected:** `125THK`, `150THK`, `175THK`, `200THK` (13 labels in plan region).

**Parse patterns:** `(\d+)\s*THK`, `(\d+)\s*mm\s*THK`, note regex `ALL SLABS ARE (\d+)mm`.

### 2.5 Voids and non-slab zones (LGF)

Labels found on drawing (engineer confirms polygons):

| Type | Labels | Action |
|------|--------|--------|
| Stair | `STAIRCASE` (×2 on LGF region) | Deduct from slab area |
| Lift | `LIFT PIT`, `LIFT` | Deduct |
| Planter | `PLANTER` (×3) | Deduct or tag non-structural |
| Ramp | `RAMP`, `SLOPE IN 1:12` | Separate treatment (not flat slab) |
| Cutout linework | `STR-CUTOUT` | Use as opening boundary where closed |

---

## 3. Semantic Building Model (schema)

```text
DrawingRun
├── source_file, units, scale, processed_at
├── floors[]
│   ├── floor_id, name, elevation_text, bounds_xy
│   ├── default_thickness_mm, thickness_source
│   ├── slabs[]
│   │   ├── slab_id, polygon_wkt, area_m2
│   │   ├── thickness_mm, thickness_confidence, thickness_evidence[]
│   │   ├── openings[] (polygon, type)
│   │   └── quantities { concrete_m3, shuttering_m2, trace }
│   └── notes[] (raw text, parsed thickness)
└── audit { strategies_used, consensus_scores }
```

**Slab polygon sources (enum):** `region`, `beam_frame`, `grid`, `topology`, `engineer_override`.

---

## 4. Detection model (consensus)

| Strategy | Use on Slab-02 | Weight (MVP) |
|----------|----------------|--------------|
| A — Closed region | Secondary (small beam-pocket polygons only) | 0.15 |
| **B — Beam-frame bays** | **Primary** — build graph from `S_FRAMES` | **0.50** |
| C — Grid reconstruction | If grid lines detected | 0.20 |
| D — Topology | Fallback for gaps | 0.15 |

**Consensus:** IoU overlap between candidate polygons → cluster → pick representative per cluster → score by strategy weight × closure quality × annotation proximity.

**Beams:** Extract centerlines/edges from `S_FRAMES` + beam tags `PB\d+` for topology only. **No beam BOQ.**

---

## 5. Quantity engine (deterministic)

| Output | Formula |
|--------|---------|
| `area_m2` | Shapely polygon area after void deduction |
| `concrete_m3` | `area_m2 × (thickness_mm / 1000)` |
| `shuttering_m2` | `area_m2` (soffit only, MVP) — edge formwork deferred |

Every quantity record:

```json
{
  "value": 0.0,
  "unit": "m3",
  "confidence": 0.0,
  "evidence": ["note:ALL SLABS 200mm", "label:175THK@747279,26522"],
  "trace": "area_m2=1234.5; thickness_mm=200; volume=246.9"
}
```

---

## 6. AI boundary (DeepSeek)

**Allowed:** thickness disambiguation, conflicting notes, slab naming.  
**Forbidden:** area, volume, shuttering math.

**Trigger:** `thickness_confidence < 0.60` or conflicting general vs local labels.

**Response contract:**

```json
{
  "proposal": "200",
  "unit": "mm",
  "evidence": ["MTEXT handle ...", "TEXT 175THK near bay 3"],
  "confidence": 0.82
}
```

---

## 7. Confidence thresholds

| Score | Action |
|-------|--------|
| ≥ 0.85 | Auto-accept quantity |
| 0.60 – 0.84 | Flag for engineer review in UI |
| < 0.60 | Block export; require confirmation |

---

## 8. MVP scope (build order)

**In scope (Slab-02 LGF only):**

1. DXF ingestion → normalized model  
2. Floor zone split (5 floors; run LGF first)  
3. Strategy B slab detection + STR-CUTOUT openings  
4. Thickness engine (note + local THK)  
5. Quantity engine + JSON export  
6. SVG overlay (slabs, thickness, voids, confidence)

**Out of scope for MVP:**

- DeepSeek integration  
- React UI (CLI + SVG first)  
- GF / FF / TF / SHR floors (after LGF passes regression)  
- Beam quantity  
- DWG / PDF ingestion  

---

## 9. Regression metrics (vs ground truth)

Ground truth file: `data/ground_truth/Slab-02_Layer_Try.json`

| Metric | MVP target (LGF) |
|--------|------------------|
| Slab area | ±3% vs engineer `expected_total.area_m2` |
| Thickness | 100% match on tagged bays; default note elsewhere |
| Concrete m³ | ±3% (derived from area × thickness) |
| Shuttering m² | ±3% (soffit = area, MVP) |
| Runtime | < 60 s per floor on dev machine |

---

## 10. Repository layout

```text
P2_SlabVersion1/
├── docs/
│   ├── Prompt.docx
│   └── MODEL_DESIGN.md          ← this file
├── Data Source/Slab Test/
│   └── Slab-02_Layer_Try.dxf
├── data/
│   ├── audits/                  ← machine DXF audits
│   └── ground_truth/            ← engineer-validated truth
├── scripts/
│   └── analyze_dxf.py
└── src/sdie/                    ← implementation (next step)
```

---

## 11. Engineer actions required

1. Open `Slab-02_Layer_Try.dxf` → confirm **LGF bounds** in ground truth.  
2. Fill `expected_total` for LGF (area, concrete, shuttering) from your manual BOQ.  
3. Mark each `slabs[]` entry: `is_slab`, `thickness_mm`, or merge bays into fewer polygons.  
4. Set `validation_status` to `approved` when ready for regression.  

After approval, implementation starts at `src/sdie/ingestion`.

---

## 12. Decisions log

| # | Decision | Choice |
|---|----------|--------|
| D1 | Internal length unit | mm (convert from cm DXF) |
| D2 | Slab definition | Beam-bounded bay polygon (Strategy B) |
| D3 | Thickness fallback | Floor general note → user prompt if missing |
| D4 | Opening deduction | Yes — stairs, lift pit, cutouts |
| D5 | Shuttering MVP | Soffit area = net slab area |
| D6 | Multi-floor DXF | Split by `S-HEADING`; process per floor |
| D7 | First implementation floor | **LGF** |

---

*Audit artifacts: `data/audits/Slab-02_Layer_Try_audit.json`, `data/audits/Slab-02_LGF_candidates.json`*
