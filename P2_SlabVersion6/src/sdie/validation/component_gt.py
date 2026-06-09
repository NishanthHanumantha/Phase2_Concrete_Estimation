"""Entity-level ground truth from manifest tagged component drawings."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sdie.classification.features import build_annotation_features
from sdie.classification.types import ComponentType
from sdie.ingestion.dxf_reader import load_drawing
from sdie.ingestion.entity_extractor import DrawingEntity, extract_drawing_entities
from sdie.project_knowledge.paths import resolve_manifest_dxf_path

BUSINESS_COMPONENT_TYPES: tuple[str, ...] = (
    "Slab",
    "Beam",
    "Column",
    "Shear Wall",
)

# Current phase: quantity targets + primary classification eval scope.
QUANTITY_PHASE_TYPES: tuple[str, ...] = ("Slab", "Beam")

MANIFEST_SUPERVISED_FLAGS: dict[str, str] = {
    "tagged_beam": ComponentType.BEAM.value,
    "tagged_column": ComponentType.COLUMN.value,
    "tagged_shearwall": ComponentType.SHEAR_WALL.value,
    "tagged_slab": ComponentType.SLAB.value,
}

DEFAULT_STRUCTURAL_LAYERS: tuple[str, ...] = (
    "S-BEAM",
    "S_FRAMES",
    "STR-BEAM",
    "S-COLS",
    "S-COL HATCH",
    "S-COL",
    "S-SHEARWALL",
    "S-SHEAR",
    "S-WALL",
    "STR-CUTOUT",
    "SUNK SLAB",
    "A-FLOR-IDEN",
    "S-BEAM-IDEN",
)

DEFAULT_ANNOTATION_LAYERS: tuple[str, ...] = (
    "A-FLOR-IDEN",
    "S-BEAM-IDEN",
    "G-ANNO-TEXT",
)


def normalize_business_type(component_type: str) -> str:
    """Map internal classifier labels to the four business calculator types."""
    if component_type == ComponentType.STRUCTURAL_WALL.value:
        return ComponentType.SHEAR_WALL.value
    if component_type in BUSINESS_COMPONENT_TYPES:
        return component_type
    return "Other"


def supervised_type_from_drawing(drawing: dict[str, Any]) -> str | None:
    for flag, ctype in MANIFEST_SUPERVISED_FLAGS.items():
        if drawing.get(flag):
            return ctype
    return None


@dataclass
class GtDrawingSpec:
    project_id: str
    drawing_id: str
    dxf_path: Path
    supervised_type: str | None
    primary: bool = False


@dataclass
class EntityGroundTruth:
    entity_id: str
    project_id: str
    source_drawing: str
    dxf_path: Path
    expected_type: str
    gt_source: str
    layer: str
    entity_type: str


def load_manifest(manifest_path: Path) -> dict[str, Any]:
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def iter_gt_drawing_specs(
    manifest_path: Path,
    project_root: Path,
) -> list[GtDrawingSpec]:
    manifest = load_manifest(manifest_path)
    specs: list[GtDrawingSpec] = []
    for project in manifest.get("projects", []):
        pid = project["project_id"]
        for drawing in project.get("drawings", []):
            rel = drawing.get("dxf")
            if not rel:
                continue
            dxf_path = resolve_manifest_dxf_path(project_root, rel)
            if not dxf_path.exists():
                continue
            specs.append(
                GtDrawingSpec(
                    project_id=pid,
                    drawing_id=drawing.get("drawing_id", dxf_path.stem),
                    dxf_path=dxf_path,
                    supervised_type=supervised_type_from_drawing(drawing),
                    primary=bool(drawing.get("primary")),
                )
            )
    return specs


def extract_entities_from_dxf(
    dxf_path: Path,
    *,
    structural_layers: tuple[str, ...] | None = None,
    annotation_layers: tuple[str, ...] | None = None,
) -> list[DrawingEntity]:
    doc, _meta = load_drawing(dxf_path)
    msp = doc.modelspace()
    return extract_drawing_entities(
        msp,
        layers=structural_layers or DEFAULT_STRUCTURAL_LAYERS,
        include_text_layers=annotation_layers or DEFAULT_ANNOTATION_LAYERS,
    )


def build_entity_ground_truth(
    spec: GtDrawingSpec,
    entities: list[DrawingEntity] | None = None,
) -> list[EntityGroundTruth]:
    """Build per-entity GT for one manifest drawing."""
    entities = entities or extract_entities_from_dxf(spec.dxf_path)
    out: list[EntityGroundTruth] = []

    if spec.supervised_type:
        for ent in entities:
            out.append(
                EntityGroundTruth(
                    entity_id=ent.entity_id,
                    project_id=spec.project_id,
                    source_drawing=spec.dxf_path.name,
                    dxf_path=spec.dxf_path,
                    expected_type=spec.supervised_type,
                    gt_source=f"manifest:{spec.supervised_type}",
                    layer=ent.layer,
                    entity_type=ent.entity_type,
                )
            )
        return out

    if spec.primary:
        for ent in entities:
            ann = build_annotation_features(ent)
            if ann.get("has_thk"):
                out.append(
                    EntityGroundTruth(
                        entity_id=ent.entity_id,
                        project_id=spec.project_id,
                        source_drawing=spec.dxf_path.name,
                        dxf_path=spec.dxf_path,
                        expected_type=ComponentType.SLAB.value,
                        gt_source="primary:thk_annotation",
                        layer=ent.layer,
                        entity_type=ent.entity_type,
                    )
                )
    return out


def load_all_entity_ground_truth(
    manifest_path: Path,
    project_root: Path,
    *,
    include_primary_slab: bool = True,
    component_tagged_only: bool = False,
    slab_beam_only: bool = False,
) -> list[EntityGroundTruth]:
    """
    Load entity GT corpus from manifest.

    component_tagged_only: only manifest-tagged drawings (tagged_slab/beam/column/shearwall)
    slab_beam_only: only tagged Slab/ and Beam/ teach drawings (quantity-phase eval)
    """
    all_gt: list[EntityGroundTruth] = []
    for spec in iter_gt_drawing_specs(manifest_path, project_root):
        if component_tagged_only and not spec.supervised_type:
            continue
        if slab_beam_only:
            if spec.supervised_type not in QUANTITY_PHASE_TYPES:
                continue
        if not include_primary_slab and spec.primary and not spec.supervised_type:
            continue
        all_gt.extend(build_entity_ground_truth(spec))
    return all_gt


def summarize_gt_corpus(gt: list[EntityGroundTruth]) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    by_project: dict[str, int] = {}
    by_drawing: dict[str, int] = {}
    for row in gt:
        by_type[row.expected_type] = by_type.get(row.expected_type, 0) + 1
        by_project[row.project_id] = by_project.get(row.project_id, 0) + 1
        key = f"{row.project_id}/{row.source_drawing}"
        by_drawing[key] = by_drawing.get(key, 0) + 1
    return {
        "total_entities": len(gt),
        "by_type": by_type,
        "by_project": by_project,
        "by_drawing": by_drawing,
    }
