from __future__ import annotations

import re
from dataclasses import dataclass, field

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

from sdie.geometry.segments import entity_to_segments
from sdie.thickness.parser import parse_text_content

BEAM_TAG_RE = re.compile(r"\(?\s*(\d+)\s*[xX]\s*(\d+)\s*\)?", re.I)

VOID_KEYWORD_RADIUS_MM: dict[str, float] = {
    "STAIRCASE": 5500.0,
    "STAIR": 5500.0,
    "LIFT": 4500.0,
    "LIFT PIT": 4500.0,
    "HEADROOM": 4500.0,
    "OHT": 3500.0,
    "TANK": 3500.0,
    "SHAFT": 3500.0,
    "CORE": 4500.0,
    "PLANTER": 3000.0,
    "SUNK": 3500.0,
}

# Ramps handled by centroid skip in beam_grid (large circles over-deduct).
VOID_LABEL_BUFFER_KEYWORDS = tuple(VOID_KEYWORD_RADIUS_MM.keys())

NON_SLAB_TEXT_KEYWORDS = tuple(VOID_KEYWORD_RADIUS_MM.keys()) + (
    "BEAM ALONG",
    "NON STRUCTURAL",
)


@dataclass
class ExclusionCatalog:
    """Union of non-slab regions to subtract from slab candidates."""

    union: object  # shapely geometry
    parts: list[tuple[str, object]] = field(default_factory=list)
    area_m2: float = 0.0

    def difference(self, slab_poly: Polygon, area_to_m2_factor: float) -> Polygon | None:
        if self.union is None:
            return slab_poly
        if self.union.is_empty:
            return slab_poly
        net = slab_poly.difference(self.union)
        if net.is_empty:
            return None
        if net.geom_type == "Polygon":
            return net
        if net.geom_type == "MultiPolygon":
            pieces = [g for g in net.geoms if g.area * area_to_m2_factor >= 0.05]
            if not pieces:
                return None
            return max(pieces, key=lambda g: g.area)
        return None


def _in_y_band(y: float, bounds_y: tuple[float, float] | None) -> bool:
    if bounds_y is None:
        return True
    return bounds_y[0] <= y <= bounds_y[1]


def _entity_centroid_y(entity) -> float | None:
    if entity.dxftype() == "LINE":
        return (entity.dxf.start.y + entity.dxf.end.y) / 2.0
    if hasattr(entity.dxf, "insert"):
        return entity.dxf.insert.y
    return None


def parse_beam_half_width_mm(msp, annotation_layers: tuple[str, ...]) -> float:
    widths: list[float] = []
    for entity in msp:
        if entity.dxf.layer not in annotation_layers:
            continue
        if entity.dxftype() != "TEXT":
            continue
        match = BEAM_TAG_RE.search((entity.dxf.text or "").strip())
        if match:
            w, d = float(match.group(1)), float(match.group(2))
            widths.append(min(w, d))
    if not widths:
        return 225.0
    return max(100.0, min(widths) / 2.0)


def _lwpoly_to_polygon(entity) -> Polygon | None:
    if entity.dxftype() != "LWPOLYLINE":
        return None
    pts = [(p[0], p[1]) for p in entity.get_points("xy")]
    if len(pts) < 3:
        return None
    if not entity.closed:
        return None
    try:
        poly = Polygon(pts)
        return poly if poly.is_valid and not poly.is_empty else None
    except Exception:
        return None


def _hatch_bbox_polygon(entity) -> Polygon | None:
    if entity.dxftype() != "HATCH":
        return None
    try:
        ext = entity.bbox()
        if ext is None:
            return None
        return box(ext.extmin.x, ext.extmin.y, ext.extmax.x, ext.extmax.y)
    except Exception:
        return None


def _buffer_segments(
    msp,
    layers: tuple[str, ...],
    half_width_mm: float,
    bounds_y: tuple[float, float] | None,
) -> list[Polygon]:
    polys: list[Polygon] = []
    for entity in msp:
        if entity.dxf.layer not in layers:
            continue
        cy = _entity_centroid_y(entity)
        if cy is not None and not _in_y_band(cy, bounds_y):
            continue
        for seg in entity_to_segments(entity):
            if seg.length < 50:
                continue
            polys.append(seg.buffer(half_width_mm, cap_style=2, join_style=2))
    return polys


