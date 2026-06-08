from __future__ import annotations

import math
import re
from typing import Any

from shapely import wkt

from sdie.classification.types import ClassifiedComponent, ComponentType
from sdie.graph.engine import StructuralGraph
from sdie.ingestion.dxf_reader import DrawingMeta
from sdie.ingestion.entity_extractor import DrawingEntity

SCALE_RE = re.compile(
    r"(?:SCALE\s*)?(?:1\s*[:/]\s*(\d+)|(\d+)\s*[:/]\s*1)",
    re.I,
)

BEAM_TYPES = frozenset({ComponentType.BEAM})
COLUMN_TYPES = frozenset({ComponentType.COLUMN})
WALL_TYPES = frozenset({ComponentType.SHEAR_WALL, ComponentType.STRUCTURAL_WALL})


def infer_drawing_scale(msp) -> str | None:
    """Scan TEXT/MTEXT for scale annotations (e.g. 1:100)."""
    best: tuple[int, str] | None = None
    for entity in msp:
        if entity.dxftype() not in ("TEXT", "MTEXT"):
            continue
        text = ""
        if entity.dxftype() == "TEXT":
            text = str(entity.dxf.text or "")
        else:
            text = entity.plain_text() if hasattr(entity, "plain_text") else str(entity.text)
        for m in SCALE_RE.finditer(text):
            denom = m.group(1) or m.group(2)
            if denom and denom.isdigit():
                scale = f"1:{denom}"
                priority = 1 if "SCALE" in text.upper() else 0
                if best is None or priority > best[0]:
                    best = (priority, scale)
    return best[1] if best else None


def collect_drawing_layers(msp, *, max_layers: int = 120) -> list[str]:
    seen: set[str] = set()
    layers: list[str] = []
    for entity in msp:
        layer = entity.dxf.layer
        if layer not in seen:
            seen.add(layer)
            layers.append(layer)
        if len(layers) >= max_layers:
            break
    return sorted(layers)


def _unit_label(meta: DrawingMeta) -> str:
    cu = meta.coordinate_unit
    if cu == "mm":
        return "Millimeters (Metric)"
    if cu == "cm":
        return "Centimeters (Metric)"
    if cu == "m":
        return "Meters (Metric)"
    name = meta.insunits_name.lower()
    if name in ("inches", "feet"):
        return f"{name.title()} (Imperial)"
    return f"{meta.insunits_name} / {cu}"


def build_drawing_context(
    *,
    meta: DrawingMeta,
    msp,
    project_id: str,
    drawing_name: str,
) -> dict[str, Any]:
    scale = infer_drawing_scale(msp)
    layers = collect_drawing_layers(msp)
    return {
        "project_id": project_id,
        "drawing_name": drawing_name,
        "scale": scale or "unknown — infer from geometry and units",
        "units": _unit_label(meta),
        "coordinate_unit": meta.coordinate_unit,
        "insunits": meta.insunits_name,
        "area_to_m2_factor": meta.area_to_m2_factor,
        "extents": meta.extents,
        "layers_found": layers,
        "layer_count": len(layers),
    }


def collect_annotation_points(
    msp, annotation_layers: tuple[str, ...]
) -> list[tuple[float, float, str, str]]:
    points: list[tuple[float, float, str, str]] = []
    for entity in msp:
        if entity.dxf.layer not in annotation_layers:
            continue
        if entity.dxftype() not in ("TEXT", "MTEXT"):
            continue
        if entity.dxftype() == "TEXT":
            text = str(entity.dxf.text or "").strip()
            x, y = entity.dxf.insert.x, entity.dxf.insert.y
        else:
            text = (
                entity.plain_text()
                if hasattr(entity, "plain_text")
                else str(getattr(entity, "text", "") or "")
            ).strip()
            x, y = entity.dxf.insert.x, entity.dxf.insert.y
        if text:
            points.append((x, y, text[:120], entity.dxf.layer))
    return points


def nearby_annotations(
    entity: DrawingEntity,
    annotation_points: list[tuple[float, float, str, str]],
    *,
    radius_mm: float = 2500.0,
    limit: int = 8,
) -> list[dict[str, Any]]:
    if not entity.centroid_mm:
        return []
    cx, cy = entity.centroid_mm
    hits: list[tuple[float, dict]] = []
    for x, y, text, layer in annotation_points:
        dist = math.hypot(cx - x, cy - y)
        if dist <= radius_mm:
            hits.append(
                (
                    dist,
                    {
                        "text": text,
                        "layer": layer,
                        "distance_mm": round(dist, 1),
                    },
                )
            )
    hits.sort(key=lambda h: h[0])
    return [h[1] for h in hits[:limit]]


