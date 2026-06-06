from __future__ import annotations

import json
import logging
from typing import Any

from sdie.atlas.schema import AtlasSample
from sdie.classification.classifier import classify_entities
from sdie.classification.layer_profiles import load_profiles, merged_layer_hints_for_project
from sdie.classification.types import ClassifiedComponent, ComponentType
from sdie.confidence.scorer import (
    infer_v5_evidence_from_baseline,
    score_confidence,
    score_v5_confidence,
)
from sdie.graph.engine import build_structural_graph
from sdie.ingestion.dxf_reader import DrawingMeta
from sdie.ingestion.entity_extractor import DrawingEntity
from sdie.rag.index import RagIndex
from sdie.rag.retriever import build_rag_index, retrieve_rag_context
from sdie.rag.schema import StructuralKnowledgeBase
from sdie.reasoning.deepseek_client import DeepSeekError, chat_json
from sdie.reasoning.env import get_deepseek_api_key
from sdie.reasoning.v5_context import (
    attach_topology_to_components,
    build_drawing_context,
    collect_annotation_points,
    enrich_entity_context,
    nearby_annotations,
)

logger = logging.getLogger(__name__)

ALLOWED = [t.value for t in ComponentType]

SYSTEM = """You are SDIE v4 DeepSeek Semantic Structural Classifier.
Classify structural drawing entities. NEVER compute area, volume, or quantities.

Use RAG context: layer knowledge, annotation rules, atlas samples, estimator mappings.

Return JSON:
{
  "classifications": [
    {"component_id": "ENT-00001", "component": "Beam", "confidence": 0.96,
     "evidence": ["Layer Match", "Topology Match"]}
  ]
}

Allowed: """ + ", ".join(ALLOWED)

V5_SYSTEM = """You are a senior structural quantity surveyor, structural estimator, and CAD interpretation specialist.
Your responsibility is structural component identification.
You must classify structural entities using:
Layer names
Geometry
Annotation text
Structural topology
Historical estimator examples
Knowledge base context
Atlas examples

You are forbidden from calculating:
Area
Volume
Concrete
Shuttering

You are only responsible for structural understanding.
When layers are missing, infer component types from geometry, topology, and estimator patterns.
Return confidence scores for every entity.
Flag uncertain entities for review.

Geometry fallback rules:
- Long narrow high aspect ratio connecting columns → Beam
- Small rectangular grid-aligned footprint supporting beams → Column
- Continuous thick wall geometry near core → Shear Wall
- Large enclosed framed region with THK nearby, not wall/core/opening → Slab
- Lift/stair/shaft annotations with enclosure → Lift Core / Stair Core / Shaft
- VOID/CUTOUT/OPENING annotations → Opening

Never classify beams/columns/cores/walls/openings as Slab unless strong THK slab-tag evidence exists.
Exclusion-before-slab: beams, columns, walls, cores, shafts, openings must be identified before any slab region.

Return JSON:
{
  "classifications": [
    {
      "component_id": "ENT-00001",
      "component": "Beam",
      "confidence": 94,
      "review_required": false,
      "evidence": {
        "layer_match": 100,
        "geometry_match": 95,
        "topology_match": 88,
        "annotation_match": 80,
        "atlas_match": 92,
        "kb_match": 70
      },
      "alternatives": []
    }
  ]
}

Allowed components: """ + ", ".join(ALLOWED)

def _is_ambiguous(
    comp: ClassifiedComponent,
    *,
    threshold: float,
    project_id: str,
    profiles: dict | None = None,
) -> bool:
    if comp.component_type == ComponentType.UNKNOWN:
        return True
    if any(e.startswith(("hard_layer:", "layer_profile:")) for e in comp.evidence):
        if comp.confidence >= 82:
            return False
    if comp.confidence < threshold:
        return True
    hints = merged_layer_hints_for_project(project_id, profiles=profiles)
    layer_hint = hints.get(comp.layer or "")
    if layer_hint and layer_hint != ComponentType.SLAB and comp.component_type == ComponentType.SLAB:
        return True
    if layer_hint == ComponentType.SLAB and comp.component_type not in (
        ComponentType.SLAB,
        ComponentType.UNKNOWN,
    ):
        return True
    text = (comp.annotation_features.get("text") or "").upper()
    if "THK" in text and comp.component_type != ComponentType.SLAB:
        return True
    return False


