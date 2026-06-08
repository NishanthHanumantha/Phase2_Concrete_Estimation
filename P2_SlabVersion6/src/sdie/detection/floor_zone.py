from __future__ import annotations

import re
from dataclasses import dataclass, field

from ezdxf.entities import DXFEntity

from sdie.thickness.parser import parse_text_content

FLOOR_TITLE_RE = re.compile(
    r"BASEMENT\s*[-\s]*0?2|B\s*[-\s]*2\s*FLOOR|BASEMENT\s*02|"
    r"TERRACE|FIRST\s*FLOOR|L\.?G\.?F\.?|GROUND\s*FLOOR|"
    r"(\d+)\s*(?:ST|ND|RD|TH)\s*FLOOR",
    re.I,
)
THK_RE = re.compile(r"(\d+)\s*THK", re.I)


@dataclass
class LabelCluster:
    y_min: float
    y_max: float
    count: int
    indices: list[int] = field(default_factory=list)


@dataclass
class FloorZone:
    """Active floor band for slab takeoff on multi-stack DXF sheets."""

    bounds_y: tuple[float, float] | None
    method: str
    label_count: int = 0
    cluster_count: int = 0
    included_satellite_clusters: int = 0
    label_bounds_y: tuple[float, float] | None = None
    notes: dict = field(default_factory=dict)

    @property
    def thk_filter_bounds_y(self) -> tuple[float, float] | None:
        return self.label_bounds_y or self.bounds_y


