from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class LayerKnowledge:
    layer: str
    component_type: str
    project_id: str
    confidence: float = 0.8
    source: str = "atlas"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnnotationKnowledge:
    pattern: str
    interpretation: str
    component_hint: str | None = None
    project_id: str = "GLOBAL"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EstimatorMapping:
    project_id: str
    drawing_signal: str
    estimator_component: str
    component_type: str
    source_drawing: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StructuralKnowledgeBase:
    """V4 Component Knowledge Base (RAG corpus)."""

    version: str = "4.0"
    layer_knowledge: list[LayerKnowledge] = field(default_factory=list)
    annotation_knowledge: list[AnnotationKnowledge] = field(default_factory=list)
    pattern_knowledge: list[dict[str, Any]] = field(default_factory=list)
    estimator_mappings: list[EstimatorMapping] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "layer_knowledge": [x.to_dict() for x in self.layer_knowledge],
            "annotation_knowledge": [x.to_dict() for x in self.annotation_knowledge],
            "pattern_knowledge": self.pattern_knowledge,
            "estimator_mappings": [x.to_dict() for x in self.estimator_mappings],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StructuralKnowledgeBase":
        return cls(
            version=data.get("version", "4.0"),
            layer_knowledge=[
                LayerKnowledge(**k) for k in data.get("layer_knowledge", [])
            ],
            annotation_knowledge=[
                AnnotationKnowledge(**k) for k in data.get("annotation_knowledge", [])
            ],
            pattern_knowledge=list(data.get("pattern_knowledge", [])),
            estimator_mappings=[
                EstimatorMapping(**k) for k in data.get("estimator_mappings", [])
            ],
        )
