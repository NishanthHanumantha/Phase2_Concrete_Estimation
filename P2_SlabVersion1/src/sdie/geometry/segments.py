from __future__ import annotations

from shapely.geometry import LineString

from ezdxf.entities import DXFEntity


def entity_to_segments(entity: DXFEntity) -> list[LineString]:
    t = entity.dxftype()
    if t == "LINE":
        return [
            LineString(
                [
                    (entity.dxf.start.x, entity.dxf.start.y),
                    (entity.dxf.end.x, entity.dxf.end.y),
                ]
            )
        ]
    if t == "ARC":
        pts = [(p.x, p.y) for p in entity.flattening(0.5)]
        return [
            LineString([a, b]) for a, b in zip(pts, pts[1:]) if a != b
        ]
    if t == "LWPOLYLINE":
        pts = [(p[0], p[1]) for p in entity.get_points("xy")]
        pairs = zip(pts, pts[1:] + ([pts[0]] if entity.closed else []))
        return [LineString([a, b]) for a, b in pairs if a != b]
    return []


def collect_segments(msp, layers: tuple[str, ...]) -> list[LineString]:
    segments: list[LineString] = []
    for entity in msp:
        if entity.dxf.layer not in layers:
            continue
        segments.extend(entity_to_segments(entity))
    return segments