def _label_positions(msp, layers: tuple[str, ...]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for entity in msp:
        if entity.dxf.layer not in layers:
            continue
        if entity.dxftype() not in ("TEXT", "MTEXT"):
            continue
        text = parse_text_content(entity).upper()
        if not THK_RE.search(text):
            continue
        points.append((entity.dxf.insert.x, entity.dxf.insert.y))
    return points


def _cluster_labels_by_y(
    ys: list[float],
    *,
    gap_mm: float,
) -> list[LabelCluster]:
    if not ys:
        return []
    order = sorted(range(len(ys)), key=lambda i: ys[i])
    sorted_y = [ys[i] for i in order]
    groups: list[list[int]] = [[order[0]]]
    for k in range(1, len(sorted_y)):
        if sorted_y[k] - sorted_y[k - 1] > gap_mm:
            groups.append([order[k]])
        else:
            groups[-1].append(order[k])
    clusters: list[LabelCluster] = []
    for g in groups:
        gy = [ys[i] for i in g]
        clusters.append(
            LabelCluster(
                y_min=min(gy),
                y_max=max(gy),
                count=len(g),
                indices=g,
            )
        )
    return clusters


def _count_frame_lines_in_band(
    msp,
    frame_layers: tuple[str, ...],
    ymin: float,
    ymax: float,
) -> tuple[int, int]:
    horizontal = 0
    vertical = 0
    for entity in msp:
        if entity.dxf.layer not in frame_layers:
            continue
        if entity.dxftype() != "LINE":
            continue
        y1, y2 = entity.dxf.start.y, entity.dxf.end.y
        cy = (y1 + y2) / 2.0
        if not (ymin <= cy <= ymax):
            continue
        x1, x2 = entity.dxf.start.x, entity.dxf.end.x
        if abs(y2 - y1) < 50 and abs(x2 - x1) >= 3000:
            horizontal += 1
        elif abs(x2 - x1) < 50 and abs(y2 - y1) >= 2000:
            vertical += 1
    return horizontal, vertical


def _split_cluster_subpanels(
    ys_in_cluster: list[float],
    *,
    internal_gap_mm: float,
) -> list[tuple[float, float, int]]:
    """Split one Y-cluster at large internal gaps (stacked plans on one sheet)."""
    if len(ys_in_cluster) < 3:
        y0, y1 = min(ys_in_cluster), max(ys_in_cluster)
        return [(y0, y1, len(ys_in_cluster))]
    sorted_y = sorted(ys_in_cluster)
    groups: list[list[float]] = [[sorted_y[0]]]
    for y in sorted_y[1:]:
        if y - groups[-1][-1] > internal_gap_mm:
            groups.append([y])
        else:
            groups[-1].append(y)
    return [(min(g), max(g), len(g)) for g in groups]


def _cap_grid_ymax_for_stacked_plan(
    primary_ys: list[float],
    default_ymax: float,
    internal_gap_mm: float,
    margin_mm: float,
) -> float:
    """
    On multi-tier consultant sheets, drop the upper repeated plan copy.

    Finds a large Y-gap in the upper label band and caps the grid below its lower tier.
    """
    ys = sorted(primary_ys)
    if len(ys) < 4:
        return default_ymax
    p75 = ys[int(len(ys) * 0.75)]
    best: tuple[float, float, float] | None = None
    for i in range(len(ys) - 1):
        ylo, yhi = ys[i], ys[i + 1]
        gap = yhi - ylo
        if gap < internal_gap_mm * 0.9:
            continue
        if yhi < p75:
            continue
        if best is None or gap > best[0]:
            best = (gap, ylo, yhi)
    if best is None:
        return default_ymax
    _gap, ylo, _yhi = best
    capped = ylo - margin_mm * 0.08
    return min(default_ymax, max(ys[0], capped))


def _pick_best_subpanel(
    subpanels: list[tuple[float, float, int]],
    msp,
    frame_layers: tuple[str, ...],
    margin_mm: float,
) -> tuple[float, float, int]:
    best_score = -1.0
    best = subpanels[0]
    for ymin, ymax, n in subpanels:
        h, v = _count_frame_lines_in_band(
            msp,
            frame_layers,
            ymin - margin_mm,
            ymax + margin_mm,
        )
        score = n * 15.0 + h + v * 0.5
        if score > best_score:
            best_score = score
            best = (ymin, ymax, n)
    return best


def _internal_subpanel_gap_mm(ys: list[float], floor_gap_mm: float) -> float:
    if len(ys) < 3:
        return floor_gap_mm
    sorted_y = sorted(ys)
    gaps = [sorted_y[i + 1] - sorted_y[i] for i in range(len(sorted_y) - 1)]
    gaps = [g for g in gaps if g > 800]
    if not gaps:
        return floor_gap_mm
    gaps.sort()
    p90 = gaps[int(len(gaps) * 0.9)]
    return max(4200.0, min(p90, 8000.0))


def _adaptive_gap_mm(ys: list[float], base_gap_mm: float) -> float:
    if len(ys) < 2:
        return base_gap_mm
    sorted_y = sorted(ys)
    gaps = [sorted_y[i + 1] - sorted_y[i] for i in range(len(sorted_y) - 1)]
    gaps = [g for g in gaps if g > 500]
    if not gaps:
        return base_gap_mm
    median_gap = sorted(gaps)[len(gaps) // 2]
    return max(base_gap_mm, median_gap * 2.5)


def infer_bounds_from_thk_clusters(
    msp,
    label_layers: tuple[str, ...],
    *,
    frame_layers: tuple[str, ...] = (),
    gap_mm: float = 6000.0,
    margin_mm: float = 5000.0,
    satellite_max_count: int = 8,
    satellite_ratio: float = 0.12,
) -> FloorZone | None:
    """
    Pick the dominant *THK label Y-cluster and include small satellite clusters
    on the same sheet (e.g. mezzanine tags above a low band).
    """
    points = _label_positions(msp, label_layers)
    if len(points) < 5:
        return None

    ys = [p[1] for p in points]
    gap = _adaptive_gap_mm(ys, gap_mm)
    clusters = _cluster_labels_by_y(ys, gap_mm=gap)
    if not clusters:
        return None

    scored: list[tuple[float, int]] = []
    for i, cl in enumerate(clusters):
        ymin, ymax = cl.y_min, cl.y_max
        h, v = (0, 0)
        if frame_layers:
            h, v = _count_frame_lines_in_band(msp, frame_layers, ymin, ymax)
        score = cl.count * 20.0 + h + v * 0.5
        scored.append((score, i))

    primary_i = max(scored, key=lambda x: x[0])[1]
    primary = clusters[primary_i]
    primary_ys = [ys[i] for i in primary.indices]

    label_ymin, label_ymax = primary.y_min, primary.y_max
    satellites = 0
    thresh = max(satellite_max_count, int(primary.count * satellite_ratio))

    for i, cl in enumerate(clusters):
        if i == primary_i:
            continue
        if cl.count <= thresh:
            # Small clusters far below the primary band are separate floor stacks
            # (e.g. Basement-03 tags under Basement-02 on Inizio sheets), not satellites.
            if cl.y_max < primary.y_min - gap * 0.35:
                continue
            label_ymin = min(label_ymin, cl.y_min)
            label_ymax = max(label_ymax, cl.y_max)
            satellites += 1

    label_bounds = (label_ymin - margin_mm, label_ymax + margin_mm)

    internal_gap = _internal_subpanel_gap_mm(primary_ys, gap)
    subpanels = _split_cluster_subpanels(primary_ys, internal_gap_mm=internal_gap)
    if len(subpanels) > 1 and frame_layers:
        py0, py1, pn = _pick_best_subpanel(subpanels, msp, frame_layers, margin_mm)
        grid_ymax = _cap_grid_ymax_for_stacked_plan(
            primary_ys,
            py1 + margin_mm,
            internal_gap,
            margin_mm,
        )
        grid_bounds = (label_bounds[0], grid_ymax)
        subpanel_note = {
            "subpanels": len(subpanels),
            "selected_subpanel_labels": pn,
            "internal_gap_mm": round(internal_gap, 1),
            "grid_ymax_capped": round(grid_ymax, 1),
        }
    else:
        grid_ymax = _cap_grid_ymax_for_stacked_plan(
            primary_ys,
            label_bounds[1],
            internal_gap,
            margin_mm,
        )
        grid_bounds = (label_bounds[0], grid_ymax)
        subpanel_note = {
            "subpanels": 1,
            "grid_ymax_capped": round(grid_ymax, 1),
        }

    in_band = sum(
        1 for y in ys if label_bounds[0] <= y <= label_bounds[1]
    )

    if frame_layers:
        frame_ys: list[float] = []
        for entity in msp:
            if entity.dxf.layer not in frame_layers:
                continue
            if entity.dxftype() != "LINE":
                continue
            frame_ys.extend([entity.dxf.start.y, entity.dxf.end.y])
        if frame_ys:
            podium_margin = margin_mm * 0.25
            grid_bounds = (
                min(grid_bounds[0], min(frame_ys) - podium_margin),
                grid_bounds[1],
            )

    return FloorZone(
        bounds_y=grid_bounds,
        label_bounds_y=label_bounds,
        method="thk_cluster",
        label_count=in_band,
        cluster_count=len(clusters),
        included_satellite_clusters=satellites,
        notes={
            "gap_mm": round(gap, 1),
            "primary_cluster_labels": primary.count,
            "margin_mm": margin_mm,
            **subpanel_note,
        },
    )


def infer_bounds_from_frame_structure(
    msp,
    frame_layers: tuple[str, ...],
    *,
    margin_mm: float = 5000.0,
    min_span_mm: float = 3000.0,
) -> FloorZone | None:
    """Fallback when no *THK tags: span of long structural frame lines."""
    ys: list[float] = []
    for entity in msp:
        if entity.dxf.layer not in frame_layers:
            continue
        if entity.dxftype() != "LINE":
            continue
        x1, y1 = entity.dxf.start.x, entity.dxf.start.y
        x2, y2 = entity.dxf.end.x, entity.dxf.end.y
        span = abs(x2 - x1) + abs(y2 - y1)
        if span < min_span_mm:
            continue
        ys.extend([y1, y2])
    if len(ys) < 4:
        return None
    ymin, ymax = min(ys), max(ys)
    return FloorZone(
        bounds_y=(ymin - margin_mm, ymax + margin_mm),
        method="frame_structure",
        label_count=0,
        notes={"line_y_samples": len(ys)},
    )


def infer_bounds_from_floor_title(
    msp,
    title_layers: tuple[str, ...] = ("G-ANNO-TEXT", "dim", "S-BEAM-IDEN"),
    *,
    y_span_mm: float = 48000.0,
) -> FloorZone | None:
    title_y: float | None = None
    for entity in msp:
        if entity.dxf.layer not in title_layers:
            continue
        if entity.dxftype() not in ("TEXT", "MTEXT"):
            continue
        text = parse_text_content(entity)
        if FLOOR_TITLE_RE.search(text):
            title_y = entity.dxf.insert.y
            break

    if title_y is None:
        return None

    ymin = title_y + 5000.0
    ymax = ymin + y_span_mm
    return FloorZone(
        bounds_y=(ymin, ymax),
        method="floor_title",
        notes={"title_y_mm": round(title_y, 1)},
    )


def infer_bounds_from_thk_labels_legacy(
    msp,
    label_layers: tuple[str, ...],
    *,
    margin_below_mm: float = 5000.0,
    y_span_mm: float = 37200.0,
) -> FloorZone | None:
    """Legacy fixed-span band from global minimum Y (kept for regression compare)."""
    points = _label_positions(msp, label_layers)
    if len(points) < 5:
        return None
    ys = [p[1] for p in points]
    y_label_min = min(ys)
    bounds = (y_label_min - margin_below_mm, y_label_min + y_span_mm)
    in_band = sum(1 for y in ys if bounds[0] <= y <= bounds[1])
    return FloorZone(
        bounds_y=bounds,
        method="thk_legacy_span",
        label_count=in_band,
        notes={"y_span_mm": y_span_mm},
    )


def resolve_floor_zone(
    msp,
    *,
    label_layers: tuple[str, ...],
    frame_layers: tuple[str, ...] = (),
    bounds_y: tuple[float, float] | None = None,
    mode: str = "cluster",
    cluster_gap_mm: float = 6000.0,
    cluster_margin_mm: float = 5000.0,
) -> FloorZone:
    """
    Resolve vertical floor band for slab detection.

    mode:
      cluster — generic Y-cluster of *THK labels (+ small satellites)
      legacy  — fixed span from min Y
      manual  — use bounds_y only
    """
    if bounds_y is not None:
        return FloorZone(
            bounds_y=bounds_y,
            method="manual",
            notes={},
        )

    if mode == "legacy":
        zone = infer_bounds_from_thk_labels_legacy(msp, label_layers)
        if zone:
            return zone

    if mode == "cluster":
        zone = infer_bounds_from_thk_clusters(
            msp,
            label_layers,
            frame_layers=frame_layers,
            gap_mm=cluster_gap_mm,
            margin_mm=cluster_margin_mm,
        )
        if zone:
            return zone

    zone = infer_bounds_from_floor_title(msp) or infer_bounds_from_frame_structure(
        msp, frame_layers
    )
    if zone:
        return zone

    return FloorZone(bounds_y=None, method="none")


def resolve_floor_bounds(
    msp,
    *,
    label_layers: tuple[str, ...],
    bounds_y: tuple[float, float] | None = None,
    frame_layers: tuple[str, ...] = (),
    mode: str = "cluster",
    cluster_gap_mm: float = 6000.0,
    cluster_margin_mm: float = 5000.0,
) -> tuple[float, float] | None:
    """Backward-compatible helper returning only Y bounds."""
    zone = resolve_floor_zone(
        msp,
        label_layers=label_layers,
        frame_layers=frame_layers,
        bounds_y=bounds_y,
        mode=mode,
        cluster_gap_mm=cluster_gap_mm,
        cluster_margin_mm=cluster_margin_mm,
    )
    return zone.bounds_y
