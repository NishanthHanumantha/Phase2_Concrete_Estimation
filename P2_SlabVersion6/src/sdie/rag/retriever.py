from __future__ import annotations

from sdie.atlas.schema import AtlasSample
from sdie.ingestion.entity_extractor import DrawingEntity
from sdie.rag.index import RagIndex
from sdie.rag.schema import StructuralKnowledgeBase


def build_rag_index(
    kb: StructuralKnowledgeBase,
    atlas: list[AtlasSample],
    project_id: str,
) -> RagIndex:
    return RagIndex(kb, atlas, project_id)


def retrieve_rag_context(
    entity: DrawingEntity,
    *,
    kb: StructuralKnowledgeBase | None = None,
    atlas: list[AtlasSample] | None = None,
    project_id: str = "GENERIC",
    index: RagIndex | None = None,
    rule_baseline_type: str | None = None,
    top_k: int = 5,
) -> dict:
    """Retrieve layer, annotation, pattern, and estimator context for one entity."""
    idx = index or build_rag_index(kb or StructuralKnowledgeBase(), atlas or [], project_id)

    layer_hits = [lk.to_dict() for lk in idx.layer_knowledge_by_layer.get(entity.layer or "", [])]

    ann_hits = []
    if kb is not None:
        text = (entity.text or "").upper()
        for ak in kb.annotation_knowledge:
            if ak.pattern.upper() in text or (
                ak.component_hint and ak.component_hint.upper() in text
            ):
                ann_hits.append(ak.to_dict())
            elif "THK" in text and "THK" in ak.pattern.upper():
                ann_hits.append(ak.to_dict())

    candidate_types = {rule_baseline_type} if rule_baseline_type else set()
    candidate_types.discard(None)
    if not candidate_types:
        candidate_types = set(idx.patterns_by_type.keys())

    pattern_hits: list[dict] = []
    for ctype in candidate_types:
        for p in idx.patterns_by_type.get(ctype, []):
            pf = p.get("geometry_features", {})
            score = 0.0
            if p.get("component_type") and entity.entity_type:
                score += 0.2
            if pf.get("aspect_ratio") and entity.aspect_ratio:
                diff = abs(pf["aspect_ratio"] - entity.aspect_ratio)
                score += max(0, 0.4 - diff * 0.05)
            if score > 0.25:
                pattern_hits.append({**p, "_score": round(score, 3)})
    pattern_hits.sort(key=lambda x: x.get("_score", 0), reverse=True)
    pattern_hits = pattern_hits[:top_k]

    atlas_hits: list[dict] = []
    for sample in idx.atlas_by_layer.get(entity.layer or "", []):
        score = 0.0
        if sample.layer == entity.layer:
            score += 0.35
        if sample.entity_type == entity.entity_type:
            score += 0.2
        if score >= 0.35:
            atlas_hits.append({**sample.to_dict(), "_score": score})
    atlas_hits.sort(key=lambda x: x.get("_score", 0), reverse=True)
    atlas_hits = atlas_hits[:top_k]

    estimator_hits = [m.to_dict() for m in idx.estimator_mappings[:top_k]]

    return {
        "entity_id": entity.entity_id,
        "layer": entity.layer,
        "layer_knowledge": layer_hits[:top_k],
        "annotation_knowledge": ann_hits[:top_k],
        "pattern_knowledge": pattern_hits,
        "atlas_samples": atlas_hits,
        "estimator_mappings": estimator_hits,
    }
