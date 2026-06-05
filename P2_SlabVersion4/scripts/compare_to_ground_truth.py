"""Compare pipeline results JSON to ground truth expected_total."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def within(actual: float, target: float, pct: float) -> bool:
    if target == 0:
        return actual == 0
    return abs(actual - target) / target * 100 <= pct


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: compare_to_ground_truth.py <results.json> <ground_truth.json>")
        return 1

    results = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    gt = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    expected = gt["expected_total"]
    tol = gt.get("regression_config", {}).get("area_tolerance_pct", 3)
    totals = results["totals"]

    report = {}
    for key in ("area_m2", "concrete_m3", "shuttering_m2"):
        if expected.get(key) is None:
            continue
        act = totals[key]
        tgt = expected[key]
        delta_pct = (act - tgt) / tgt * 100 if tgt else 0
        report[key] = {
            "actual": act,
            "expected": tgt,
            "delta_pct": round(delta_pct, 3),
            "within_tolerance": within(act, tgt, tol),
        }

    count_tol = gt.get("regression_config", {}).get("slab_count_tolerance")
    if expected.get("slab_count") is not None:
        act_n = totals.get("slab_count", 0)
        tgt_n = int(expected["slab_count"])
        delta_n = act_n - tgt_n
        if count_tol is not None:
            count_ok = abs(delta_n) <= int(count_tol)
        else:
            count_ok = act_n == tgt_n
        report["slab_count"] = {
            "actual": act_n,
            "expected": tgt_n,
            "delta": delta_n,
            "within_tolerance": count_ok,
        }

    passed = all(v["within_tolerance"] for v in report.values())
    print(json.dumps({"passed": passed, "tolerance_pct": tol, "metrics": report}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
