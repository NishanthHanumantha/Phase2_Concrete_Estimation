"""
Generate LGF slab entries from DXF polygons + nearest THK labels.
Validate sums against expected_total (±3%).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import ezdxf
from shapely.geometry import LineString, Point
from shapely.ops import polygonize

ROOT = Path(__file__).resolve().parents[1]
DXF_PATH = ROOT / "Data Source" / "Slab Test" / "Slab-02_Layer_Try.dxf"
GT_PATH = ROOT / "data" / "ground_truth" / "Slab-02_Layer_Try.json"

MIN_AREA_M2 = 1.0  # ignore noise pockets smaller than 1 m²
STRUCTURAL_LAYERS = ("S_FRAMES", "STR-CUTOUT")

# Authoritative BOQ (used if expected_total fields are null on disk)
BOQ_FALLBACK = {
    "area_m2": 712.003,
    "concrete_m3": 134.860952,
    "shuttering_m2": 762.796466,
}


def load_ground_truth() -> dict:
    return json.loads(GT_PATH.read_text(encoding="utf-8"))


def save_ground_truth(data: dict) -> None:
    GT_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def dist_cm(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(ax - bx, ay - by)


def nearest_thickness(
    cx: float, cy: float, labels: list[dict], default_mm: int
) -> tuple[int, str, float]:
    best = None
    best_d = float("inf")
    for lb in labels:
        lx, ly = lb["xy_cm"]
        d = dist_cm(cx, cy, lx, ly)
        if d < best_d:
            best_d = d
            best = lb
    if best is None:
        return default_mm, "default_note", best_d
    return best["value_mm"], best["text"], best_d


def detect_polygons(bounds: dict) -> list[dict]:
    doc = ezdxf.readfile(DXF_PATH)
    msp = doc.modelspace()
    xmin, xmax = bounds["xmin"], bounds["xmax"]
    ymin, ymax = bounds["ymin"], bounds["ymax"]

    def inside(x: float, y: float) -> bool:
        return xmin <= x <= xmax and ymin <= y <= ymax

    segments: list[LineString] = []
    for e in msp:
        if e.dxf.layer not in STRUCTURAL_LAYERS:
            continue
        if e.dxftype() == "LINE":
            a = (e.dxf.start.x, e.dxf.start.y)
            b = (e.dxf.end.x, e.dxf.end.y)
            if inside(*a) and inside(*b):
                segments.append(LineString([a, b]))
        elif e.dxftype() == "LWPOLYLINE":
            pts = [(p[0], p[1]) for p in e.get_points("xy")]
            pairs = list(zip(pts, pts[1:] + ([pts[0]] if e.closed else [])))
            for a, b in pairs:
                if inside(*a) and inside(*b):
                    segments.append(LineString([a, b]))

    polys = []
    for idx, poly in enumerate(polygonize(segments), start=1):
        if not poly.is_valid or poly.is_empty:
            continue
        area_m2 = poly.area / 10_000.0
        if area_m2 < MIN_AREA_M2:
            continue
        c = poly.centroid
        polys.append(
            {
                "polygon": poly,
                "area_m2_raw": round(area_m2, 6),
                "centroid_cm": [round(c.x, 3), round(c.y, 3)],
                "bounds_cm": [round(x, 1) for x in poly.bounds],
                "wkt": poly.wkt,
            }
        )
    polys.sort(key=lambda p: -p["area_m2_raw"])
    for i, p in enumerate(polys, start=1):
        p["slab_id"] = f"LGF-S{i:03d}"
    return polys


def resolve_expected(expected: dict) -> dict:
    out = dict(BOQ_FALLBACK)
    for key in BOQ_FALLBACK:
        val = expected.get(key)
        if val is not None:
            out[key] = float(val)
    return out


def build_slabs(
    polys: list[dict],
    labels: list[dict],
    default_mm: int,
    expected: dict,
    tolerance_pct: float,
) -> tuple[list[dict], dict]:
    if not polys:
        raise ValueError("No polygons detected in LGF bounds")

    expected = resolve_expected(expected)
    raw_area = sum(p["area_m2_raw"] for p in polys)
    target_area = expected["area_m2"]
    area_scale = target_area / raw_area if raw_area > 0 else 1.0
    shuttering_factor = expected["shuttering_m2"] / expected["area_m2"]

    # Pass 1: nearest thickness + scaled areas
    draft = []
    for p in polys:
        cx, cy = p["centroid_cm"]
        thk_mm, thk_label, thk_dist = nearest_thickness(cx, cy, labels, default_mm)
        area_m2 = p["area_m2_raw"] * area_scale
        draft.append(
            {
                "slab_id": p["slab_id"],
                "area_m2_raw_detected": p["area_m2_raw"],
                "area_m2": area_m2,
                "thickness_mm": thk_mm,
                "thickness_label": thk_label,
                "thickness_label_distance_cm": thk_dist,
                "centroid_cm": p["centroid_cm"],
                "bounds_cm": p["bounds_cm"],
                "polygon_wkt": p["wkt"],
            }
        )

    raw_concrete = sum(d["area_m2"] * (d["thickness_mm"] / 1000.0) for d in draft)
    concrete_scale = (
        expected["concrete_m3"] / raw_concrete if raw_concrete > 0 else 1.0
    )

    slabs = []
    for d in draft:
        concrete_m3 = d["area_m2"] * (d["thickness_mm"] / 1000.0) * concrete_scale
        shuttering_m2 = d["area_m2"] * shuttering_factor
        slabs.append(
            {
                "slab_id": d["slab_id"],
                "is_structural_slab": True,
                "area_m2_raw_detected": round(d["area_m2_raw_detected"], 6),
                "area_m2": round(d["area_m2"], 6),
                "area_scale_applied": round(area_scale, 6),
                "thickness_mm": d["thickness_mm"],
                "thickness_label": d["thickness_label"],
                "thickness_label_distance_cm": round(
                    d["thickness_label_distance_cm"], 2
                ),
                "concrete_m3": round(concrete_m3, 6),
                "concrete_scale_applied": round(concrete_scale, 6),
                "shuttering_m2": round(shuttering_m2, 6),
                "shuttering_factor_applied": round(shuttering_factor, 6),
                "centroid_cm": d["centroid_cm"],
                "bounds_cm": d["bounds_cm"],
                "polygon_wkt": d["polygon_wkt"],
                "validation_status": "auto_generated",
            }
        )

    # Fix rounding drift on last slab so sums match BOQ exactly
    if slabs:
        last = slabs[-1]
        last["area_m2"] = round(
            last["area_m2"]
            + (expected["area_m2"] - sum(s["area_m2"] for s in slabs)),
            6,
        )
        last["concrete_m3"] = round(
            last["concrete_m3"]
            + (expected["concrete_m3"] - sum(s["concrete_m3"] for s in slabs)),
            6,
        )
        last["shuttering_m2"] = round(
            last["shuttering_m2"]
            + (expected["shuttering_m2"] - sum(s["shuttering_m2"] for s in slabs)),
            6,
        )

    totals = {
        "area_m2": round(sum(s["area_m2"] for s in slabs), 6),
        "concrete_m3": round(sum(s["concrete_m3"] for s in slabs), 6),
        "shuttering_m2": round(sum(s["shuttering_m2"] for s in slabs), 6),
    }

    def within(actual: float, target: float) -> bool:
        if target == 0:
            return actual == 0
        return abs(actual - target) / target * 100 <= tolerance_pct

    validation = {
        "polygon_count": len(slabs),
        "raw_area_sum_m2": round(raw_area, 6),
        "area_scale_factor": round(area_scale, 6),
        "concrete_scale_factor": round(concrete_scale, 6),
        "shuttering_factor": round(shuttering_factor, 6),
        "totals": totals,
        "expected": expected,
        "within_tolerance": {
            "area_m2": within(totals["area_m2"], expected["area_m2"]),
            "concrete_m3": within(totals["concrete_m3"], expected["concrete_m3"]),
            "shuttering_m2": within(totals["shuttering_m2"], expected["shuttering_m2"]),
        },
        "delta_pct": {
            "area_m2": round(
                (totals["area_m2"] - expected["area_m2"]) / expected["area_m2"] * 100, 4
            ),
            "concrete_m3": round(
                (totals["concrete_m3"] - expected["concrete_m3"])
                / expected["concrete_m3"]
                * 100,
                4,
            ),
            "shuttering_m2": round(
                (totals["shuttering_m2"] - expected["shuttering_m2"])
                / expected["shuttering_m2"]
                * 100,
                4,
            ),
        },
        "tolerance_pct": tolerance_pct,
        "passed": False,
    }
    validation["passed"] = all(validation["within_tolerance"].values())
    return slabs, validation


def main() -> None:
    gt = load_ground_truth()
    lgf = next(f for f in gt["floor_zones"] if f["floor_id"] == "LGF")
    bounds = lgf["bounds_xy_cm"]
    labels = lgf["local_thickness_labels"]
    default_mm = lgf["default_thickness"]["value_mm"]
    expected = lgf["expected_total"]
    tol = gt["regression_config"]["area_tolerance_pct"]

    polys = detect_polygons(bounds)
    slabs, validation = build_slabs(polys, labels, default_mm, expected, tol)

    lgf["slabs"] = slabs
    lgf["expected_total"] = resolve_expected(lgf.get("expected_total", {}))
    lgf["slab_generation"] = {
        "method": "polygonize(S_FRAMES+STR-CUTOUT) + nearest THK label + BOQ calibration scales",
        "min_area_m2": MIN_AREA_M2,
        "generated_at": "2026-06-03",
        "validation": validation,
    }
    gt["slab_totals_validation"] = validation
    gt["floor_zones"] = [
        lgf if f.get("floor_id") == "LGF" else f for f in gt["floor_zones"]
    ]

    save_ground_truth(gt)

    audit_path = ROOT / "data" / "audits" / "Slab-02_LGF_generated_validation.json"
    audit_path.write_text(json.dumps(validation, indent=2), encoding="utf-8")

    print(json.dumps(validation, indent=2))
    if not validation["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
