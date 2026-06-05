# SDIE v3.3 — Simple Overview

**What is this?**  
**SDIE** (Structural Drawing Intelligence Engine) reads structural **DXF** drawings and produces **BOQ-quality slab quantities** — but v3.3 does it differently from earlier versions.

**The big change in v3.3:** The engine first **understands structural components** (beams, columns, walls, cores) before it decides what is a slab. Semantics come first; geometry-based quantities second.

---

## The problem we solve

Consultant drawings mix beams, columns, stairs, lifts, and slab tags on one sheet. A geometry-only engine can treat beam bays and voids as slabs. v3.3 classifies each structural primitive, builds a **semantic building model**, then estimates slabs only in the **remaining framed regions**.

---

## v3.3 pipeline in plain language

| Step | What happens |
|------|----------------|
| 1. Read DXF | Load drawing, units, floor zone |
| 2. Extract entities | Lines, polylines, hatches, text |
| 3. Classify components | Beam, Column, Wall, Core, Slab tag, Opening, … |
| 4. Build structural graph | Column supports beam; beam frames slab |
| 5. Semantic building model | JSON export of floors, components, relationships |
| 6. Slab intelligence | Exclude classified non-slab regions; find slab bays |
| 7. Quantities | Area × thickness (code only — never LLM math) |
| 8. Benchmark | Compare to estimator workbook; target 95% accuracy |

---

## Main outputs

```powershell
cd P2_SlabVersion3
$env:PYTHONPATH="src"
python scripts/run_pipeline.py "Data Source/Slab Test/Inizio_B2_LayerTest1.dxf" `
  -o "Output/Slab Test" --mode auto --layers S-BEAM --min-area 0.4
```

| File | Purpose |
|------|---------|
| `*_results.json` | Slabs, totals, component counts, benchmark |
| `*_building_model.json` | Semantic building model (v3.3) |
| `*_overlay.html` | Visual check — blue slabs, red exclusions |
| `*_summary.txt` | Human-readable totals |

---

## Building the Component Atlas (one-time setup)

From tagged drawings:

```powershell
python scripts/build_atlas.py "Data Source/Slab Test/Inizio_B2_LayerTest1.dxf" --merge
```

Creates `data/atlas/component_atlas.json` — used to improve classification on future drawings.

---

## Optional AI

| Flag | Purpose |
|------|---------|
| `--component-llm` | DeepSeek classifies ambiguous components |
| `--llm` | DeepSeek filters doubtful slab bays (legacy refinement) |
| `--legacy-geometry` | Disable v3.3; use old geometry-first pipeline |

AI never calculates area or concrete volume.

---

## Limits (honest)

- React Validation UI (Epic 7) and full PostgreSQL deployment are scaffolded, not production UI yet.  
- One floor band per run on multi-storey sheets.  
- 95% benchmark target requires ground truth JSON per drawing.

---

## Read next

1. [02_ARCHITECTURE.md](./02_ARCHITECTURE.md) — technical design  
2. [03_PIPELINE_FLOW.md](./03_PIPELINE_FLOW.md) — flowcharts  
3. [NEW_DRAWING_GUIDE.md](./NEW_DRAWING_GUIDE.md) — new DXF workflow
