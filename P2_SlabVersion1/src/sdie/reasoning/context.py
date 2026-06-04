from __future__ import annotations

import math
from typing import Any

from sdie.detection.exclusions import NON_SLAB_TEXT_KEYWORDS
from sdie.detection.region import SlabCandidate
from sdie.thickness.parser import ThicknessLabel, parse_text_content


def _labels_in_band(
    labels: list[ThicknessLabel],
    bounds_y: tuple[float, float] | None,
) -> list[ThicknessLabel]:
    if bounds_y is None:
        return labels
    ymin, ymax = bounds_y
    return [lb for lb in labels if ymin <= lb.xy_cm[1] <= ymax]


def _nearest_label_index(
    cx: float, cy: float, labels: list[ThicknessLabel]
) -> int:
    return min(
        range(len(labels)),
        key=lambda i: math.hypot(cx - labels[i].xy_cm[0], cy - labels[i].xy_cm[1]),
    )


def collect_void_annotations(
    msp,
    annotation_layers: tuple[str, ...],
    bounds_y: tuple[float, float] | None,
) -> list[dict[str, Any]]:
    """TEXT/MTEXT that indicate non-slab zones (stairs, lifts, ramps, etc.)."""
    out: list[dict[str, Any]] = []
    ymin, ymax = (bounds_y or (None, None))
    for entity in msp:
        if entity.dxf.layer not in annotation_layers:
            continue
        if entity.dxftype() not in ("TEXT", "MTEXT"):
            continue
        text = parse_text_content(entity).upper()
        if not any(kw in text for kw in NON_SLAB_TEXT_KEYWORDS):
            continue
        y = entity.dxf.insert.y
        if bounds_y is not None and not (ymin <= y <= ymax):
            continue
        out.append(
            {
                "text": text[:120],
                "x_mm": round(entity.dxf.insert.x, 1),
                "y_mm": round(y, 1),
                "layer": entity.dxf.layer,
            }
        )
    return out[:80]


def summarize_layers(msp, max_layers: int = 40) -> list[dict[str, int]]:
    counts: dict[str, int] = {}
    for entity in msp:
        layer = entity.dxf.layer
        counts[layer] = counts.get(layer, 0) + 1
    ranked = sorted(counts.items(), key=lambda x: -x[1])[:max_layers]
    return [{"layer": k, "entities": v} for k, v in ranked]


def build_slab_reasoning_context(
    *,
    drawing_name: str,
    structural_layers: tuple[str, ...],
    frame_line_count: dict[str, int],
    floor_bounds_y: tuple[float, float] | None,
    thk_labels: list[ThicknessLabel],
    grid_cells: list[SlabCandidate],
    merged_slabs: list[SlabCandidate] | None,
    void_annotations: list[dict[str, Any]],
    layer_summary: list[dict[str, int]],
    exclusion_area_m2: float | None,
    geometric_notes: dict[str, Any],
) -> dict[str, Any]:
    labels_floor = _labels_in_band(thk_labels, floor_bounds_y)
    label_rows = [
        {
            "idx": i,
            "thk_mm": lb.value_mm,
            "text": lb.text[:40],
            "x_mm": round(lb.xy_cm[0], 1),
            "y_mm": round(lb.xy_cm[1], 1),
        }
        for i, lb in enumerate(labels_floor)
    ]

    cell_rows: list[dict[str, Any]] = []
    for i, cell in enumerate(grid_cells):
        cx, cy = cell.centroid_cm
        li = _nearest_label_index(cx, cy, labels_floor) if labels_floor else -1
        cell_rows.append(
            {
                "cell_id": f"G-{i + 1:03d}",
                "area_m2": round(cell.area_m2, 3),
                "x_mm": round(cx, 1),
                "y_mm": round(cy, 1),
                "nearest_label_idx": li,
                "slab_id": cell.slab_id,
            }
        )

    merged_rows = []
    if merged_slabs:
        for s in merged_slabs:
            merged_rows.append(
                {
                    "slab_id": s.slab_id,
                    "area_m2": round(s.area_m2, 3),
                    "thk_mm": s.thickness_mm,
                    "x_mm": round(s.centroid_cm[0], 1),
                    "y_mm": round(s.centroid_cm[1], 1),
                }
            )

    return {
        "drawing": drawing_name,
        "structural_layers": list(structural_layers),
        "frame_lines": frame_line_count,
        "floor_bounds_y_mm": (
            [round(v, 1) for v in floor_bounds_y] if floor_bounds_y else None
        ),
        "thk_label_count_floor": len(labels_floor),
        "thk_labels": label_rows,
        "void_annotations": void_annotations,
        "top_layers": layer_summary[:25],
        "exclusion_area_m2": exclusion_area_m2,
        "grid_cell_count": len(grid_cells),
        "grid_cells": cell_rows,
        "merged_slabs_preview": merged_rows,
        "geometric_pipeline": geometric_notes,
        "rules": {
            "one_slab_per_thk_tag": True,
            "exclude": [
                "beams",
                "columns",
                "structural walls",
                "walls",
                "stairs",
                "lifts",
                "ramps",
                "sunk slab",
                "label boxes",
            ],
            "quantity_math": "forbidden_for_llm",
        },
    }
