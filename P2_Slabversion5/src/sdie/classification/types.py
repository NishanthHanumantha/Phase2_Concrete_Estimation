from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ComponentType(str, Enum):
    SLAB = "Slab"
    BEAM = "Beam"
    COLUMN = "Column"
    SHEAR_WALL = "Shear Wall"
    STRUCTURAL_WALL = "Structural Wall"
    LIFT_CORE = "Lift Core"
    STAIR_CORE = "Stair Core"
    SHAFT = "Shaft"
    OPENING = "Opening"
    UNKNOWN = "Unknown"

    @classmethod
    def non_slab_types(cls) -> tuple["ComponentType", ...]:
        return (
            cls.BEAM,
            cls.COLUMN,
            cls.SHEAR_WALL,
            cls.STRUCTURAL_WALL,
            cls.LIFT_CORE,
            cls.STAIR_CORE,
            cls.SHAFT,
            cls.OPENING,
        )


NON_SLAB_COMPONENTS = frozenset(ComponentType.non_slab_types())

# Subset used for slab area exclusion — beams frame bays, they are not deducted.
EXCLUSION_COMPONENT_TYPES = frozenset(
    t
    for t in ComponentType.non_slab_types()
    if t != ComponentType.BEAM
)


@dataclass
class ClassifiedComponent:
    component_id: str
    component_type: ComponentType
    layer: str
    entity_type: str
    geometry_wkt: str | None
    centroid_mm: tuple[float, float] | None
    annotation_text: str | None = None
    geometry_features: dict = field(default_factory=dict)
    annotation_features: dict = field(default_factory=dict)
    graph_features: dict = field(default_factory=dict)
    confidence: float = 0.0
    confidence_breakdown: dict = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    review_required: bool = False
    source_handle: str | None = None