def _apply_deepseek_results(
    classified: list[ClassifiedComponent],
    items: list[dict],
) -> int:
    by_id = {c.component_id: c for c in classified}
    updated = 0
    for item in items:
        cid = item.get("component_id")
        if cid not in by_id:
            continue
        comp = by_id[cid]
        try:
            comp.component_type = ComponentType(item.get("component", comp.component_type.value))
        except ValueError:
            continue
        ds = float(item.get("confidence", 0.75))
        comp.evidence = list(item.get("evidence", [])) + comp.evidence
        comp.confidence_breakdown = score_confidence(
            geometry_score=comp.confidence_breakdown.get("geometry", 50) / 100,
            topology_score=comp.confidence_breakdown.get("topology", 50) / 100,
            graph_score=comp.confidence_breakdown.get("graph", 50) / 100,
            deepseek_score=ds,
        )
        comp.confidence = comp.confidence_breakdown["final"]
        updated += 1
    return updated


def classify_entities_v4(
    entities: list[DrawingEntity],
    *,
    kb: StructuralKnowledgeBase,
    atlas: list[AtlasSample],
    project_id: str,
    enable_deepseek: bool = True,
    deepseek_model: str = "deepseek-chat",
    deepseek_base_url: str = "https://api.deepseek.com",
    batch_size: int = 30,
    ambiguity_threshold: float = 65.0,
) -> tuple[list[ClassifiedComponent], dict[str, Any]]:
    """
    V4: rule baseline → indexed RAG → DeepSeek on ambiguous entities only.
    """
    notes: dict[str, Any] = {"method": "rag_rule_baseline"}
    profiles = load_profiles()
    classified = classify_entities(
        entities, atlas=atlas, project_id=project_id, profiles=profiles
    )
    index: RagIndex = build_rag_index(kb, atlas, project_id)

    ambiguous_ids = {
        c.component_id
        for c in classified
        if _is_ambiguous(
            c,
            threshold=ambiguity_threshold,
            project_id=project_id,
            profiles=profiles,
        )
    }
    notes["ambiguous_count"] = len(ambiguous_ids)
    notes["total_entities"] = len(entities)

    if not enable_deepseek or not get_deepseek_api_key():
        notes["deepseek"] = "skipped_no_key_or_disabled"
        return classified, notes

    if not ambiguous_ids:
        notes["deepseek"] = {"status": "skipped", "reason": "no_ambiguous_entities"}
        notes["method"] = "rag_rule_only"
        return classified, notes

    rag_payload = []
    for entity in entities:
        if entity.entity_id not in ambiguous_ids:
            continue
        baseline = next(c for c in classified if c.component_id == entity.entity_id)
        rag_payload.append(
            {
                "component_id": entity.entity_id,
                "layer": entity.layer,
                "entity_type": entity.entity_type,
                "annotation": entity.text,
                "geometry_features": baseline.geometry_features,
                "rule_baseline": baseline.component_type.value,
                "rule_confidence": baseline.confidence,
                "rag_context": retrieve_rag_context(
                    entity,
                    kb=kb,
                    index=index,
                    project_id=project_id,
                    rule_baseline_type=baseline.component_type.value,
                ),
            }
        )

    updated_total = 0
    notes["deepseek"] = {
        "status": "ok",
        "batches": 0,
        "updated": 0,
        "entities_sent": len(rag_payload),
    }
    for i in range(0, len(rag_payload), batch_size):
        batch = rag_payload[i : i + batch_size]
        user_msg = (
            f"Project: {project_id}\n"
            f"Classify {len(batch)} ambiguous structural entities using RAG context.\n"
            f"Never classify beams/columns/cores/walls/openings as Slab unless "
            f"strong THK slab-tag evidence exists.\n\n"
            f"{json.dumps(batch, indent=2)}"
        )
        try:
            resp = chat_json(
                [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                model=deepseek_model,
                base_url=deepseek_base_url,
            )
        except DeepSeekError as exc:
            logger.warning("V4 DeepSeek classification batch failed: %s", exc)
            notes["deepseek"] = {"status": "error", "error": str(exc)}
            break
        n = _apply_deepseek_results(classified, resp.get("classifications", []))
        updated_total += n
        notes["deepseek"]["batches"] += 1

    notes["deepseek"]["updated"] = updated_total
    notes["method"] = "rag_deepseek_v4_ambiguous"
    return classified, notes


def _apply_v5_baseline_scores(classified: list[ClassifiedComponent]) -> None:
    for comp in classified:
        ev = infer_v5_evidence_from_baseline(comp)
        breakdown = score_v5_confidence(
            layer_score=ev["layer"],
            geometry_score=ev["geometry"],
            topology_score=ev["topology"],
            annotation_score=ev["annotation"],
            atlas_score=ev["atlas"],
            kb_score=ev["knowledge_base"],
        )
        comp.confidence_breakdown = breakdown
        comp.confidence = breakdown["final"]
        comp.review_required = bool(breakdown.get("review_required"))


def _apply_v5_deepseek_results(
    classified: list[ClassifiedComponent],
    items: list[dict],
) -> int:
    by_id = {c.component_id: c for c in classified}
    updated = 0
    for item in items:
        cid = item.get("component_id")
        if cid not in by_id:
            continue
        comp = by_id[cid]
        try:
            comp.component_type = ComponentType(
                item.get("component", comp.component_type.value)
            )
        except ValueError:
            continue

        raw_ev = item.get("evidence") or {}
        if isinstance(raw_ev, dict) and raw_ev:
            breakdown = score_v5_confidence(
                layer_score=float(raw_ev.get("layer_match", 50)) / 100,
                geometry_score=float(raw_ev.get("geometry_match", 50)) / 100,
                topology_score=float(raw_ev.get("topology_match", 50)) / 100,
                annotation_score=float(raw_ev.get("annotation_match", 50)) / 100,
                atlas_score=float(raw_ev.get("atlas_match", 50)) / 100,
                kb_score=float(raw_ev.get("kb_match", 50)) / 100,
            )
        else:
            ds = float(item.get("confidence", 75)) / 100
            ev = infer_v5_evidence_from_baseline(comp)
            ev["layer"] = max(ev["layer"], ds)
            breakdown = score_v5_confidence(
                layer_score=ev["layer"],
                geometry_score=ev["geometry"],
                topology_score=ev["topology"],
                annotation_score=ev["annotation"],
                atlas_score=ev["atlas"],
                kb_score=ev["knowledge_base"],
            )

        comp.confidence_breakdown = breakdown
        comp.confidence = breakdown["final"]
        comp.review_required = bool(
            item.get("review_required", breakdown.get("review_required"))
        )
        alts = item.get("alternatives") or []
        if alts:
            comp.evidence = comp.evidence + [f"alternatives:{','.join(alts[:3])}"]
        comp.evidence = comp.evidence + ["deepseek_v5"]
        updated += 1
    return updated


def classify_entities_v5(
    entities: list[DrawingEntity],
    *,
    kb: StructuralKnowledgeBase,
    atlas: list[AtlasSample],
    project_id: str,
    msp,
    meta: DrawingMeta,
    drawing_name: str,
    annotation_layers: tuple[str, ...] = (),
    enable_deepseek: bool = True,
    deepseek_model: str = "deepseek-chat",
    deepseek_base_url: str = "https://api.deepseek.com",
    batch_size: int = 25,
    ambiguity_threshold: float = 75.0,
) -> tuple[list[ClassifiedComponent], dict[str, Any]]:
    """
    V5: rule baseline → structural graph → topology-enriched DeepSeek reasoning.
    """
    notes: dict[str, Any] = {"method": "v5_rule_baseline"}
    profiles = load_profiles()
    classified = classify_entities(
        entities, atlas=atlas, project_id=project_id, profiles=profiles
    )

    graph = build_structural_graph(classified)
    attach_topology_to_components(classified, graph)
    _apply_v5_baseline_scores(classified)

    drawing_ctx = build_drawing_context(
        meta=meta,
        msp=msp,
        project_id=project_id,
        drawing_name=drawing_name,
    )
    notes["drawing_context"] = drawing_ctx

    index: RagIndex = build_rag_index(kb, atlas, project_id)
    ann_points = collect_annotation_points(msp, annotation_layers)
    classified_by_id = {c.component_id: c for c in classified}

    ambiguous_ids = {
        c.component_id
        for c in classified
        if _is_ambiguous(
            c,
            threshold=ambiguity_threshold,
            project_id=project_id,
            profiles=profiles,
        )
        or c.review_required
    }
    notes["ambiguous_count"] = len(ambiguous_ids)
    notes["total_entities"] = len(entities)
    notes["graph"] = {"nodes": graph.node_count, "edges": graph.edge_count}

    review_before = sum(1 for c in classified if c.review_required)
    notes["review_required_before_deepseek"] = review_before

    if not enable_deepseek or not get_deepseek_api_key():
        notes["deepseek"] = "skipped_no_key_or_disabled"
        notes["method"] = "v5_rule_topology_only"
        return classified, notes

    if not ambiguous_ids:
        notes["deepseek"] = {"status": "skipped", "reason": "no_ambiguous_entities"}
        notes["method"] = "v5_rule_topology_only"
        return classified, notes

    entity_by_id = {e.entity_id: e for e in entities}
    rag_payload = []
    for cid in sorted(ambiguous_ids):
        entity = entity_by_id.get(cid)
        if entity is None:
            continue
        baseline = classified_by_id[cid]
        rag_ctx = retrieve_rag_context(
            entity,
            kb=kb,
            index=index,
            project_id=project_id,
            rule_baseline_type=baseline.component_type.value,
            top_k=5,
        )
        rag_payload.append(
            {
                **enrich_entity_context(
                    entity,
                    baseline,
                    meta=meta,
                    graph=graph,
                    classified_by_id=classified_by_id,
                    nearby_ann=nearby_annotations(entity, ann_points),
                ),
                "few_shot": {
                    "atlas_samples": rag_ctx.get("atlas_samples", [])[:5],
                    "knowledge_base": {
                        "layer_knowledge": rag_ctx.get("layer_knowledge", [])[:5],
                        "annotation_knowledge": rag_ctx.get("annotation_knowledge", [])[:5],
                        "pattern_knowledge": rag_ctx.get("pattern_knowledge", [])[:5],
                        "estimator_mappings": rag_ctx.get("estimator_mappings", [])[:5],
                    },
                },
            }
        )

    updated_total = 0
    notes["deepseek"] = {
        "status": "ok",
        "batches": 0,
        "updated": 0,
        "entities_sent": len(rag_payload),
        "engine": "v5_structural_reasoning",
    }

    geometry_fallback = {
        "beam": "long narrow, high aspect ratio, connects columns",
        "column": "small rectangular, grid aligned, supports beams",
        "shear_wall": "continuous wall, large thickness, core proximity",
        "slab": "large enclosed framed region, THK nearby, not wall/core/opening",
        "lift_core": "core enclosure + lift annotation",
        "stair_core": "stair annotation + flight geometry",
    }

    for i in range(0, len(rag_payload), batch_size):
        batch = rag_payload[i : i + batch_size]
        user_msg = (
            f"SDIE V5 Structural Reasoning — classify {len(batch)} ambiguous entities.\n\n"
            f"DRAWING CONTEXT (never assume scale or units):\n"
            f"{json.dumps(drawing_ctx, indent=2)}\n\n"
            f"GEOMETRY FALLBACK RULES:\n{json.dumps(geometry_fallback, indent=2)}\n\n"
            f"ENTITIES (with topology, annotations, few-shot atlas/KB):\n"
            f"{json.dumps(batch, indent=2)}"
        )
        try:
            resp = chat_json(
                [
                    {"role": "system", "content": V5_SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                model=deepseek_model,
                base_url=deepseek_base_url,
            )
        except DeepSeekError as exc:
            logger.warning("V5 DeepSeek classification batch failed: %s", exc)
            notes["deepseek"] = {"status": "error", "error": str(exc)}
            break
        n = _apply_v5_deepseek_results(classified, resp.get("classifications", []))
        updated_total += n
        notes["deepseek"]["batches"] += 1

    graph = build_structural_graph(classified)
    attach_topology_to_components(classified, graph)
    notes["deepseek"]["updated"] = updated_total
    notes["graph_after"] = {"nodes": graph.node_count, "edges": graph.edge_count}
    notes["review_required_after"] = sum(1 for c in classified if c.review_required)
    notes["method"] = "v5_rag_topology_deepseek"
    return classified, notes
