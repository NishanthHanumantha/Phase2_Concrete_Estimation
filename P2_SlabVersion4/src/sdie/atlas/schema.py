from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class AtlasSample:
    sample_id: str
    project_id: str
    component_type: str
    geometry_features: dict[str, Any]
    annotation_features: dict[str, Any]
    graph_features: dict[str, Any]
    source_drawing: str
    confidence: float = 1.0
    layer: str | None = None
    entity_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AtlasSample":
        return cls(
            sample_id=data["sample_id"],
            project_id=data.get("project_id", "INIZIO"),
            component_type=data["component_type"],
            geometry_features=data.get("geometry_features", {}),
            annotation_features=data.get("annotation_features", {}),
            graph_features=data.get("graph_features", {}),
            source_drawing=data.get("source_drawing", ""),
            confidence=float(data.get("confidence", 1.0)),
            layer=data.get("layer"),
            entity_type=data.get("entity_type"),
        )
