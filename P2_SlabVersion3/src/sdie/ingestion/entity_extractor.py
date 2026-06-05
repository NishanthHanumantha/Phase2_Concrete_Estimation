from __future__ import annotations

from dataclasses import dataclass, field

from shapely.geometry import LineString, Point, Polygon, box

from sdie.geometry.segments import entity_to_segments
from sdie.thickness.parser import parse_text_content


@dataclass
class DrawingEntity:
    entity_id: str
    handle: str
    layer: str
    entity_type: str
    geometry_wkt: str | None
    centroid_mm: tuple[float, float] | None
    bounds_mm: tuple[float, float, float, float] | None
    text: str | None = None
    length_mm: float | None = None
    area_mm2: float | None = None
    aspect_ratio: float | None = None
    metadata: dict = field(default_factory=dict)


def _line_length(entity) -> float | None:
    if entity.dxftype() != "LINE":
        return None
    return float(
        LineString(
            [(entity.dxf.start.x, entity.dxf.start.y), (entity.dxf.end.x, entity.dxf.end.y)]
        ).length
    )


def _lwpoly_geom(entity) -> tuple[Polygon | None, float | None]:
    if entity.dxftype() != "LWPOLYLINE":
        return None, None
    pts = [(p[0], p[1]) for p in entity.get_points("xy")]
    if len(pts) < 2:
        return None, None
    if entity.closed and len(pts) >= 3:
        try:
            poly = Polygon(pts)
            if poly.is_valid and not poly.is_empty:
                return poly, poly.area
        except Exception:
            pass
    line = LineString(pts)
    return line, line.length


def _entity_centroid(entity) -> tuple[float, float] | None:
    if entity.dxftype() == "LINE":
        return (
            (entity.dxf.start.x + entity.dxf.end.x) / 2.0,
            (entity.dxf.start.y + entity.dxf.end.y) / 2.0,
        )
    if entity.dxftype() in ("TEXT", "MTEXT"):
        if hasattr(entity.dxf, "insert"):
            return (entity.dxf.insert.x, entity.dxf.insert.y)
    if entity.dxftype() == "LWPOLYLINE":
        pts = [(p[0], p[1]) for p in entity.get_points("xy")]
        if pts:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            return (sum(xs) / len(xs), sum(ys) / len(ys))
    if entity.dxftype() == "HATCH":
        try:
            ext = entity.bbox()
            if ext:
                return (
                    (ext.extmin.x + ext.extmax.x) / 2.0,
                    (ext.extmin.y + ext.extmax.y) / 2.0,
                )
        except Exception:
            return None
    return None


def _entity_bounds(entity) -> tuple[float, float, float, float] | None:
    c = _entity_centroid(entity)
    if c is None:
        return None
    if entity.dxftype() == "LINE":
        xs = [entity.dxf.start.x, entity.dxf.end.x]
        ys = [entity.dxf.start.y, entity.dxf.end.y]
        return (min(xs), min(ys), max(xs), max(ys))
    if entity.dxftype() == "LWPOLYLINE":
        pts = [(p[0], p[1]) for p in entity.get_points("xy")]
        if not pts:
            return None
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))
    if entity.dxftype() == "HATCH":
        try:
            ext = entity.bbox()
            if ext:
                return (ext.extmin.x, ext.extmin.y, ext.extmax.x, ext.extmax.y)
        except Exception:
            return None
    if entity.dxftype() in ("TEXT", "MTEXT") and hasattr(entity.dxf, "insert"):
        x, y = entity.dxf.insert.x, entity.dxf.insert.y
        return (x, y, x, y)
    return (c[0], c[1], c[0], c[1])


def extract_drawing_entities(
    msp,
    *,
    layers: tuple[str, ...] | None = None,
    include_text_layers: tuple[str, ...] | None = None,
    bounds_y: tuple[float, float] | None = None,
) -> list[DrawingEntity]:
    """Extract structural primitives from modelspace for classification."""
    entities: list[DrawingEntity] = []
    layer_filter = set(layers) if layers else None
    text_layers = set(include_text_layers or ())
    idx = 0

    for entity in msp:
        layer = entity.dxf.layer
        if layer_filter and layer not in layer_filter and layer not in text_layers:
            continue
        if text_layers and layer not in text_layers and layer_filter and layer not in layer_filter:
            continue

        centroid = _entity_centroid(entity)
        if bounds_y is not None and centroid is not None:
            if not (bounds_y[0] <= centroid[1] <= bounds_y[1]):
                continue

        idx += 1
        dxftype = entity.dxftype()
        geom_wkt = None
        length_mm = None
        area_mm2 = None
        aspect_ratio = None
        text = None

        if dxftype == "LINE":
            line = LineString(
                [(entity.dxf.start.x, entity.dxf.start.y), (entity.dxf.end.x, entity.dxf.end.y)]
            )
            geom_wkt = line.wkt
            length_mm = line.length
            if line.length > 1:
                dx = abs(entity.dxf.end.x - entity.dxf.start.x)
                dy = abs(entity.dxf.end.y - entity.dxf.start.y)
                aspect_ratio = max(dx, dy) / max(min(dx, dy), 1.0)
        elif dxftype == "LWPOLYLINE":
            geom, measure = _lwpoly_geom(entity)
            if geom is not None:
                geom_wkt = geom.wkt
                if geom.geom_type == "Polygon":
                    area_mm2 = geom.area
                    minx, miny, maxx, maxy = geom.bounds
                    w, h = maxx - minx, maxy - miny
                    if min(w, h) > 1:
                        aspect_ratio = max(w, h) / min(w, h)
                else:
                    length_mm = measure
        elif dxftype == "HATCH":
            b = _entity_bounds(entity)
            if b:
                poly = box(*b)
                geom_wkt = poly.wkt
                area_mm2 = poly.area
        elif dxftype in ("TEXT", "MTEXT"):
            text = parse_text_content(entity)

        handle = str(getattr(entity.dxf, "handle", idx))
        entities.append(
            DrawingEntity(
                entity_id=f"ENT-{idx:05d}",
                handle=handle,
                layer=layer,
                entity_type=dxftype,
                geometry_wkt=geom_wkt,
                centroid_mm=centroid,
                bounds_mm=_entity_bounds(entity),
                text=text,
                length_mm=length_mm,
                area_mm2=area_mm2,
                aspect_ratio=aspect_ratio,
            )
        )
    return entities
