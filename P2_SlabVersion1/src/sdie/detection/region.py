from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import LineString
from shapely.ops import polygonize


@dataclass
class SlabCandidate:
    slab_id: str
    polygon_wkt: str
    area_m2: float
    centroid_cm: list[float]
    bounds_cm: list[float]
    strategy: str = "region_polygonize"


def detect_closed_regions(
    segments: list[LineString],
    *,
    cm2_to_m2: float,
    min_area_m2: float,
    id_prefix: str = "SLAB",
) -> list[SlabCandidate]:
    candidates: list[SlabCandidate] = []
    polys = sorted(
        (p for p in polygonize(segments) if p.is_valid and not p.is_empty),
        key=lambda p: p.area,
        reverse=True,
    )
    idx = 0
    for poly in polys:
        area_m2 = poly.area * cm2_to_m2
        if area_m2 < min_area_m2:
            continue
        idx += 1
        c = poly.centroid
        candidates.append(
            SlabCandidate(
                slab_id=f"{id_prefix}-{idx:03d}",
                polygon_wkt=poly.wkt,
                area_m2=round(area_m2, 6),
                centroid_cm=[round(c.x, 3), round(c.y, 3)],
                bounds_cm=[round(v, 1) for v in poly.bounds],
            )
        )
    return candidates
