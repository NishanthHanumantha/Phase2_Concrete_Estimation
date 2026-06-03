from __future__ import annotations

import re

import numpy as np
from shapely.geometry import Point, box

from sdie.detection.region import SlabCandidate

BEAM_TAG_RE = re.compile(r"\((\d+)\s*[xX]\s*(\d+)\)", re.I)
VOID_KEYWORDS = ("STAIRCASE", "LIFT", "RAMP", "OHT", "TANK", "HEADROOM")


def _cluster_axis(values: list[float], tolerance_mm: float) -> list[float]:
    if not values:
        return []
    sorted_vals = sorted(values)
    groups: list[list[float]] = [[sorted_vals[0]]]
    for value in sorted_vals[1:]:
        if value - groups[-1][-1] <= tolerance_mm:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [sum(group) / len(group) for group in groups]


def _parse_beam_width_mm(msp, annotation_layers: tuple[str, ...]) -> float:
    widths: list[float] = []
    for entity in msp:
        if entity.dxf.layer not in annotation_layers:
            continue
        if entity.dxftype() != "TEXT":
            continue
        match = BEAM_TAG_RE.search((entity.dxf.text or "").strip())
        if match:
            widths.append(float(match.group(1)))
    if not widths:
        return 300.0
    return float(np.median(widths))


def _collect_void_points(msp, annotation_layers: tuple[str, ...]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for entity in msp:
        if entity.dxf.layer not in annotation_layers:
            continue
        if entity.dxftype() != "TEXT":
            continue
        text = (entity.dxf.text or "").upper()
        if any(keyword in text for keyword in VOID_KEYWORDS):
            points.append((entity.dxf.insert.x, entity.dxf.insert.y))
    return points


def _split_vertical_axes(axes_x: list[float], gap_threshold_mm: float) -> list[float]:
    if len(axes_x) < 2:
        return axes_x
    x = np.array(axes_x)
    gaps = np.diff(x)
    gap_idx = int(np.argmax(gaps))
    if float(gaps[gap_idx]) < gap_threshold_mm:
        return axes_x
    split_x = (x[gap_idx] + x[gap_idx + 1]) / 2.0
    return [value for value in axes_x if value <= split_x]


def _collect_grid_axes(
    msp,
    frame_layers: tuple[str, ...],
    *,
    min_horizontal_span_mm: float,
    min_vertical_span_mm: float,
    axis_cluster_tol_mm: float,
) -> tuple[list[float], list[float]]:
    horizontal_y: list[float] = []
    vertical_x: list[float] = []

    for entity in msp:
        if entity.dxf.layer not in frame_layers:
            continue
        if entity.dxftype() != "LINE":
            continue
        x1, y1 = entity.dxf.start.x, entity.dxf.start.y
        x2, y2 = entity.dxf.end.x, entity.dxf.end.y
        if abs(y2 - y1) < 50 and abs(x2 - x1) >= min_horizontal_span_mm:
            horizontal_y.append((y1 + y2) / 2.0)
        elif abs(x2 - x1) < 50 and abs(y2 - y1) >= min_vertical_span_mm:
            vertical_x.append((x1 + x2) / 2.0)

    return (
        _cluster_axis(horizontal_y, axis_cluster_tol_mm),
        _split_vertical_axes(
            _cluster_axis(vertical_x, axis_cluster_tol_mm),
            gap_threshold_mm=1500.0,
        ),
    )


def detect_beam_grid_slabs(
    msp,
    *,
    frame_layers: tuple[str, ...],
    annotation_layers: tuple[str, ...],
    area_to_m2_factor: float,
    min_area_m2: float,
    id_prefix: str = "SLAB",
    min_horizontal_span_mm: float = 3000.0,
    min_vertical_span_mm: float = 2000.0,
    axis_cluster_tol_mm: float = 300.0,
    slab_face_expand_mm: float | None = None,
    void_label_radius_mm: float = 2000.0,
    min_cell_side_mm: float = 400.0,
) -> list[SlabCandidate]:
    """
    Strategy B: orthogonal beam centerline grid → one slab bay per cell.

    Cells expand outward to approximate clear span between beam faces.
    Bays whose centroid falls near STAIRCASE / LIFT / similar labels are skipped.
    """
    axes_y, axes_x = _collect_grid_axes(
        msp,
        frame_layers,
        min_horizontal_span_mm=min_horizontal_span_mm,
        min_vertical_span_mm=min_vertical_span_mm,
        axis_cluster_tol_mm=axis_cluster_tol_mm,
    )
    if len(axes_x) < 2 or len(axes_y) < 2:
        return []

    expand = slab_face_expand_mm
    if expand is None:
        beam_width = _parse_beam_width_mm(msp, annotation_layers)
        expand = max(25.0, beam_width / 6.0)

    void_points = _collect_void_points(msp, annotation_layers)
    candidates: list[SlabCandidate] = []
    idx = 0

    for i in range(len(axes_x) - 1):
        for j in range(len(axes_y) - 1):
            xmin = axes_x[i] - expand
            xmax = axes_x[i + 1] + expand
            ymin = axes_y[j] - expand
            ymax = axes_y[j + 1] + expand
            width = xmax - xmin
            height = ymax - ymin
            if width < min_cell_side_mm or height < min_cell_side_mm:
                continue

            poly = box(xmin, ymin, xmax, ymax)
            area_m2 = poly.area * area_to_m2_factor
            if area_m2 < min_area_m2:
                continue

            centroid = poly.centroid
            if void_points:
                near_void = any(
                    Point(vx, vy).distance(centroid) < void_label_radius_mm
                    for vx, vy in void_points
                )
                if near_void:
                    continue

            idx += 1
            candidates.append(
                SlabCandidate(
                    slab_id=f"{id_prefix}-{idx:03d}",
                    polygon_wkt=poly.wkt,
                    area_m2=round(area_m2, 6),
                    centroid_cm=[round(centroid.x, 3), round(centroid.y, 3)],
                    bounds_cm=[round(v, 1) for v in poly.bounds],
                    strategy="beam_grid_bay",
                )
            )

    return candidates


def count_orthogonal_frame_lines(msp, frame_layers: tuple[str, ...]) -> tuple[int, int]:
    """Return (horizontal_line_count, vertical_line_count) on frame layers."""
    horizontal = 0
    vertical = 0
    for entity in msp:
        if entity.dxf.layer not in frame_layers:
            continue
        if entity.dxftype() != "LINE":
            continue
        x1, y1 = entity.dxf.start.x, entity.dxf.start.y
        x2, y2 = entity.dxf.end.x, entity.dxf.end.y
        if abs(y2 - y1) < 50:
            horizontal += 1
        elif abs(x2 - x1) < 50:
            vertical += 1
    return horizontal, vertical
