"""Diagnose S43 bay geometry vs beam grid."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shapely import wkt
from shapely.geometry import box

from sdie.config import PipelineConfig
from sdie.detection.bay_merge import BayMergeParams, _GridCell, merge_raw_grid_cells
from sdie.detection.beam_grid import _collect_grid_axes
from sdie.detection.floor_zone import resolve_floor_zone
from sdie.ingestion.dxf_reader import load_drawing
from sdie.validation.gt_match import load_gt_xlsx

DXF = ROOT / "Data Source/TestInput/TrustOffice_FF_LayerTest_RAG.dxf"
RESULTS = ROOT / "Output/TestRun_V5_terrace/TrustOffice_FF_LayerTest_RAG_results.json"
S43 = next(s for s in load_gt_xlsx(ROOT / "Data Source/Ground Truths/TestGT/TrustOffice_FF_ExpectedOutput.xlsx") if s["id"] == "S43")

doc, meta = load_drawing(DXF)
msp = doc.modelspace()
config = PipelineConfig(structural_layers=("S_FRAMES", "STR-CUTOUT"))
floor_zone = resolve_floor_zone(msp, label_layers=config.floor_label_layers, frame_layers=config.structural_layers)
bounds_y = floor_zone.bounds_y if floor_zone else None
factor = meta.area_to_m2_factor
expand = 55.0

axes_y, axes_x = _collect_grid_axes(
    msp,
    config.structural_layers,
    min_horizontal_span_mm=config.grid_min_horizontal_span_mm,
    min_vertical_span_mm=config.grid_min_vertical_span_mm,
    axis_cluster_tol_mm=config.grid_axis_cluster_tol_mm,
    bounds_y=bounds_y,
)

print("S43 GT:", S43["area_m2"], "m2", S43["length_m"], "x", S43["breadth_m"])
print("floor_bounds_y:", bounds_y)
print(f"axes: {len(axes_x)} x {len(axes_y)}")

all_cells = []
for i in range(len(axes_x) - 1):
    for j in range(len(axes_y) - 1):
        xmin = axes_x[i] - expand
        xmax = axes_x[i + 1] + expand
        ymin = axes_y[j] - expand
        ymax = axes_y[j + 1] + expand
        w, h = xmax - xmin, ymax - ymin
        area = w * h * factor
        all_cells.append(_GridCell(i, j, xmin, xmax, ymin, ymax))
        if area >= 12:
            print(f"  cell i={i} j={j} w={w/1000:.2f} h={h/1000:.2f} area={area:.2f} y=[{ymin:.0f},{ymax:.0f}]")

params = BayMergeParams.infer_from_cells(all_cells, area_to_m2_factor=factor)
print("\nInferred merge limits:", params.max_merged_span_mm, params.max_merged_raw_area_m2)

merged, notes = merge_raw_grid_cells(all_cells, area_to_m2_factor=factor, params=params)
print("Merge:", notes)

# cells that could combine to ~27m2
print("\nMerged cells area 15-35:")
for c in merged:
    a = c.raw_area_m2(factor)
    if a >= 15:
        print(f"  i={c.i} j={c.j} w={c.width_mm()/1000:.2f} h={c.height_mm()/1000:.2f} area={a:.2f}")

r = json.loads(RESULTS.read_text(encoding="utf-8"))
# find slab ~18.6 near y=19000
for s in r["slabs"]:
    cy = s.get("centroid_cm", [0, 0])[1]
    if 18000 < cy < 20000:
        print(f"\nModel {s['slab_id']}: {s['area_m2']:.3f} m2 centroid={s['centroid_cm']} bounds={s.get('bounds_cm')}")
