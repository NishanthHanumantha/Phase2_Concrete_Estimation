from __future__ import annotations

from pathlib import Path

from sdie.atlas.schema import AtlasSample
from sdie.classification.classifier import classify_entities
from sdie.classification.types import ComponentType
from sdie.ingestion.dxf_reader import load_drawing
from sdie.ingestion.entity_extractor import extract_drawing_entities


def build_atlas_samples_from_dxf(
    dxf_path: Path,
    *,
    project_id: str = "INIZIO",
    structural_layers: tuple[str, ...] | None = None,
    annotation_layers: tuple[str, ...] | None = None,
) -> list[AtlasSample]:
    """
    Auto-labelling engine (Epic 1): tagged/structured DXF → atlas samples.
    Uses layer + geometry + annotation signals from the classifier.
    """
    doc, _meta = load_drawing(dxf_path)
    msp = doc.modelspace()
    layers = structural_layers or (
        "S-BEAM",
        "S_FRAMES",
        "STR-BEAM",
        "S-COLS",
        "S-COL HATCH",
        "S-SHEARWALL",
        "S-WALL",
        "STR-CUTOUT",
        "SUNK SLAB",
        "A-FLOR-IDEN",
        "S-BEAM-IDEN",
    )
    ann = annotation_layers or ("A-FLOR-IDEN", "S-BEAM-IDEN", "G-ANNO-TEXT")
    entities = extract_drawing_entities(
        msp,
        layers=layers,
        include_text_layers=ann,
    )
    classified = classify_entities(entities)
    samples: list[AtlasSample] = []
    for comp in classified:
        if comp.component_type == ComponentType.UNKNOWN:
            continue
        samples.append(
            AtlasSample(
                sample_id=f"{dxf_path.stem}_{comp.component_id}",
                project_id=project_id,
                component_type=comp.component_type.value,
                geometry_features=comp.geometry_features,
                annotation_features=comp.annotation_features,
                graph_features=comp.graph_features,
                source_drawing=dxf_path.name,
                confidence=comp.confidence,
                layer=comp.layer,
                entity_type=comp.entity_type,
            )
        )
    return samples
