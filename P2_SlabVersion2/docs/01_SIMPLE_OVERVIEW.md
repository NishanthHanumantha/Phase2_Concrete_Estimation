# SDIE — Simple Overview

**What is this?**  
**SDIE** (Structural Drawing Intelligence Engine) reads a structural consultant’s **DXF drawing** and estimates **slab quantities** the way an engineer would: slab area, concrete volume, and shuttering area — without needing ready-made slab polygons in CAD.

**What it is not:** A generic AI that guesses numbers. All **math is done by code** from geometry. AI (DeepSeek) is **optional** and only helps decide “is this bay really a slab?”

---

## The problem we solve

Consultant drawings often have:

- Beam lines, not closed slab outlines  
- Many `200 THK` / `275 THK` tags instead of one slab polyline per pour  
- Stairs, lifts, columns, and **several floors drawn on one sheet** (stacked vertically)  
- No cleanup before quantity takeoff  

SDIE turns that into **one polygon per physical slab** (or per THK tag on the floor) and sums area × thickness.

---

## How an engineer would do it (and how SDIE maps)

| Engineer step | What SDIE does |
|---------------|----------------|
| Open the right floor on the sheet | **Floor zone** — finds the Y-band for this floor from `*THK` labels and beam lines |
| Ignore stairs, lifts, columns | **Exclusions** — subtracts columns, sunk slabs; skips void labels (STAIR, LIFT, …) |
| Find slab between beams | **Beam grid** — builds bays between horizontal/vertical beam centerlines |
| One slab per THK tag on plan | **Label merge** — groups small grid cells under each `A-FLOR-IDEN` tag |
| Read 200 mm / 275 mm | **Thickness** — nearest `*THK` to each slab; else default note (e.g. “ALL SLABS 200mm”) |
| Calculate m² and m³ | **Quantity engine** — area from polygons; volume = area × thickness |
| Check on drawing | **Overlay** — blue = slab, red = excluded zones (HTML pan/zoom) |

---

## Main outputs

After you run:

```powershell
python scripts/run_pipeline.py "your.dxf" -o "Output/Slab Test" --mode auto --layers S-BEAM --min-area 0.4
```

you get:

| File | Purpose |
|------|---------|
| `*_results.json` | Every slab: area, thickness, concrete, polygon, how it was detected |
| `*_summary.txt` | Human-readable totals |
| `*_overlay.html` | Visual check in the browser |
| `*_overlay.svg` | Same view for reports |

---

## When detection strategy changes

**Auto mode** picks the best approach:

1. **Beam grid** (most common on Inizio / Slab-02 style) — many orthogonal beam lines → grid of bays.  
2. **Region** — rare small closed loops on the framing layer.  
3. **Beam frame** — fallback single bounding box if nothing else works.

On **Inizio B2**, the winning path is: beam grid → exclusions → **merge by THK label** → ~73 slabs, ~1943 m².

---

## Optional AI (`--llm`)

- Sends a **summary** of detected slabs and void text to **DeepSeek**.  
- Model returns: which slabs to drop (e.g. tiny label boxes, void-adjacent).  
- Code applies that list; **never** lets the model compute area.  
- Default production run: **no LLM** — faster and matches BOQ on Inizio.

---

## Limits (honest)

- One **floor band per run** on multi-storey sheets.  
- Drawings **without** `*THK` tags use frame-line bounds (e.g. Terrace) — less accurate.  
- Slab **count** follows THK tags; estimator may group bays differently.  
- **Concrete** can be a few % off if many bays are 275 mm vs estimator average.

---

## Read next

| Document | Content |
|----------|---------|
| [02_ARCHITECTURE.md](./02_ARCHITECTURE.md) | Modules, layers, data structures |
| [03_PIPELINE_FLOW.md](./03_PIPELINE_FLOW.md) | Flowcharts (Mermaid) |
| [NEW_DRAWING_GUIDE.md](./NEW_DRAWING_GUIDE.md) | Run on a new DXF |
| [SESSION_PROGRESS.md](./SESSION_PROGRESS.md) | History and benchmark numbers |
