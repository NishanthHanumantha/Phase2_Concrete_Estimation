from __future__ import annotations

from collections import defaultdict

from sdie.atlas.schema import AtlasSample
from sdie.classification.features import (
    beam_enclosure_score,
    build_annotation_features,
    build_geometry_features,
    column_compactness_score,
    WALL_KEYWORDS,
    wall_continuity_score,
)
from sdie.classification.layer_profiles import (
    HARD_GLOBAL_LAYER_HINTS,
    SOFT_LAYER_HINTS,
    load_profiles,
    merged_layer_hints_for_project,
    resolve_hard_global_layer,
    resolve_layer_rule,
)
from sdie.classification.types import ClassifiedComponent, ComponentType
from sdie.confidence.scorer import score_confidence
from sdie.ingestion.entity_extractor import DrawingEntity

# Backward-compatible export used by rag/builder
DEFAULT_LAYER_HINTS = {k: v for k, v in HARD_GLOBAL_LAYER_HINTS.items()}
DEFAULT_LAYER_HINTS["S_FRAMES"] = ComponentType.BEAM
DEFAULT_LAYER_HINTS["STR-BEAM"] = ComponentType.BEAM
DEFAULT_LAYER_HINTS["S-WALL"] = ComponentType.STRUCTURAL_WALL


def build_atlas_layer_index(
    atlas: list[AtlasSample],
) -> dict[str, list[AtlasSample]]:
    idx: dict[str, list[AtlasSample]] = defaultdict(list)
    for sample in atlas:
        if sample.layer:
            idx[sample.layer].append(sample)
    return idx


def _atlas_vote(
    entity: DrawingEntity,
    atlas: list[AtlasSample],
    *,
    layer_index: dict[str, list[AtlasSample]] | None = None,
    rule_confidence: float = 0.0,
) -> tuple[ComponentType | None, float, list[str]]:
    if not atlas:
        return None, 0.0, []
    candidates = (
        layer_index.get(entity.layer or "", [])
        if layer_index is not None
        else atlas
    )
    if not candidates:
        return None, 0.0, []
    best_type: ComponentType | None = None
    best_score = 0.0
    evidence: list[str] = []
    geo = build_geometry_features(entity)
    ann = build_annotation_features(entity)

    for sample in candidates:
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
        if sample.confidence >= 0.99:
            score += 0.35
        if score > best_score:
            best_score = score
            try:
                best_type = ComponentType(sample.component_type)
            except ValueError:
                best_type = ComponentType.UNKNOWN
            evidence = [f"atlas_match:{sample.sample_id}"]

    if best_score < 0.45:
        return None, 0.0, []
    atlas_conf = min(0.95, best_score)
    if rule_confidence >= 0.88:
        return None, 0.0, []
    return best_type, atlas_conf, evidence


def _geometry_classify(
    entity: DrawingEntity,
    layer: str,
) -> tuple[ComponentType | None, float, list[str]]:
    """Geometry-first for soft/ambiguous layers (e.g. S_FRAMES)."""
    beam_s = beam_enclosure_score(entity)
    col_s = column_compactness_score(entity)
    wall_s = wall_continuity_score(entity)

    if col_s >= 0.65 and col_s >= beam_s:
        return ComponentType.COLUMN, max(0.82, col_s), ["geometry:column_footprint"]
    if beam_s >= 0.65 and beam_s > col_s:
        return ComponentType.BEAM, max(0.82, beam_s), ["geometry:beam_line"]
    if wall_s >= 0.6:
        ctype = (
            ComponentType.SHEAR_WALL
            if any(k in layer.upper() for k in ("SHEAR", "SW", "WALL"))
            else ComponentType.STRUCTURAL_WALL
        )
        return ctype, wall_s, ["geometry:wall_line"]
    return None, 0.0, []


def classify_entity(
    entity: DrawingEntity,
    *,
    atlas: list[AtlasSample] | None = None,
    layer_hints: dict[str, ComponentType] | None = None,
    atlas_layer_index: dict[str, list[AtlasSample]] | None = None,
    project_id: str = "INIZIO",
    profiles: dict | None = None,
) -> ClassifiedComponent:
    profiles = profiles if profiles is not None else load_profiles()
    hints = layer_hints or merged_layer_hints_for_project(project_id, profiles=profiles)
    geo_feats = build_geometry_features(entity)
    ann_feats = build_annotation_features(entity)
    evidence: list[str] = []
    layer = entity.layer or ""
    etype = entity.entity_type or ""

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
    else:
        matched = False

        hard = resolve_hard_global_layer(layer, etype, profiles=profiles)
        if hard:
            component_type, rule_conf, tag = hard
            evidence.append(tag)
            matched = True

        if not matched:
            proj_rule = resolve_layer_rule(project_id, layer, etype, profiles=profiles)
            if proj_rule:
                component_type, rule_conf, tag = proj_rule
                evidence.append(tag)
                matched = True

        if not matched and layer in SOFT_LAYER_HINTS:
            gtype, gconf, gev = _geometry_classify(entity, layer)
            if gtype:
                component_type, rule_conf = gtype, gconf
                evidence.extend(gev)
                matched = True

        if not matched and layer in hints and layer not in SOFT_LAYER_HINTS:
            component_type = hints[layer]
            rule_conf = 0.75
            evidence.append(f"layer_hint:{layer}")

        if not matched and component_type == ComponentType.UNKNOWN:
            gtype, gconf, gev = _geometry_classify(entity, layer)
            if gtype:
                component_type, rule_conf = gtype, gconf
                evidence.extend(gev)
            elif any(k in text for k in WALL_KEYWORDS):
                component_type = ComponentType.SHEAR_WALL
                rule_conf = 0.7
                evidence.append("text:wall")

    atlas_type, atlas_conf, atlas_ev = _atlas_vote(
        entity,
        atlas or [],
        layer_index=atlas_layer_index,
        rule_confidence=rule_conf,
    )
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
    project_id: str = "INIZIO",
    profiles: dict | None = None,
) -> list[ClassifiedComponent]:
    profiles = profiles if profiles is not None else load_profiles()
    atlas_layer_index = build_atlas_layer_index(atlas or [])
    return [
        classify_entity(
            e,
            atlas=atlas,
            layer_hints=layer_hints,
            atlas_layer_index=atlas_layer_index,
            project_id=project_id,
            profiles=profiles,
        )
        for e in entities
    ]
