from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx
from shapely import wkt
from shapely.geometry import Point

from sdie.classification.types import ClassifiedComponent, ComponentType

REL_SUPPORTS = "supports"
REL_FRAMES = "frames"
REL_TOUCHES = "touches"
REL_CONTAINS = "contains"
REL_ADJACENT = "adjacent"

NODE_TYPE_MAP = {
    ComponentType.SLAB: "Slab",
    ComponentType.BEAM: "Beam",
    ComponentType.COLUMN: "Column",
    ComponentType.SHEAR_WALL: "Wall",
    ComponentType.STRUCTURAL_WALL: "Wall",
    ComponentType.LIFT_CORE: "Core",
    ComponentType.STAIR_CORE: "Core",
    ComponentType.SHAFT: "Core",
    ComponentType.OPENING: "Opening",
    ComponentType.UNKNOWN: "Unknown",
}


@dataclass
class StructuralGraph:
    graph: nx.Graph = field(default_factory=nx.Graph)
    node_count: int = 0
    edge_count: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "nodes": [
                {"id": n, **self.graph.nodes[n]} for n in self.graph.nodes
            ],
            "edges": [
                {"source": u, "target": v, **d}
                for u, v, d in self.graph.edges(data=True)
            ],
            "notes": self.notes,
        }


def _geom_point(comp: ClassifiedComponent) -> Point | None:
    if comp.centroid_mm:
        return Point(comp.centroid_mm[0], comp.centroid_mm[1])
    if comp.geometry_wkt:
        try:
            geom = wkt.loads(comp.geometry_wkt)
            return geom.centroid
        except Exception:
            return None
    return None


def build_structural_graph(
    components: list[ClassifiedComponent],
    *,
    touch_distance_mm: float = 800.0,
) -> StructuralGraph:
    """PART 6 — Column → Beam → Slab relationships via proximity graph."""
    g = nx.Graph()
    points: dict[str, Point] = {}

    for comp in components:
        g.add_node(
            comp.component_id,
            component_type=comp.component_type.value,
            node_type=NODE_TYPE_MAP.get(comp.component_type, "Unknown"),
            layer=comp.layer,
            confidence=comp.confidence,
        )
        pt = _geom_point(comp)
        if pt is not None:
            points[comp.component_id] = pt

    beams = [c for c in components if c.component_type == ComponentType.BEAM]
    columns = [c for c in components if c.component_type == ComponentType.COLUMN]
    slabs = [c for c in components if c.component_type == ComponentType.SLAB]
    cores = [
        c
        for c in components
        if c.component_type
        in (
            ComponentType.LIFT_CORE,
            ComponentType.STAIR_CORE,
            ComponentType.SHAFT,
        )
    ]
    walls = [
        c
        for c in components
        if c.component_type
        in (ComponentType.SHEAR_WALL, ComponentType.STRUCTURAL_WALL)
    ]

    def link(a_id: str, b_id: str, rel: str, weight: float = 1.0) -> None:
        if a_id == b_id:
            return
        if g.has_edge(a_id, b_id):
            g.edges[a_id, b_id]["relationships"].append(rel)
        else:
            g.add_edge(a_id, b_id, relationships=[rel], weight=weight)

    for col in columns:
        cp = points.get(col.component_id)
        if cp is None:
            continue
        for beam in beams:
            bp = points.get(beam.component_id)
            if bp is None:
                continue
            if cp.distance(bp) <= touch_distance_mm * 2:
                link(col.component_id, beam.component_id, REL_SUPPORTS)

    for beam in beams:
        bp = points.get(beam.component_id)
        if bp is None:
            continue
        for slab in slabs:
            sp = points.get(slab.component_id)
            if sp is None:
                continue
            if bp.distance(sp) <= touch_distance_mm * 3:
                link(beam.component_id, slab.component_id, REL_FRAMES)

    for i, a in enumerate(components):
        pa = points.get(a.component_id)
        if pa is None:
            continue
        for b in components[i + 1 :]:
            pb = points.get(b.component_id)
            if pb is None:
                continue
            dist = pa.distance(pb)
            if dist <= touch_distance_mm:
                link(a.component_id, b.component_id, REL_ADJACENT, weight=0.5)

    for core in cores:
        cp = points.get(core.component_id)
        if cp is None:
            continue
        for comp in components:
            if comp.component_id == core.component_id:
                continue
            pt = points.get(comp.component_id)
            if pt and cp.distance(pt) <= touch_distance_mm * 2:
                link(core.component_id, comp.component_id, REL_CONTAINS)

    for wall in walls:
        wp = points.get(wall.component_id)
        if wp is None:
            continue
        for beam in beams:
            bp = points.get(beam.component_id)
            if bp and wp.distance(bp) <= touch_distance_mm:
                link(wall.component_id, beam.component_id, REL_TOUCHES)

    # Enrich graph_features on components
    for comp in components:
        if comp.component_id not in g:
            continue
        comp.graph_features = {
            "degree": g.degree(comp.component_id),
            "neighbors": list(g.neighbors(comp.component_id)),
            "node_type": NODE_TYPE_MAP.get(comp.component_type, "Unknown"),
        }

    sg = StructuralGraph(
        graph=g,
        node_count=g.number_of_nodes(),
        edge_count=g.number_of_edges(),
        notes=[
            f"beams={len(beams)} columns={len(columns)} slabs={len(slabs)}",
            f"cores={len(cores)} walls={len(walls)}",
        ],
    )
    return sg