def _perimeter_mm(entity: DrawingEntity) -> float | None:
    if not entity.geometry_wkt:
        return None
    try:
        geom = wkt.loads(entity.geometry_wkt)
        if geom.geom_type == "Polygon":
            return float(geom.length)
        if geom.geom_type == "LineString":
            return float(geom.length)
    except Exception:
        return None
    return None


def _area_m2(entity: DrawingEntity, area_to_m2_factor: float) -> float | None:
    if entity.area_mm2 is None:
        return None
    return round(entity.area_mm2 * area_to_m2_factor, 4)


def topology_counts(
    comp: ClassifiedComponent,
    graph: StructuralGraph,
    classified_by_id: dict[str, ClassifiedComponent],
) -> dict[str, int]:
    g = graph.graph
    cid = comp.component_id
    if cid not in g:
        return {
            "connected_beams": 0,
            "connected_columns": 0,
            "connected_walls": 0,
            "neighbor_count": 0,
        }

    beams = cols = walls = 0
    for neighbor in g.neighbors(cid):
        other = classified_by_id.get(neighbor)
        if other is None:
            continue
        if other.component_type in BEAM_TYPES:
            beams += 1
        elif other.component_type in COLUMN_TYPES:
            cols += 1
        elif other.component_type in WALL_TYPES:
            walls += 1

    return {
        "connected_beams": beams,
        "connected_columns": cols,
        "connected_walls": walls,
        "neighbor_count": g.degree(cid),
    }


def enrich_entity_context(
    entity: DrawingEntity,
    comp: ClassifiedComponent,
    *,
    meta: DrawingMeta,
    graph: StructuralGraph,
    classified_by_id: dict[str, ClassifiedComponent],
    nearby_ann: list[dict[str, Any]],
) -> dict[str, Any]:
    perim = _perimeter_mm(entity)
    area_m2 = _area_m2(entity, meta.area_to_m2_factor)
    topo = topology_counts(comp, graph, classified_by_id)
    neighbors = list(graph.graph.neighbors(comp.component_id))[:12] if comp.component_id in graph.graph else []

    bbox = None
    if entity.bounds_mm:
        minx, miny, maxx, maxy = entity.bounds_mm
        bbox = {
            "min_x": round(minx, 2),
            "min_y": round(miny, 2),
            "max_x": round(maxx, 2),
            "max_y": round(maxy, 2),
        }

    length_m = None
    if entity.length_mm is not None:
        if meta.coordinate_unit == "mm":
            length_m = round(entity.length_mm / 1000.0, 3)
        elif meta.coordinate_unit == "cm":
            length_m = round(entity.length_mm / 100.0, 3)
        else:
            length_m = round(entity.length_mm, 3)

    return {
        "entity_id": entity.entity_id,
        "entity_type": entity.entity_type,
        "layer": entity.layer,
        "area_m2": area_m2,
        "perimeter_m": round(perim / 1000.0, 3) if perim and meta.coordinate_unit == "mm" else perim,
        "aspect_ratio": entity.aspect_ratio,
        "length_m": length_m,
        "bounding_box": bbox,
        "connected_beams": topo["connected_beams"],
        "connected_columns": topo["connected_columns"],
        "connected_walls": topo["connected_walls"],
        "neighbor_count": topo["neighbor_count"],
        "neighbor_ids": neighbors,
        "nearby_annotations": nearby_ann,
        "entity_annotation": entity.text,
        "rule_baseline": comp.component_type.value,
        "rule_confidence": comp.confidence,
        "geometry_features": comp.geometry_features,
        "annotation_features": comp.annotation_features,
    }


def attach_topology_to_components(
    classified: list[ClassifiedComponent],
    graph: StructuralGraph,
) -> None:
    by_id = {c.component_id: c for c in classified}
    for comp in classified:
        topo = topology_counts(comp, graph, by_id)
        comp.graph_features = {
            **comp.graph_features,
            **topo,
            "neighbors": list(graph.graph.neighbors(comp.component_id))[:20]
            if comp.component_id in graph.graph
            else [],
        }