def _collect_void_label_circles(
    msp,
    layers: tuple[str, ...],
    bounds_y: tuple[float, float] | None,
    *,
    keywords: tuple[str, ...] = VOID_LABEL_BUFFER_KEYWORDS,
) -> list[Polygon]:
    circles: list[Polygon] = []
    for entity in msp:
        if entity.dxf.layer not in layers:
            continue
        if entity.dxftype() not in ("TEXT", "MTEXT"):
            continue
        text = parse_text_content(entity).upper()
        if not any(k in text for k in keywords):
            continue
        x, y = entity.dxf.insert.x, entity.dxf.insert.y
        if not _in_y_band(y, bounds_y):
            continue
        radius = 4000.0
        for keyword, r in VOID_KEYWORD_RADIUS_MM.items():
            if keyword in text:
                radius = max(radius, r)
        circles.append(Point(x, y).buffer(radius))
    return circles


def build_exclusion_catalog(
    msp,
    *,
    bounds_y: tuple[float, float] | None = None,
    beam_layers: tuple[str, ...] = (),
    column_layers: tuple[str, ...] = ("S-COLS", "S-COL HATCH"),
    wall_layers: tuple[str, ...] = (),
    hatch_void_layers: tuple[str, ...] = ("SUNK SLAB", "S-COL HATCH"),
    label_box_layers: tuple[str, ...] = (),
    annotation_layers: tuple[str, ...] = ("G-ANNO-TEXT", "S-BEAM-IDEN", "A-FLOR-IDEN"),
    beam_half_width_mm: float | None = None,
    wall_half_width_mm: float = 100.0,
    area_to_m2_factor: float = 1e-6,
    include_void_label_buffers: bool = True,
) -> ExclusionCatalog:
    """
    Collect beam footprints, columns, walls, hatches, and labelled voids.

    Aligns with Prompt_extracted semantic model (Stair Voids, Lift Cores) and
    MODEL_DESIGN §2.5 non-slab zones.
    """
    half_beam = beam_half_width_mm or parse_beam_half_width_mm(
        msp, annotation_layers
    )
    parts: list[tuple[str, object]] = []

    for tag, polys in (
        ("beam", _buffer_segments(msp, beam_layers, half_beam, bounds_y)),
        ("wall", _buffer_segments(msp, wall_layers, wall_half_width_mm, bounds_y)),
    ):
        for poly in polys:
            parts.append((tag, poly))

    for layer in column_layers:
        for entity in msp:
            if entity.dxf.layer != layer:
                continue
            cy = _entity_centroid_y(entity)
            if cy is not None and not _in_y_band(cy, bounds_y):
                continue
            if entity.dxftype() == "LWPOLYLINE":
                poly = _lwpoly_to_polygon(entity)
                if poly is not None:
                    parts.append(("column", poly))
            elif entity.dxftype() == "HATCH":
                poly = _hatch_bbox_polygon(entity)
                if poly is not None:
                    parts.append(("column_hatch", poly))

    for layer in hatch_void_layers:
        for entity in msp:
            if entity.dxf.layer != layer:
                continue
            poly = _hatch_bbox_polygon(entity)
            if poly is not None:
                parts.append(("hatch_void", poly))

    for layer in label_box_layers:
        for entity in msp:
            if entity.dxf.layer != layer:
                continue
            if entity.dxftype() != "LWPOLYLINE" or not entity.closed:
                continue
            poly = _lwpoly_to_polygon(entity)
            if poly is None:
                continue
            # THK tag boxes on A-FLOR-IDEN (~0.4 m²) — not slab area
            if poly.area * area_to_m2_factor < 15.0:
                parts.append(("label_box", poly))

    if include_void_label_buffers:
        for poly in _collect_void_label_circles(msp, annotation_layers, bounds_y):
            parts.append(("void_label", poly))

    if not parts:
        return ExclusionCatalog(union=None, parts=[], area_m2=0.0)

    union = unary_union([p[1] for p in parts])
    return ExclusionCatalog(
        union=union,
        parts=parts,
        area_m2=round(union.area * area_to_m2_factor, 3),
    )


def build_beam_footprint_overlay(
    msp,
    beam_layers: tuple[str, ...],
    *,
    bounds_y: tuple[float, float] | None,
    annotation_layers: tuple[str, ...],
    beam_half_width_mm: float | None = None,
) -> object | None:
    """Beam stripe geometry for overlay only (Prompt §10 ignored areas)."""
    if not beam_layers:
        return None
    half = beam_half_width_mm or parse_beam_half_width_mm(msp, annotation_layers)
    polys = _buffer_segments(msp, beam_layers, half, bounds_y)
    if not polys:
        return None
    return unary_union(polys)
