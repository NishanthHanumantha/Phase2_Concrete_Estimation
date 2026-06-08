from __future__ import annotations

import re

import numpy as np
from shapely.geometry import Point, box

from sdie.detection.exclusions import (
    ExclusionCatalog,
    build_exclusion_catalog,
    parse_beam_half_width_mm,
)
from sdie.thickness.parser import parse_text_content
from sdie.detection.bay_merge import BayMergeParams, _GridCell, merge_raw_grid_cells
from sdie.detection.region import SlabCandidate

BEAM_TAG_RE = re.compile(r"\(?\s*(\d+)\s*[xX]\s*(\d+)\s*\)?", re.I)
VOID_KEYWORDS = (
    "STAIRCASE",
    "STAIR",
    "LIFT",
    "RAMP",
    "OHT",
    "TANK",
    "HEADROOM",
    "SHAFT",
    "CORE",
    "PLANTER",
)


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


def _void_skip_radius_mm(text: str, default_radius_mm: float) -> float:
    upper = text.upper()
    if "RAMP" in upper:
        return max(default_radius_mm, 2800.0)
    if any(k in upper for k in ("STAIRCASE", "STAIR", "LIFT", "CORE", "SHAFT")):
        return max(default_radius_mm, 3500.0)
    return default_radius_mm


def _collect_void_points(
    msp,
    annotation_layers: tuple[str, ...],
    default_radius_mm: float,
) -> list[tuple[float, float, float]]:
    points: list[tuple[float, float, float]] = []
    for entity in msp:
        if entity.dxf.layer not in annotation_layers:
            continue
        if entity.dxftype() not in ("TEXT", "MTEXT"):
            continue
        text = parse_text_content(entity)
        if any(keyword in text.upper() for keyword in VOID_KEYWORDS):
            r = _void_skip_radius_mm(text, default_radius_mm)
            points.append((entity.dxf.insert.x, entity.dxf.insert.y, r))
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


def _line_in_y_band(
    y1: float,
    y2: float,
    bounds_y: tuple[float, float] | None,
) -> bool:
    """True when the segment intersects the Y band (not only when centroid is inside)."""
    if bounds_y is None:
        return True
    ymin, ymax = bounds_y
    lo, hi = (y1, y2) if y1 <= y2 else (y2, y1)
    return hi >= ymin and lo <= ymax


def _vertical_overlap_in_band(
    y1: float,
    y2: float,
    bounds_y: tuple[float, float] | None,
) -> float:
    if bounds_y is None:
        return abs(y2 - y1)
    ymin, ymax = bounds_y
    lo, hi = (y1, y2) if y1 <= y2 else (y2, y1)
    return max(0.0, min(hi, ymax) - max(lo, ymin))


def _augment_horizontal_axes(
    axes_y: list[float],
    bounds_y: tuple[float, float] | None,
) -> list[float]:
    """Sparse podium grids: add band edges so beam-grid cells can form."""
    if bounds_y is None or len(axes_y) >= 2:
        return axes_y
    ymin, ymax = bounds_y
    return sorted({ymin, ymax, *axes_y})


def _augment_vertical_axes(
    axes_x: list[float],
    bounds_y: tuple[float, float] | None,
) -> list[float]:
    """Sparse podium grids: ensure at least two vertical axes from band extent."""
    if bounds_y is None or len(axes_x) >= 2:
        return axes_x
    if not axes_x:
        return axes_x
    xmin, xmax = min(axes_x), max(axes_x)
    if xmax - xmin < 400.0:
        pad = 2000.0
        return sorted({xmin - pad, xmax + pad, *axes_x})
    return sorted({xmin, xmax, *axes_x})


def _cluster_axis_groups(
    axes: list[float],
    gap_threshold_mm: float,
) -> list[list[float]]:
    if not axes:
        return []
    xs = sorted(axes)
    groups: list[list[float]] = [[xs[0]]]
    for value in xs[1:]:
        if value - groups[-1][-1] > gap_threshold_mm:
            groups.append([value])
        else:
            groups[-1].append(value)
    return groups


