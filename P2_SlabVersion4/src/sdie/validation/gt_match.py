"""Ground-truth slab matching for validation overlays and scripts."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import openpyxl


def _num(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def load_gt_xlsx(path: Path) -> list[dict[str, Any]]:
    """Load estimator GT slabs from TrustOffice-style Excel workbook."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Sheet1"]
    slabs: list[dict[str, Any]] = []
    for row in ws.iter_rows(min_row=3, values_only=True):
        if not row or not isinstance(row[2], (int, float)):
            continue
        desc = row[3]
        if not isinstance(desc, str) or not re.match(r"^S\d+", desc.strip(), re.I):
            continue
        length = _num(row[5])
        breadth = _num(row[6])
        thickness = _num(row[7])
        conc = _num(row[8])
        shut = _num(row[9])
        area = shut if shut else (length * breadth if length and breadth else None)
        if area is None:
            continue
        slabs.append(
            {
                "id": desc.strip().upper(),
                "length_m": length,
                "breadth_m": breadth,
                "thickness_m": thickness,
                "area_m2": area,
                "concrete_m3": conc,
            }
        )
    wb.close()
    return slabs


def find_gt_xlsx_for_stem(stem: str, project_root: Path) -> Path | None:
    """Resolve TestGT Excel path from a LayerTest drawing stem when present."""
    base = stem.split("_LayerTest")[0]
    candidate = (
        project_root
        / "Data Source"
        / "Ground Truths"
        / "TestGT"
        / f"{base}_ExpectedOutput.xlsx"
    )
    return candidate if candidate.exists() else None


def greedy_match(
    expected: list[dict[str, Any]],
    actual: list[dict[str, Any]],
    *,
    tol_pct: float = 20.0,
) -> tuple[list[tuple[dict, dict | None, float | None]], list[dict]]:
    """Match GT slabs to model polygons by nearest area."""
    used: set[int] = set()
    matches: list[tuple[dict, dict | None, float | None]] = []
    for exp in expected:
        best: tuple[int, dict] | None = None
        best_err = 1e9
        for i, act in enumerate(actual):
            if i in used:
                continue
            err = abs(act["area_m2"] - exp["area_m2"]) / exp["area_m2"] * 100
            if err < best_err:
                best_err = err
                best = (i, act)
        if best and best_err <= tol_pct:
            used.add(best[0])
            matches.append((exp, best[1], best_err))
        else:
            matches.append((exp, None, best_err if best else None))
    unmatched_actual = [a for i, a in enumerate(actual) if i not in used]
    return matches, unmatched_actual


def annotate_slabs_with_gt(
    slabs: list[dict[str, Any]],
    gt: list[dict[str, Any]],
    *,
    match_tol_pct: float = 20.0,
    good_tol_pct: float = 5.0,
) -> dict[str, Any]:
    """
    Return overlay context: per-slab GT status plus summary lists.

    Status values: matched | weak | extra
    """
    matches, extra = greedy_match(gt, slabs, tol_pct=match_tol_pct)
    by_slab_id: dict[str, dict[str, Any]] = {}
    for slab in slabs:
        by_slab_id[slab["slab_id"]] = {
            "gt_status": "extra",
            "gt_id": None,
            "gt_area_err_pct": None,
            "gt_expected_area_m2": None,
        }

    missed: list[dict[str, Any]] = []
    weak: list[dict[str, Any]] = []
    matched: list[dict[str, Any]] = []

    for exp, act, err in matches:
        if act is None:
            missed.append(
                {
                    "gt_id": exp["id"],
                    "expected_area_m2": exp["area_m2"],
                    "length_m": exp.get("length_m"),
                    "breadth_m": exp.get("breadth_m"),
                    "nearest_err_pct": err,
                }
            )
            continue
        status = "matched" if err is not None and err <= good_tol_pct else "weak"
        by_slab_id[act["slab_id"]] = {
            "gt_status": status,
            "gt_id": exp["id"],
            "gt_area_err_pct": round(err, 1) if err is not None else None,
            "gt_expected_area_m2": exp["area_m2"],
        }
        entry = {
            "gt_id": exp["id"],
            "slab_id": act["slab_id"],
            "expected_area_m2": exp["area_m2"],
            "actual_area_m2": act["area_m2"],
            "err_pct": round(err, 1) if err is not None else None,
        }
        if status == "matched":
            matched.append(entry)
        else:
            weak.append(entry)

    extra_entries = [
        {
            "slab_id": s["slab_id"],
            "area_m2": s["area_m2"],
            "strategy": s.get("strategy"),
            "thickness_mm": s.get("thickness_mm"),
        }
        for s in extra
    ]

    annotated = []
    for slab in slabs:
        ann = dict(slab)
        ann.update(by_slab_id.get(slab["slab_id"], {}))
        annotated.append(ann)

    return {
        "slabs": annotated,
        "summary": {
            "gt_count": len(gt),
            "matched_count": len(matched),
            "weak_count": len(weak),
            "missed_count": len(missed),
            "extra_count": len(extra_entries),
        },
        "matched": matched,
        "weak": weak,
        "missed": missed,
        "extra": extra_entries,
    }
