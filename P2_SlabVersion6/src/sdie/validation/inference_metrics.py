"""Inference-quality metrics for raw DXF runs (no workbook GT required)."""
from __future__ import annotations

from typing import Any

from sdie.classification.types import ClassifiedComponent, ComponentType
from sdie.validation.component_gt import QUANTITY_PHASE_TYPES


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def build_inference_metrics(
    classified: list[ClassifiedComponent],
    *,
    detection_notes: dict[str, Any],
    totals: dict[str, Any],
    benchmark: dict[str, Any],
    review_threshold: float = 75.0,
) -> dict[str, Any]:
    """
    Metrics for raw/generic inference when tagged entity GT is unavailable.

    Entity accuracy (F1 vs teach drawings) is measured separately via
    evaluate_component_classification.py --slab-beam-only.
    """
    n = len(classified)
    by_type: dict[str, int] = {}
    conf_by_type: dict[str, list[float]] = {}
    for comp in classified:
        label = comp.component_type.value
        by_type[label] = by_type.get(label, 0) + 1
        conf_by_type.setdefault(label, []).append(float(comp.confidence))

    slab_beam = [c for c in classified if c.component_type.value in QUANTITY_PHASE_TYPES]
    low_conf = sum(1 for c in classified if c.confidence < review_threshold)
    review_n = sum(1 for c in classified if c.review_required)
    unknown_n = by_type.get(ComponentType.UNKNOWN.value, 0)

    cls_notes = detection_notes.get("classification") or {}
    deepseek = cls_notes.get("deepseek") if isinstance(cls_notes.get("deepseek"), dict) else {}

    per_type_conf: dict[str, Any] = {}
    for ctype, confs in sorted(conf_by_type.items()):
        per_type_conf[ctype] = {
            "count": len(confs),
            "mean_confidence": _mean(confs),
            "low_confidence_pct": round(
                100.0 * sum(1 for x in confs if x < review_threshold) / len(confs),
                1,
            ),
        }

    phase_conf = [float(c.confidence) for c in slab_beam]
    metrics: dict[str, Any] = {
        "split": "test",
        "phase": "slab_beam_quantity",
        "metric_type": "inference_proxy",
        "ground_truth": {
            "workbook_benchmark": benchmark.get("status", "unknown"),
            "train_accuracy_eval": (
                "scripts/evaluate_ml_project.py --train-only "
                "(entity F1 on Tagged Files_2)"
            ),
            "test_accuracy_eval": (
                "scripts/evaluate_ml_project.py --test-only "
                "(paired teach reference on Raw files_2)"
            ),
        },
        "classification": {
            "entities_total": n,
            "by_type": by_type,
            "slab_beam_entity_count": len(slab_beam),
            "slab_beam_share_pct": round(100.0 * len(slab_beam) / max(1, n), 1),
            "mean_confidence_all": _mean([float(c.confidence) for c in classified]),
            "mean_confidence_slab_beam": _mean(phase_conf),
            "low_confidence_count": low_conf,
            "low_confidence_pct": detection_notes.get("low_confidence_pct"),
            "review_required_count": review_n,
            "review_required_pct": round(100.0 * review_n / max(1, n), 1),
            "unknown_count": unknown_n,
            "unknown_pct": round(100.0 * unknown_n / max(1, n), 1),
            "ambiguous_count": cls_notes.get("ambiguous_count"),
            "deepseek_updated": deepseek.get("updated"),
            "per_type": per_type_conf,
        },
        "quantities": {
            "slab_count": totals.get("slab_count"),
            "slab_area_m2": totals.get("area_m2"),
            "slab_concrete_m3": totals.get("slab_concrete_m3", totals.get("concrete_m3")),
            "beam_count": totals.get("beam_count"),
            "beam_total_length_m": totals.get("beam_total_length_m"),
            "beam_concrete_m3": totals.get("beam_concrete_m3"),
            "total_concrete_m3": totals.get("concrete_m3"),
            "total_shuttering_m2": totals.get("shuttering_m2"),
        },
        "quality_targets": {
            "mean_confidence_slab_beam_min": 75.0,
            "low_confidence_pct_max": 10.0,
            "unknown_pct_max": 5.0,
        },
    }

    slab_beam_conf = metrics["classification"]["mean_confidence_slab_beam"]
    low_pct = metrics["classification"]["low_confidence_pct"]
    unknown_pct = metrics["classification"]["unknown_pct"]
    checks: list[dict[str, Any]] = []
    if slab_beam_conf is not None:
        checks.append(
            {
                "check": "slab_beam_mean_confidence",
                "value": slab_beam_conf,
                "target": ">= 75",
                "pass": slab_beam_conf >= 75.0,
            }
        )
    if low_pct is not None:
        checks.append(
            {
                "check": "low_confidence_pct",
                "value": low_pct,
                "target": "<= 10",
                "pass": low_pct <= 10.0,
            }
        )
    if unknown_pct is not None:
        checks.append(
            {
                "check": "unknown_pct",
                "value": unknown_pct,
                "target": "<= 5",
                "pass": unknown_pct <= 5.0,
            }
        )
    metrics["quality_checks"] = checks
    metrics["quality_pass"] = all(c["pass"] for c in checks) if checks else None
    return metrics
