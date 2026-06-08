"""Ground-truth slab matching for validation overlays and scripts."""
from __future__ import annotations

import re
from itertools import combinations
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
        aspect = None
        if length and breadth and breadth > 0:
            aspect = max(length, breadth) / min(length, breadth)
        slabs.append(
            {
                "id": desc.strip().upper(),
                "length_m": length,
                "breadth_m": breadth,
                "thickness_m": thickness,
                "area_m2": area,
                "concrete_m3": conc,
                "aspect_ratio": aspect,
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


def _model_aspect_ratio(slab: dict[str, Any]) -> float | None:
    bounds = slab.get("bounds_cm")
    if not bounds or len(bounds) < 4:
        return None
    minx, miny, maxx, maxy = bounds[:4]
    w = abs(maxx - minx) / 100.0
    h = abs(maxy - miny) / 100.0
    if w <= 0 or h <= 0:
        return None
    return max(w, h) / min(w, h)


def _area_err_pct(expected: float, actual: float) -> float:
    if expected <= 0:
        return 100.0
    return abs(actual - expected) / expected * 100.0


def _aspect_err_pct(expected_ar: float | None, actual_ar: float | None) -> float:
    if expected_ar is None or actual_ar is None or expected_ar <= 0:
        return 50.0
    return abs(actual_ar - expected_ar) / expected_ar * 100.0


def _match_score(
    exp: dict[str, Any],
    act: dict[str, Any],
    *,
    area_weight: float = 0.65,
    aspect_weight: float = 0.35,
) -> tuple[float, float, float]:
    """Lower is better. Returns (combined_score, area_err%, aspect_err%)."""
    area_err = _area_err_pct(exp["area_m2"], act["area_m2"])
    aspect_err = _aspect_err_pct(exp.get("aspect_ratio"), _model_aspect_ratio(act))
    combined = area_weight * area_err + aspect_weight * aspect_err
    return combined, area_err, aspect_err


def _is_strong_match(area_err: float, aspect_err: float) -> bool:
    if area_err <= 5.0:
        return True
    if area_err <= 10.0 and aspect_err <= 20.0:
        return True
    if area_err <= 8.0 and aspect_err <= 12.0:
        return True
    return False


def greedy_match(
    expected: list[dict[str, Any]],
    actual: list[dict[str, Any]],
    *,
    tol_pct: float = 20.0,
) -> tuple[list[tuple[dict, dict | None, float | None]], list[dict]]:
    """Match GT slabs to model polygons — global best-pair first (avoids order bias)."""
    candidates: list[tuple[float, int, int, float]] = []
    for ei, exp in enumerate(expected):
        for ai, act in enumerate(actual):
            combined, area_err, _aspect_err = _match_score(exp, act)
            if area_err <= tol_pct:
                candidates.append((combined, ei, ai, area_err))

    candidates.sort(key=lambda x: x[0])
    used_exp: set[int] = set()
    used_act: set[int] = set()
    paired: dict[int, tuple[dict, float]] = {}

    for _combined, ei, ai, area_err in candidates:
        if ei in used_exp or ai in used_act:
            continue
        used_exp.add(ei)
        used_act.add(ai)
        paired[ei] = (actual[ai], area_err)

    matches: list[tuple[dict, dict | None, float | None]] = []
    for ei, exp in enumerate(expected):
        if ei in paired:
            act, area_err = paired[ei]
            matches.append((exp, act, area_err))
            continue
        nearest_err = min(
            (_match_score(exp, act)[1] for act in actual),
            default=None,
        )
        matches.append((exp, None, nearest_err))

    unmatched_actual = [a for i, a in enumerate(actual) if i not in used_act]
    return matches, unmatched_actual


def _partition_match(
    expected: list[dict[str, Any]],
    actual: list[dict[str, Any]],
    *,
    tol_pct: float = 12.0,
    max_group: int = 3,
) -> tuple[
    list[tuple[dict, list[dict], float]],
    list[dict],
    list[dict],
]:
    """
    Match one GT slab to a group of model slabs whose areas sum correctly.
    Handles estimator bays that were split by the grid detector.
    """
    one_to_one, extra = greedy_match(expected, actual, tol_pct=25.0)
    matched_gt: list[tuple[dict, list[dict], float]] = []
    unmatched_gt: list[dict] = []
    used_ids: set[str] = set()

    for exp, act, err in one_to_one:
        if act is not None:
            matched_gt.append((exp, [act], err or 0.0))
            used_ids.add(act["slab_id"])
        else:
            unmatched_gt.append(exp)

    pool = [a for a in actual if a["slab_id"] not in used_ids]
    still_unmatched: list[dict] = []

    for exp in unmatched_gt:
        best_group: list[dict] | None = None
        best_err = 1e9
        for size in range(2, min(max_group, len(pool)) + 1):
            for group in combinations(pool, size):
                total = sum(g["area_m2"] for g in group)
                err = _area_err_pct(exp["area_m2"], total)
                if err <= tol_pct and err < best_err:
                    best_err = err
                    best_group = list(group)
        if best_group:
            matched_gt.append((exp, best_group, best_err))
            for g in best_group:
                pool.remove(g)
                used_ids.add(g["slab_id"])
        else:
            still_unmatched.append(exp)

    extra_final = [a for a in actual if a["slab_id"] not in used_ids]
    return matched_gt, still_unmatched, extra_final


def annotate_slabs_with_gt(
    slabs: list[dict[str, Any]],
    gt: list[dict[str, Any]],
    *,
    match_tol_pct: float = 25.0,
    partition_tol_pct: float = 12.0,
    use_partition_matching: bool = True,
) -> dict[str, Any]:
    """
    Return overlay context: per-slab GT status plus summary lists.

    Status values: matched | weak | extra | partition
    """
    by_slab_id: dict[str, dict[str, Any]] = {}
    for slab in slabs:
        by_slab_id[slab["slab_id"]] = {
            "gt_status": "extra",
            "gt_id": None,
            "gt_area_err_pct": None,
            "gt_expected_area_m2": None,
        }

    matched: list[dict[str, Any]] = []
    weak: list[dict[str, Any]] = []
    missed: list[dict[str, Any]] = []
    partition: list[dict[str, Any]] = []

    if use_partition_matching:
        groups, still_missed, extra = _partition_match(
            gt, slabs, tol_pct=partition_tol_pct
        )
        for exp, acts, err in groups:
            if len(acts) == 1:
                act = acts[0]
                _, area_err, aspect_err = _match_score(exp, act)
                status = (
                    "matched"
                    if _is_strong_match(area_err, aspect_err)
                    else "weak"
                )
                by_slab_id[act["slab_id"]] = {
                    "gt_status": status,
                    "gt_id": exp["id"],
                    "gt_area_err_pct": round(area_err, 1),
                    "gt_expected_area_m2": exp["area_m2"],
                }
                entry = {
                    "gt_id": exp["id"],
                    "slab_id": act["slab_id"],
                    "expected_area_m2": exp["area_m2"],
                    "actual_area_m2": act["area_m2"],
                    "err_pct": round(area_err, 1),
                    "aspect_err_pct": round(aspect_err, 1),
                }
                if status == "matched":
                    matched.append(entry)
                else:
                    weak.append(entry)
            else:
                total = sum(a["area_m2"] for a in acts)
                for act in acts:
                    by_slab_id[act["slab_id"]] = {
                        "gt_status": "partition",
                        "gt_id": exp["id"],
                        "gt_area_err_pct": round(err, 1),
                        "gt_expected_area_m2": exp["area_m2"],
                        "gt_partition_group": [a["slab_id"] for a in acts],
                    }
                partition.append(
                    {
                        "gt_id": exp["id"],
                        "slab_ids": [a["slab_id"] for a in acts],
                        "expected_area_m2": exp["area_m2"],
                        "actual_area_m2": round(total, 3),
                        "err_pct": round(err, 1),
                    }
                )
                if _is_strong_match(err, 0.0):
                    matched.append(partition[-1])
                else:
                    weak.append(partition[-1])

        for exp in still_missed:
            nearest = (
                min(_match_score(exp, a)[1] for a in slabs) if slabs else None
            )
            missed.append(
                {
                    "gt_id": exp["id"],
                    "expected_area_m2": exp["area_m2"],
                    "length_m": exp.get("length_m"),
                    "breadth_m": exp.get("breadth_m"),
                    "nearest_err_pct": round(nearest, 1) if slabs else None,
                }
            )
        extra_entries = [
            {
                "slab_id": s["slab_id"],
                "area_m2": s["area_m2"],
                "strategy": s.get("strategy"),
                "thickness_mm": s.get("thickness_mm"),
            }
            for s in extra
        ]
    else:
        matches, extra = greedy_match(gt, slabs, tol_pct=match_tol_pct)
        extra_entries = [
            {
                "slab_id": s["slab_id"],
                "area_m2": s["area_m2"],
                "strategy": s.get("strategy"),
                "thickness_mm": s.get("thickness_mm"),
            }
            for s in extra
        ]
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
            _, area_err, aspect_err = _match_score(exp, act)
            status = (
                "matched" if _is_strong_match(area_err, aspect_err) else "weak"
            )
            by_slab_id[act["slab_id"]] = {
                "gt_status": status,
                "gt_id": exp["id"],
                "gt_area_err_pct": round(area_err, 1),
                "gt_expected_area_m2": exp["area_m2"],
            }
            entry = {
                "gt_id": exp["id"],
                "slab_id": act["slab_id"],
                "expected_area_m2": exp["area_m2"],
                "actual_area_m2": act["area_m2"],
                "err_pct": round(area_err, 1),
            }
            if status == "matched":
                matched.append(entry)
            else:
                weak.append(entry)

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
            "partition_match_count": len(partition),
        },
        "matched": matched,
        "weak": weak,
        "missed": missed,
        "extra": extra_entries,
        "partition": partition,
    }