def _horizontal_beam_score_in_band(
    msp,
    frame_layers: tuple[str, ...],
    bounds_y: tuple[float, float],
    x_cluster: list[float],
    *,
    min_horizontal_span_mm: float,
) -> int:
    xmin, xmax = min(x_cluster), max(x_cluster)
    score = 0
    for entity in msp:
        if entity.dxf.layer not in frame_layers:
            continue
        if entity.dxftype() != "LINE":
            continue
        x1, y1 = entity.dxf.start.x, entity.dxf.start.y
        x2, y2 = entity.dxf.end.x, entity.dxf.end.y
        if abs(y2 - y1) >= 50:
            continue
        if abs(x2 - x1) < min_horizontal_span_mm:
            continue
        if not _line_in_y_band(y1, y2, bounds_y):
            continue
        cx = (x1 + x2) / 2.0
        if xmin - 1500.0 <= cx <= xmax + 1500.0:
            score += 1
    return score


def _select_primary_vertical_axis_cluster(
    axes_x: list[float],
    msp,
    frame_layers: tuple[str, ...],
    bounds_y: tuple[float, float] | None,
    *,
    gap_threshold_mm: float,
    min_horizontal_span_mm: float,
) -> list[float]:
    """Drop duplicate plan copies — keep the X cluster with most podium framing."""
    groups = _cluster_axis_groups(axes_x, gap_threshold_mm)
    if len(groups) <= 1 or bounds_y is None:
        return axes_x
    best = max(
        groups,
        key=lambda cluster: _horizontal_beam_score_in_band(
            msp,
            frame_layers,
            bounds_y,
            cluster,
            min_horizontal_span_mm=min_horizontal_span_mm,
        ),
    )
    return best


def bay_polygon_for_point(
    x: float,
    y: float,
    axes_x: list[float],
    axes_y: list[float],
    expand_mm: float,
):
    if len(axes_x) < 2 or len(axes_y) < 2:
        return None
    xs = sorted(axes_x)
    ys = sorted(axes_y)
    x0 = x1 = None
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            x0, x1 = xs[i], xs[i + 1]
            break
    if x0 is None:
        x0, x1 = (xs[0], xs[1]) if x <= xs[0] else (xs[-2], xs[-1])
    y0 = y1 = None
    for j in range(len(ys) - 1):
        if ys[j] <= y <= ys[j + 1]:
            y0, y1 = ys[j], ys[j + 1]
            break
    if y0 is None:
        y0, y1 = (ys[0], ys[1]) if y <= ys[0] else (ys[-2], ys[-1])
    return box(x0 - expand_mm, y0 - expand_mm, x1 + expand_mm, y1 + expand_mm)


