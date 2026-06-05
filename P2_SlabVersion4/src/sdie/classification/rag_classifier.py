from __future__ import annotations

import json
import logging
from typing import Any

from sdie.atlas.schema import AtlasSample
from sdie.classification.classifier import DEFAULT_LAYER_HINTS, classify_entity
from sdie.classification.types import ClassifiedComponent, ComponentType
from sdie.confidence.scorer import score_confidence
from sdie.ingestion.entity_extractor import DrawingEntity
from sdie.rag.index import RagIndex
from sdie.rag.retriever import build_rag_index, retrieve_rag_context
from sdie.rag.schema import StructuralKnowledgeBase
from sdie.reasoning.deepseek_client import DeepSeekError, chat_json
from sdie.reasoning.env import get_deepseek_api_key

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

def _is_ambiguous(comp: ClassifiedComponent, *, threshold: float) -> bool:
    if comp.component_type == ComponentType.UNKNOWN:
        return True
    if comp.confidence < threshold:
        return True
    layer_hint = DEFAULT_LAYER_HINTS.get(comp.layer or "")
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
    classified = [classify_entity(e, atlas=atlas) for e in entities]
    index: RagIndex = build_rag_index(kb, atlas, project_id)

    ambiguous_ids = {
        c.component_id
        for c in classified
        if _is_ambiguous(c, threshold=ambiguity_threshold)
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
