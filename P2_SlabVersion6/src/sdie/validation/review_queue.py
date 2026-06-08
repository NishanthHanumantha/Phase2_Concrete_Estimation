from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sdie.classification.types import ClassifiedComponent, ComponentType

ALLOWED = [t.value for t in ComponentType]


def _suggest_alternatives(comp: ClassifiedComponent) -> list[str]:
    current = comp.component_type.value
    alts: list[str] = []
    layer = (comp.layer or "").upper()
    ann = comp.annotation_features or {}

    if current == "Beam" and comp.graph_features.get("connected_columns", 0) == 0:
        alts.extend(["Shear Wall", "Structural Wall"])
    if current in ("Shear Wall", "Structural Wall") and comp.geometry_features.get("aspect_ratio", 0) >= 4:
        alts.append("Beam")
    if current == "Column" and (comp.geometry_features.get("aspect_ratio") or 0) >= 3:
        alts.append("Beam")
    if ann.get("has_thk") and current != "Slab":
        alts.append("Slab")
    if "WALL" in layer and current == "Beam":
        alts.append("Shear Wall")
    if "COL" in layer and current != "Column":
        alts.append("Column")
    if "BEAM" in layer and current != "Beam":
        alts.append("Beam")

    return [a for a in dict.fromkeys(alts) if a != current and a in ALLOWED][:3]


def build_review_entry(comp: ClassifiedComponent) -> dict[str, Any]:
    evidence = comp.confidence_breakdown.get("evidence") or {}
    if not evidence and comp.confidence_breakdown:
        evidence = {
            k: v
            for k, v in comp.confidence_breakdown.items()
            if k not in ("final", "weights", "review_required", "status")
        }
    return {
        "entity_id": comp.component_id,
        "classification": comp.component_type.value,
        "confidence": round(comp.confidence, 2),
        "review_required": comp.review_required,
        "layer": comp.layer,
        "evidence": evidence,
        "rule_evidence": comp.evidence[:8],
        "alternatives": _suggest_alternatives(comp),
    }


def build_review_queue(
    classified: list[ClassifiedComponent],
    *,
    review_threshold: float = 75.0,
    force_queue_threshold: float = 60.0,
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    queued_ids: set[str] = set()
    warning_count = 0
    for comp in classified:
        if comp.confidence < 90.0 and comp.confidence >= review_threshold:
            warning_count += 1
        needs_queue = (
            comp.review_required
            or comp.confidence < review_threshold
            or comp.confidence < force_queue_threshold
        )
        if needs_queue and comp.component_id not in queued_ids:
            entries.append(build_review_entry(comp))
            queued_ids.add(comp.component_id)

    entries.sort(key=lambda e: e["confidence"])
    low_conf = [c for c in classified if c.confidence < review_threshold]
    return {
        "review_count": len(entries),
        "warning_count": warning_count,
        "total_entities": len(classified),
        "low_confidence_pct": round(100.0 * len(low_conf) / max(1, len(classified)), 2),
        "thresholds": {
            "auto_accept": 90.0,
            "warning": 75.0,
            "review": review_threshold,
            "force_queue": force_queue_threshold,
        },
        "entities": entries,
    }


def write_review_queue(
    output_dir: Path,
    classified: list[ClassifiedComponent],
    *,
    stem: str,
    review_threshold: float = 75.0,
    force_queue_threshold: float = 60.0,
) -> Path:
    payload = build_review_queue(
        classified,
        review_threshold=review_threshold,
        force_queue_threshold=force_queue_threshold,
    )
    path = output_dir / f"{stem}_review_queue.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
