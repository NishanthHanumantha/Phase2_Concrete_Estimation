from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sdie.classification.types import ClassifiedComponent
from sdie.graph.engine import StructuralGraph


@dataclass
class SemanticBuildingModel:
    """PART 8 — Building → Floors → Zones → Components → Relationships → Quantities."""

    project_id: str
    source_drawing: str
    floors: list[dict[str, Any]] = field(default_factory=list)
    zones: list[dict[str, Any]] = field(default_factory=list)
    components: list[dict[str, Any]] = field(default_factory=list)
    relationships: list[dict[str, Any]] = field(default_factory=list)
    quantities: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "building": {
                "project_id": self.project_id,
                "source_drawing": self.source_drawing,
                "floors": self.floors,
                "zones": self.zones,
                "components": self.components,
                "relationships": self.relationships,
                "quantities": self.quantities,
            }
        }


def build_semantic_model(
    *,
    project_id: str,
    source_drawing: str,
    classified: list[ClassifiedComponent],
    graph: StructuralGraph,
    floor_zone: dict | None = None,
    slab_quantities: list[dict] | None = None,
) -> SemanticBuildingModel:
    floors = []
    if floor_zone:
        floors.append(
            {
                "floor_id": "FLOOR-01",
                "method": floor_zone.get("method"),
                "bounds_y_mm": floor_zone.get("bounds_y_mm"),
                "label_bounds_y_mm": floor_zone.get("label_bounds_y_mm"),
            }
        )

    components = [
        {
            "component_id": c.component_id,
            "component_type": c.component_type.value,
            "layer": c.layer,
            "entity_type": c.entity_type,
            "confidence": c.confidence,
            "confidence_breakdown": c.confidence_breakdown,
            "evidence": c.evidence,
            "centroid_mm": list(c.centroid_mm) if c.centroid_mm else None,
            "geometry_features": c.geometry_features,
            "annotation_features": c.annotation_features,
            "graph_features": c.graph_features,
        }
        for c in classified
    ]

    relationships = [
        {
            "source": u,
            "target": v,
            "types": d.get("relationships", []),
            "weight": d.get("weight", 1.0),
        }
        for u, v, d in graph.graph.edges(data=True)
    ]

    qty = {}
    if slab_quantities:
        qty = {
            "slabs": slab_quantities,
            "totals": {
                "area_m2": round(sum(s.get("area_m2", 0) for s in slab_quantities), 6),
                "concrete_m3": round(
                    sum(s.get("concrete_m3", 0) for s in slab_quantities), 6
                ),
                "shuttering_m2": round(
                    sum(s.get("shuttering_m2", 0) for s in slab_quantities), 6
                ),
                "slab_count": len(slab_quantities),
            },
        }

    return SemanticBuildingModel(
        project_id=project_id,
        source_drawing=source_drawing,
        floors=floors,
        zones=[],
        components=components,
        relationships=relationships,
        quantities=qty,
    )