def _collect_grid_axes(
    msp,
    frame_layers: tuple[str, ...],
    *,
    min_horizontal_span_mm: float,
    min_vertical_span_mm: float,
    axis_cluster_tol_mm: float,
    bounds_y: tuple[float, float] | None = None,
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
        if not _line_in_y_band(y1, y2, bounds_y):
            continue
        if abs(y2 - y1) < 50 and abs(x2 - x1) >= min_horizontal_span_mm:
            horizontal_y.append((y1 + y2) / 2.0)
        elif abs(x2 - x1) < 50:
            vertical_reach = _vertical_overlap_in_band(y1, y2, bounds_y)
            if vertical_reach >= min_vertical_span_mm:
                vertical_x.append((x1 + x2) / 2.0)

    axes_x = _cluster_axis(vertical_x, axis_cluster_tol_mm)
    if bounds_y is None:
        axes_x = _split_vertical_axes(axes_x, gap_threshold_mm=1500.0)
    axes_y = _cluster_axis(horizontal_y, axis_cluster_tol_mm)
    return axes_y, axes_x


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
    bounds_y: tuple[float, float] | None = None,
    augment_sparse_grid_axes: bool = False,
    exclusions: ExclusionCatalog | None = None,
    apply_exclusions: bool = True,
    merge_to_estimator_bays: bool = False,
    bay_merge_params: BayMergeParams | None = None,
    out_notes: dict | None = None,
) -> list[SlabCandidate]:
    """
    Strategy B: orthogonal beam centerline grid → slab bays between axes.

    Non-slab area (beams, columns, walls, stairs, lifts, ramps, label boxes)
    is removed via :class:`ExclusionCatalog` per MODEL_DESIGN / Prompt_extracted.
    """
    axes_y, axes_x = _collect_grid_axes(
        msp,
        frame_layers,
        min_horizontal_span_mm=min_horizontal_span_mm,
        min_vertical_span_mm=min_vertical_span_mm,
        axis_cluster_tol_mm=axis_cluster_tol_mm,
        bounds_y=bounds_y,
    )
    if augment_sparse_grid_axes:
        axes_y = _augment_horizontal_axes(axes_y, bounds_y)
        if bounds_y is not None:
            axes_x = _select_primary_vertical_axis_cluster(
                axes_x,
                msp,
                frame_layers,
                bounds_y,
                gap_threshold_mm=axis_cluster_tol_mm * 5.0,
                min_horizontal_span_mm=min_horizontal_span_mm,
            )
        axes_x = _augment_vertical_axes(axes_x, bounds_y)
    if len(axes_x) < 2 or len(axes_y) < 2:
        return []

    if slab_face_expand_mm is None:
        expand = parse_beam_half_width_mm(msp, annotation_layers) / 7.0
    else:
        expand = slab_face_expand_mm

    if apply_exclusions and exclusions is None:
        exclusions = build_exclusion_catalog(
            msp,
            bounds_y=bounds_y,
            beam_layers=(),
            annotation_layers=annotation_layers,
            area_to_m2_factor=area_to_m2_factor,
        )

    void_points = _collect_void_points(
        msp, annotation_layers, void_label_radius_mm
    )

    raw_cells: list[_GridCell] = []
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
            raw_cells.append(_GridCell(i=i, j=j, xmin=xmin, xmax=xmax, ymin=ymin, ymax=ymax))

    if out_notes is not None:
        out_notes["raw_grid_cell_count"] = len(raw_cells)
        out_notes["merge_to_estimator_bays"] = merge_to_estimator_bays

    merge_notes: dict | None = None
    if merge_to_estimator_bays and len(raw_cells) > 1:
        merge_params = BayMergeParams.infer_from_cells(
            raw_cells,
            area_to_m2_factor=area_to_m2_factor,
            min_slab_area_m2=min_area_m2,
        )
        if bay_merge_params is not None:
            merge_params.small_bay_preserve_max_m2 = (
                bay_merge_params.small_bay_preserve_max_m2
            )
            merge_params.min_area_ratio_for_merge = (
                bay_merge_params.min_area_ratio_for_merge
            )
            merge_params.compact_bay_span_ratio = bay_merge_params.compact_bay_span_ratio
            # Keep infer_from_cells span/area caps unless caller explicitly tuned them.
            if not merge_params.auto_inferred:
                merge_params.partial_raw_area_m2 = bay_merge_params.partial_raw_area_m2
                merge_params.max_merged_raw_area_m2 = bay_merge_params.max_merged_raw_area_m2
                merge_params.max_merged_span_mm = bay_merge_params.max_merged_span_mm
        raw_cells, merge_notes = merge_raw_grid_cells(
            raw_cells,
            area_to_m2_factor=area_to_m2_factor,
            params=merge_params,
        )
        if out_notes is not None:
            out_notes["estimator_bay_merge"] = merge_notes

    candidates: list[SlabCandidate] = []
    idx = 0
    for cell in raw_cells:
        raw_poly = box(cell.xmin, cell.ymin, cell.xmax, cell.ymax)
        if apply_exclusions and exclusions is not None:
            poly = exclusions.difference(raw_poly, area_to_m2_factor)
            if poly is None:
                continue
        else:
            poly = raw_poly

        area_m2 = poly.area * area_to_m2_factor
        if area_m2 < min_area_m2:
            continue

        centroid = poly.centroid
        if bounds_y is not None:
            ymin_b, ymax_b = bounds_y
            if not (ymin_b <= centroid.y <= ymax_b):
                continue
        if void_points:
            near_void = any(
                Point(vx, vy).distance(centroid) < radius
                for vx, vy, radius in void_points
            )
            if near_void:
                continue

        idx += 1
        strategy = (
            "beam_grid_bay_merged" if merge_to_estimator_bays else "beam_grid_bay"
        )
        candidates.append(
            SlabCandidate(
                slab_id=f"{id_prefix}-{idx:03d}",
                polygon_wkt=poly.wkt,
                area_m2=round(area_m2, 6),
                centroid_cm=[round(centroid.x, 3), round(centroid.y, 3)],
                bounds_cm=[round(v, 1) for v in poly.bounds],
                strategy=strategy,
            )
        )

    if merge_notes is not None:
        for cand in candidates:
            cand.strategy = "beam_grid_bay_merged"

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
