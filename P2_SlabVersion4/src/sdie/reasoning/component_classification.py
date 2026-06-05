from __future__ import annotations

import json
import logging
from typing import Any

from sdie.classification.types import ClassifiedComponent, ComponentType
from sdie.confidence.scorer import score_confidence
from sdie.reasoning.deepseek_client import DeepSeekError, chat_json

logger = logging.getLogger(__name__)

ALLOWED_TYPES = [t.value for t in ComponentType if t != ComponentType.UNKNOWN]

SYSTEM_PROMPT = """You are a structural drawing component classifier for SDIE v3.3.
You may ONLY classify components. You must NOT compute area, volume, or quantities.

Return JSON:
{
  "classifications": [
    {"component_id": "ENT-00001", "classification": "Beam", "confidence": 0.92, "evidence": ["reason"]}
  ]
}

Allowed classifications: """ + ", ".join(ALLOWED_TYPES)


def refine_ambiguous_components(
    ambiguous: list[ClassifiedComponent],
    *,
    drawing_name: str,
    deepseek_model: str = "auto",
    deepseek_base_url: str = "https://api.deepseek.com",
    max_items: int = 40,
) -> tuple[list[ClassifiedComponent], dict[str, Any]]:
    """PART 7 — DeepSeek resolves ambiguous component classifications only."""
    notes: dict[str, Any] = {"status": "skipped", "updated": 0}
    if not ambiguous:
        notes["status"] = "no_ambiguous"
        return [], notes

    batch = ambiguous[:max_items]
    payload = [
        {
            "component_id": c.component_id,
            "layer": c.layer,
            "entity_type": c.entity_type,
            "current_type": c.component_type.value,
            "confidence": c.confidence,
            "annotation": c.annotation_text,
            "geometry_features": c.geometry_features,
            "evidence": c.evidence,
        }
        for c in batch
    ]
    user_msg = (
        f"Drawing: {drawing_name}\n"
        f"Ambiguous components ({len(batch)}):\n"
        f"{json.dumps(payload, indent=2)}\n"
        "Classify each component. Use evidence from layer, annotation, and geometry."
    )

    try:
        resp = chat_json(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            model=deepseek_model,
            base_url=deepseek_base_url,
        )
    except DeepSeekError as exc:
        logger.warning("DeepSeek component classification failed: %s", exc)
        notes["status"] = "error"
        notes["error"] = str(exc)
        return [], notes

    by_id = {c.component_id: c for c in batch}
    updated: list[ClassifiedComponent] = []
    for item in resp.get("classifications", []):
        cid = item.get("component_id")
        if cid not in by_id:
            continue
        comp = by_id[cid]
        new_type = item.get("classification", comp.component_type.value)
        try:
            comp.component_type = ComponentType(new_type)
        except ValueError:
            continue
        ds_conf = float(item.get("confidence", 0.7))
        comp.evidence = list(item.get("evidence", [])) + comp.evidence
        comp.confidence_breakdown = score_confidence(
            geometry_score=comp.confidence_breakdown.get("geometry", 50) / 100,
            topology_score=comp.confidence_breakdown.get("topology", 50) / 100,
            graph_score=comp.confidence_breakdown.get("graph", 50) / 100,
            deepseek_score=ds_conf,
        )
        comp.confidence = comp.confidence_breakdown["final"]
        updated.append(comp)

    notes["status"] = "ok"
    notes["updated"] = len(updated)
    return updated, notes
