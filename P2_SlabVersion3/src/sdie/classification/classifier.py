from __future__ import annotations

from sdie.atlas.schema import AtlasSample
from sdie.classification.features import (
    beam_enclosure_score,
    build_annotation_features,
    build_geometry_features,
    column_compactness_score,
    WALL_KEYWORDS,
    wall_continuity_score,
)
from sdie.classification.types import ClassifiedComponent, ComponentType
from sdie.confidence.scorer import score_confidence
from sdie.ingestion.entity_extractor import DrawingEntity

DEFAULT_LAYER_HINTS: dict[str, ComponentType] = {
    "S-BEAM": ComponentType.BEAM,
    "S_FRAMES": ComponentType.BEAM,
    "STR-BEAM": ComponentType.BEAM,
    "S-COLS": ComponentType.COLUMN,
    "S-COL HATCH": ComponentType.COLUMN,
    "S-COL": ComponentType.COLUMN,
    "S-SHEARWALL": ComponentType.SHEAR_WALL,
    "S-SHEAR": ComponentType.SHEAR_WALL,
    "S-WALL": ComponentType.STRUCTURAL_WALL,
    "STR-CUTOUT": ComponentType.OPENING,
    "SUNK SLAB": ComponentType.OPENING,
    "A-FLOR-IDEN": ComponentType.SLAB,
    "S-BEAM-IDEN": ComponentType.BEAM,
}


def _atlas_vote(
    entity: DrawingEntity,
    atlas: list[AtlasSample],
) -> tuple[ComponentType | None, float, list[str]]:
    if not atlas:
        return None, 0.0, []
    best_type: ComponentType | None = None
    best_score = 0.0
    evidence: list[str] = []
    geo = build_geometry_features(entity)
    ann = build_annotation_features(entity)

    for sample in atlas:
        score = 0.0
        if sample.layer and sample.layer == entity.layer:
            score += 0.35
        if sample.entity_type and sample.entity_type == entity.entity_type:
            score += 0.2
        sf = sample.geometry_features
        if sf.get("aspect_ratio") and geo.get("aspect_ratio"):
            diff = abs(sf["aspect_ratio"] - geo["aspect_ratio"])
            score += max(0, 0.25 - diff * 0.05)
        if ann.get("has_thk") and sample.annotation_features.get("has_thk"):
            score += 0.2
        if score > best_score:
            best_score = score
            try:
                best_type = ComponentType(sample.component_type)
            except ValueError:
                best_type = ComponentType.UNKNOWN
            evidence = [f"atlas_match:{sample.sample_id}"]

    if best_score < 0.45:
        return None, 0.0, []
    return best_type, min(0.95, best_score), evidence


def classify_entity(
    entity: DrawingEntity,
    *,
    atlas: list[AtlasSample] | None = None,
    layer_hints: dict[str, ComponentType] | None = None,
) -> ClassifiedComponent:
    hints = layer_hints or DEFAULT_LAYER_HINTS
    geo_feats = build_geometry_features(entity)
    ann_feats = build_annotation_features(entity)
    evidence: list[str] = []

    # Annotation-driven (highest priority for cores/openings)
    text = (entity.text or "").upper()
    component_type = ComponentType.UNKNOWN
    rule_conf = 0.5

    if ann_feats.get("void_component_hint"):
        component_type = ComponentType(ann_feats["void_component_hint"])
        rule_conf = 0.92
        evidence.append(f"void_keyword:{ann_feats.get('void_keyword')}")
    elif ann_feats.get("has_thk"):
        component_type = ComponentType.SLAB
        rule_conf = 0.88
        evidence.append("thk_annotation")
    elif ann_feats.get("has_beam_tag"):
        component_type = ComponentType.BEAM
        rule_conf = 0.85
        evidence.append("beam_size_tag")
    elif entity.layer in hints:
        component_type = hints[entity.layer]
        rule_conf = 0.75
        evidence.append(f"layer_hint:{entity.layer}")
    else:
        beam_s = beam_enclosure_score(entity)
        col_s = column_compactness_score(entity)
        wall_s = wall_continuity_score(entity)
        if beam_s >= 0.7 and beam_s >= col_s:
            component_type = ComponentType.BEAM
            rule_conf = beam_s
            evidence.append("geometry:beam_line")
        elif col_s >= 0.7:
            component_type = ComponentType.COLUMN
            rule_conf = col_s
            evidence.append("geometry:column_footprint")
        elif wall_s >= 0.6:
            component_type = (
                ComponentType.SHEAR_WALL
                if any(k in (entity.layer or "").upper() for k in ("SHEAR", "SW"))
                else ComponentType.STRUCTURAL_WALL
            )
            rule_conf = wall_s
            evidence.append("geometry:wall_line")
        elif any(k in text for k in WALL_KEYWORDS):
            component_type = ComponentType.STRUCTURAL_WALL
            rule_conf = 0.7
            evidence.append("text:wall")

    atlas_type, atlas_conf, atlas_ev = _atlas_vote(entity, atlas or [])
    if atlas_type and atlas_conf > rule_conf:
        component_type = atlas_type
        rule_conf = atlas_conf
        evidence = atlas_ev

    graph_feats: dict = {}
    breakdown = score_confidence(
        geometry_score=rule_conf,
        topology_score=0.6 if entity.entity_type == "LINE" else 0.5,
        graph_score=0.5,
        deepseek_score=0.0,
    )

    return ClassifiedComponent(
        component_id=entity.entity_id,
        component_type=component_type,
        layer=entity.layer,
        entity_type=entity.entity_type,
        geometry_wkt=entity.geometry_wkt,
        centroid_mm=entity.centroid_mm,
        annotation_text=entity.text,
        geometry_features=geo_feats,
        annotation_features=ann_feats,
        graph_features=graph_feats,
        confidence=breakdown["final"],
        confidence_breakdown=breakdown,
        evidence=evidence,
        source_handle=entity.handle,
    )


def classify_entities(
    entities: list[DrawingEntity],
    *,
    atlas: list[AtlasSample] | None = None,
    layer_hints: dict[str, ComponentType] | None = None,
) -> list[ClassifiedComponent]:
    return [
        classify_entity(e, atlas=atlas, layer_hints=layer_hints) for e in entities
    ]
