from __future__ import annotations

from typing import Any


def accuracy_pct(actual: float, expected: float) -> float | None:
    if expected == 0:
        return 100.0 if actual == 0 else 0.0
    error_pct = abs(actual - expected) / expected * 100
    return round(max(0.0, 100.0 - error_pct), 3)


def within_tolerance(actual: float, expected: float, tolerance_pct: float) -> bool:
    if expected == 0:
        return actual == 0
    return abs(actual - expected) / expected * 100 <= tolerance_pct


def compute_benchmark_report(
    totals: dict[str, Any],
    ground_truth: dict[str, Any] | None,
    *,
    target_accuracy_pct: float = 95.0,
) -> dict[str, Any]:
    """PART 10 — benchmark metrics vs estimator workbook ground truth."""
    if not ground_truth:
        return {"status": "no_ground_truth", "target_accuracy_pct": target_accuracy_pct}

    expected = ground_truth.get("expected_total", ground_truth)
    tol = ground_truth.get("regression_config", {}).get("area_tolerance_pct", 3)
    metrics: dict[str, Any] = {}

    for key, label in (
        ("area_m2", "area_accuracy"),
        ("concrete_m3", "concrete_accuracy"),
        ("shuttering_m2", "shuttering_accuracy"),
    ):
        if expected.get(key) is None:
            continue
        act = float(totals.get(key, 0))
        exp = float(expected[key])
        acc = accuracy_pct(act, exp)
        metrics[label] = {
            "actual": act,
            "expected": exp,
            "accuracy_pct": acc,
            "within_tolerance": within_tolerance(act, exp, tol),
            "meets_target_95": acc is not None and acc >= target_accuracy_pct,
        }

    if expected.get("slab_count") is not None:
        act_n = int(totals.get("slab_count", 0))
        exp_n = int(expected["slab_count"])
        count_tol = ground_truth.get("regression_config", {}).get("slab_count_tolerance")
        if count_tol is not None:
            count_ok = abs(act_n - exp_n) <= int(count_tol)
        else:
            count_ok = act_n == exp_n
        metrics["slab_count"] = {
            "actual": act_n,
            "expected": exp_n,
            "within_tolerance": count_ok,
        }

    thickness_samples = ground_truth.get("slabs") or []
    if thickness_samples and totals.get("slab_count"):
        metrics["thickness_accuracy"] = {
            "note": "per-slab thickness compare requires slab-level ground truth",
            "sample_count": len(thickness_samples),
        }

    acc_values = [
        m["accuracy_pct"]
        for m in metrics.values()
        if isinstance(m, dict) and "accuracy_pct" in m
    ]
    overall = round(sum(acc_values) / len(acc_values), 3) if acc_values else None

    return {
        "status": "computed",
        "target_accuracy_pct": target_accuracy_pct,
        "tolerance_pct": tol,
        "overall_accuracy_pct": overall,
        "meets_target_95": overall is not None and overall >= target_accuracy_pct,
        "metrics": metrics,
    }
