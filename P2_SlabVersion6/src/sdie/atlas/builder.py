from __future__ import annotations

from pathlib import Path

from sdie.atlas.schema import AtlasSample
from sdie.classification.classifier import classify_entities
from sdie.classification.features import (
    build_annotation_features,
    build_geometry_features,
)
from sdie.classification.types import ComponentType
from sdie.ingestion.dxf_reader import load_drawing
from sdie.ingestion.entity_extractor import extract_drawing_entities
from sdie.validation.component_gt import (
    DEFAULT_ANNOTATION_LAYERS,
    DEFAULT_STRUCTURAL_LAYERS,
    discover_teach_structural_layers,
    flatten_modelspace_entities,
)


def build_atlas_samples_from_dxf(
    dxf_path: Path,
    *,
    project_id: str = "INIZIO",
    structural_layers: tuple[str, ...] | None = None,
    annotation_layers: tuple[str, ...] | None = None,
    supervised_component_type: str | None = None,
) -> list[AtlasSample]:
    """
    Tagged DXF → atlas samples.

    When supervised_component_type is set (from manifest tagged_beam/column/shearwall),
    every extracted entity is labelled with that type at confidence 1.0.
    """
    doc, _meta = load_drawing(dxf_path)
    msp = doc.modelspace()
    layers = structural_layers or DEFAULT_STRUCTURAL_LAYERS
    ann = annotation_layers or DEFAULT_ANNOTATION_LAYERS
    entities = extract_drawing_entities(
        msp,
        layers=layers,
        include_text_layers=ann,
    )
    if supervised_component_type and len(entities) < 10:
        # Project with non-default layer naming: expand INSERTs, pick layers
        # by component keyword (see component_gt teach fallback).
        flat = flatten_modelspace_entities(msp)
        fallback_layers = discover_teach_structural_layers(
            flat, supervised_component_type
        )
        if fallback_layers:
            fallback = extract_drawing_entities(
                flat,
                layers=fallback_layers,
                include_text_layers=ann,
            )
            if len(fallback) > len(entities):
                entities = fallback

    if supervised_component_type:
        samples: list[AtlasSample] = []
        for ent in entities:
            if ent.entity_type in ("TEXT", "MTEXT") and not ent.text:
                continue
            geo = build_geometry_features(ent)
            ann_feats = build_annotation_features(ent)
            samples.append(
                AtlasSample(
                    sample_id=f"{dxf_path.stem}_{ent.entity_id}",
                    project_id=project_id,
                    component_type=supervised_component_type,
                    geometry_features=geo,
                    annotation_features=ann_feats,
                    graph_features={},
                    source_drawing=dxf_path.name,
                    confidence=1.0,
                    layer=ent.layer,
                    entity_type=ent.entity_type,
                )
            )
        return samples

    classified = classify_entities(entities)
    samples = []
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
