"""Validate LGF slab totals against expected_total (±3%)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GT_PATH = ROOT / "data" / "ground_truth" / "Slab-02_Layer_Try.json"


def within(actual: float, target: float, pct: float) -> bool:
    if target == 0:
        return actual == 0
    return abs(actual - target) / target * 100 <= pct


def main() -> int:
    data = json.loads(GT_PATH.read_text(encoding="utf-8"))
    lgf = next(f for f in data["floor_zones"] if f["floor_id"] == "LGF")
    expected = lgf["expected_total"]
    tol = data["regression_config"]["area_tolerance_pct"]
    slabs = lgf.get("slabs") or []

    totals = {
        "area_m2": sum(s["area_m2"] for s in slabs),
        "concrete_m3": sum(s["concrete_m3"] for s in slabs),
        "shuttering_m2": sum(s["shuttering_m2"] for s in slabs),
    }

    ok = all(
        within(totals[k], expected[k], tol)
        for k in ("area_m2", "concrete_m3", "shuttering_m2")
        if expected.get(k) is not None
    )
    print(json.dumps({"totals": totals, "expected": expected, "passed": ok}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
