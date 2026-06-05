from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
from shapely.geometry import box

BEAM_TAG_RE = re.compile(r"\((\d+)\s*[xX]\s*(\d+)\)", re.I)


@dataclass
class SlabCandidate:
    slab_id: str
    polygon_wkt: str
    area_m2: float
    centroid_cm: list[float]
    bounds_cm: list[float]
    strategy: str = "beam_frame_bbox"


def _collect_points(msp, layers: tuple[str, ...]) -> np.ndarray:
    pts: list[tuple[float, float]] = []
    for entity in msp:
        if entity.dxf.layer not in layers:
            continue
        if entity.dxftype() == "LINE":
            pts.append((entity.dxf.start.x, entity.dxf.start.y))
            pts.append((entity.dxf.end.x, entity.dxf.end.y))
        elif entity.dxftype() == "ARC":
            for p in entity.flattening(0.5):
                pts.append((p.x, p.y))
    if not pts:
        return np.empty((0, 2))
    return np.array(pts)


def _parse_beam_half_width_mm(msp, annotation_layers: tuple[str, ...]) -> float:
    for entity in msp:
        if entity.dxf.layer not in annotation_layers:
            continue
        if entity.dxftype() != "TEXT":
            continue
        text = (entity.dxf.text or "").strip()
        m = BEAM_TAG_RE.search(text)
        if m:
            return float(m.group(1)) / 2.0
    return 100.0


def _split_main_cluster_x(points: np.ndarray) -> np.ndarray:
    """Keep main framing cluster; drop detached detail (e.g. OHT tank at high X)."""
    if len(points) < 20:
        return points
    x = np.sort(points[:, 0])
    # Find largest gap between consecutive X values (detail panel separated in X)
    gaps = np.diff(x)
    if len(gaps) == 0:
        return points
    gap_idx = int(np.argmax(gaps))
    gap_size = float(gaps[gap_idx])
    if gap_size < 1500.0:
        return points
    split_x = (x[gap_idx] + x[gap_idx + 1]) / 2.0
    main = points[points[:, 0] <= split_x]
    if len(main) >= 20:
        return main
    return points


def detect_beam_frame_slab(
    msp,
    *,
    frame_layers: tuple[str, ...],
    annotation_layers: tuple[str, ...],
    area_to_m2_factor: float,
    edge_expand_mm: float | None = None,
    id_prefix: str = "SLAB",
) -> list[SlabCandidate]:
    """
    Slab = axis-aligned bbox of main beam framing cluster.

    edge_expand_mm: expand bbox outward to slab outer face (default: half beam width).
    """
    points = _collect_points(msp, frame_layers)
    if len(points) == 0:
        return []

    main = _split_main_cluster_x(points)
    xmin, ymin = main[:, 0].min(), main[:, 1].min()
    xmax, ymax = main[:, 0].max(), main[:, 1].max()

    expand = edge_expand_mm
    if expand is None:
        expand = _parse_beam_half_width_mm(msp, annotation_layers)

    xmin -= expand
    ymin -= expand
    xmax += expand
    ymax += expand

    poly = box(xmin, ymin, xmax, ymax)
    area_m2 = round(poly.area * area_to_m2_factor, 6)
    c = poly.centroid

    return [
        SlabCandidate(
            slab_id=f"{id_prefix}-001",
            polygon_wkt=poly.wkt,
            area_m2=area_m2,
            centroid_cm=[round(c.x, 3), round(c.y, 3)],
            bounds_cm=[round(v, 1) for v in poly.bounds],
            strategy="beam_frame_bbox",
        )
    ]
