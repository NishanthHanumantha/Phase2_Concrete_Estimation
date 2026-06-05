# SDIE v3.3 Model Design

**Project:** Inizio Structural Component Intelligence Engine  
**Version:** 3.3.0  
**Status:** Active — semantics-first architecture  
**Reference:** `docs/Prompt_extracted.txt`, `SDIE v3.3 Enterprise Implementation Package`

---

## 1. Purpose

SDIE v3.3 interprets raw consultant DXF and produces:

1. **Structural component classification** (Beam, Column, Wall, Core, Slab, Opening, …)  
2. **Semantic building model** (floors, components, relationships)  
3. **Slab quantities** (area, concrete, shuttering) — only after steps 1–2  

Quantities are always computed by deterministic code. DeepSeek resolves classification ambiguity only.

---

## 2. Architecture directive

> Do not improve slab detection directly. Build Structural Component Intelligence first.

Implementation order (Epics 1–7):

| Epic | Module | Acceptance |
|------|--------|------------|
| 1 Atlas Builder | `atlas/` | Tagged DXF → atlas samples |
| 2 Classifier | `classification/` | Component type + confidence |
| 3 Graph | `graph/` | NetworkX relationships |
| 4 Building Model | `model/` | JSON export |
| 5 Slab Intelligence | `detection/slab_intelligence.py` | Non-slab excluded before bays |
| 6 Quantity | `quantity/` | 95% concrete accuracy target |
| 7 Validation UI | `api/` + future React | Human review scaffold |

---

## 3. Component Atlas schema

```json
{
  "sample_id": "Inizio_B2_ENT-00042",
  "project_id": "INIZIO",
  "component_type": "Beam",
  "geometry_features": {"length_mm": 5200, "aspect_ratio": 12.5},
  "annotation_features": {"has_beam_tag": true},
  "graph_features": {},
  "source_drawing": "Inizio_B2_LayerTest1.dxf",
  "confidence": 0.85
}
```

Storage: `data/atlas/component_atlas.json` (PostgreSQL `atlas_samples` table for production).

---

## 4. Classifier design

**Inputs:** geometry, topology, layer metadata, annotation text, graph features, atlas lookup  
**Output:** `{ "component": "Beam", "confidence": 0.96 }`  
**Target:** 95%+ on tagged regression set  

Feature groups (Part 5):
- Beam: length, aspect ratio, connectivity  
- Column: compact polygon, grid proximity  
- Wall: continuity, thickness proxy  
- Slab: THK annotation, beam enclosure (via graph)

---

## 5. Structural graph

Node types: Slab, Beam, Column, Wall, Core  
Relationships: supports, frames, touches, contains, adjacent  
Library: NetworkX (GNN-ready export in `graph_features`)

---

## 6. Slab Intelligence (replaces geometry-first detection)

**Old:** DXF → grid → THK merge → quantity  
**New:**

1. Classify Beam / Column / Wall / Core / Opening  
2. Build semantic exclusions from classified components  
3. Beam grid + THK merge on remaining framed regions  
4. Quantity  

Strategies: `semantic_label_merged_bay`, `semantic_beam_grid_bay`

---

## 7. Confidence framework

```
final = 0.35×geometry + 0.25×topology + 0.20×graph + 0.20×deepseek
```

Range 0–100% on each `ClassifiedComponent`.

---

## 8. DeepSeek boundaries

| Allowed | Forbidden |
|---------|-----------|
| Component classification | Area calculation |
| Ambiguity resolution | Volume calculation |
| Missing annotation reasoning | Quantity estimation |

Output schema: `{ "classification": "", "confidence": 0.0, "evidence": [] }`

---

## 9. Benchmark framework

**Source:** Estimator workbook → `data/ground_truth/*.json`  
**Metrics:** area, thickness, concrete, shuttering accuracy  
**Target:** 95%+  
**Report:** `benchmark` section in `*_results.json`

---

## 10. Benchmark drawings

| Drawing | Ground truth | Notes |
|---------|--------------|-------|
| Inizio_B2_LayerTest1 | `data/ground_truth/Inizio_B2_LayerTest1.json` | Primary regression — 73 slabs |
| Slab-02_Terrace | `data/ground_truth/Slab-02_Terrace_LayerTest.json` | Terrace / fewer THK tags |
| Slab-02_Layer_Try | `data/ground_truth/Slab-02_Layer_Try.json` | Multi-floor LGF benchmark |

---

## 11. API & database (enterprise scaffold)

**FastAPI** (`sdie/api/app.py`):
- `GET /health`
- `POST /drawings/process`
- `GET /buildings/{stem}`

**Database** (`sdie/database/models.py`):
- SQLite default: `data/sdie_v33.db`
- PostgreSQL via `SDIE_DATABASE_URL`

**React UI (Part 14):** Planned — Project Dashboard, Drawing Viewer, Component Explorer, Atlas Manager, Validation Center, Benchmark Reports.

---

## 12. Legacy compatibility

`--legacy-geometry` runs the v2 geometry-first `pipeline.py` body for A/B comparison. Default is semantic v3.3.
