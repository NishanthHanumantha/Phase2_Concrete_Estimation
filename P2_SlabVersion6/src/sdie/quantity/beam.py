"""Beam concrete and shuttering quantities from classified beam entities."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sdie.classification.types import ClassifiedComponent, ComponentType
from sdie.detection.exclusions import parse_beam_half_width_mm

BEAM_TAG_RE = re.compile(r"\(?\s*(\d+)\s*[xX]\s*(\d+)\s*\)?", re.I)


@dataclass
class BeamQuantity:
    length_m: float
    width_mm: int
    depth_mm: int
    concrete_m3: float
    shuttering_m2: float
    trace: str


def _parse_section_from_text(text: str | None) -> tuple[int, int] | None:
    if not text:
        return None
    match = BEAM_TAG_RE.search(text.strip())
    if not match:
        return None
    w, d = int(match.group(1)), int(match.group(2))
    return min(w, d), max(w, d)


def _drawing_default_section_mm(
    msp,
    annotation_layers: tuple[str, ...],
    *,
    default_width_mm: int,
    default_depth_mm: int,
) -> tuple[int, int, str]:
    """Median (width, depth) from beam-size tags on annotation layers."""
    sections: list[tuple[int, int]] = []
    if msp is not None:
        for entity in msp:
            if entity.dxf.layer not in annotation_layers:
                continue
            if entity.dxftype() not in ("TEXT", "MTEXT"):
                continue
            raw = getattr(entity.dxf, "text", None) or ""
            parsed = _parse_section_from_text(str(raw))
            if parsed:
                sections.append(parsed)
    if sections:
        widths = sorted(s[0] for s in sections)
        depths = sorted(s[1] for s in sections)
        mid = len(sections) // 2
        return widths[mid], depths[mid], "drawing_beam_tags"
    half = int(round(parse_beam_half_width_mm(msp, annotation_layers) * 2))
    if half > 0:
        return half, max(default_depth_mm, half * 2), "drawing_half_width"
    return default_width_mm, default_depth_mm, "config_default"


def compute_beam_quantity(
    length_mm: float,
    width_mm: int,
    depth_mm: int,
) -> BeamQuantity:
    length_m = length_mm / 1000.0
    width_m = width_mm / 1000.0
    depth_m = depth_mm / 1000.0
    concrete_m3 = round(length_m * width_m * depth_m, 6)
    shuttering_m2 = round((width_m + 2.0 * depth_m) * length_m, 6)
    trace = (
        f"length_mm={round(length_mm, 1)}; section={width_mm}x{depth_mm}; "
        f"volume={concrete_m3}; shuttering={shuttering_m2}"
    )
    return BeamQuantity(
        length_m=round(length_m, 3),
        width_mm=width_mm,
        depth_mm=depth_mm,
        concrete_m3=concrete_m3,
        shuttering_m2=shuttering_m2,
        trace=trace,
    )


def dedupe_plan_copy_beams(
    beams: list[dict[str, Any]],
    *,
    y_bucket_mm: float = 80.0,
) -> tuple[list[dict[str, Any]], int]:
    """Keep one beam per (length, Y-band) — drops duplicate plan copies."""
    groups: dict[tuple[float, float], list[dict[str, Any]]] = {}
    for beam in beams:
        centroid = beam.get("centroid_mm") or [0.0, 0.0]
        y_key = round(float(centroid[1]) / y_bucket_mm) * y_bucket_mm
        key = (round(float(beam.get("length_m") or 0), 2), y_key)
        groups.setdefault(key, []).append(beam)
    removed = sum(len(g) - 1 for g in groups.values())
    kept: list[dict[str, Any]] = []
    for group in groups.values():
        kept.append(
            min(
                group,
                key=lambda b: (b.get("centroid_mm") or [0.0, 0.0])[0],
            )
        )
    kept.sort(
        key=lambda b: (
            (b.get("centroid_mm") or [0.0, 0.0])[1],
            (b.get("centroid_mm") or [0.0, 0.0])[0],
        ),
        reverse=True,
    )
    for idx, beam in enumerate(kept, start=1):
        beam["beam_id"] = f"BEAM-{idx:03d}"
    return kept, removed


def _centroid_in_plan_x_bounds(
    centroid_mm: list[float] | None,
    plan_x_bounds_mm: tuple[float, float] | None,
) -> bool:
    if plan_x_bounds_mm is None or not centroid_mm or len(centroid_mm) < 1:
        return True
    xmin, xmax = plan_x_bounds_mm
    return xmin <= float(centroid_mm[0]) <= xmax


def compute_beam_quantities_from_classification(
    classified: list[ClassifiedComponent],
    *,
    msp=None,
    annotation_layers: tuple[str, ...] = (),
    min_length_mm: float = 500.0,
    min_confidence: float = 70.0,
    default_width_mm: int = 300,
    default_depth_mm: int = 600,
    plan_x_bounds_mm: tuple[float, float] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Derive beam takeoff from classified Beam components (centerline length × section).
    """
    draw_w, draw_d, draw_src = _drawing_default_section_mm(
        msp,
        annotation_layers,
        default_width_mm=default_width_mm,
        default_depth_mm=default_depth_mm,
    )
    beams: list[dict[str, Any]] = []
    skipped_short = 0
    skipped_low_conf = 0
    skipped_duplicate_copy = 0

    beam_idx = 0
    for comp in classified:
        if comp.component_type != ComponentType.BEAM:
            continue
        if comp.confidence < min_confidence:
            skipped_low_conf += 1
            continue
        centroid = list(comp.centroid_mm) if comp.centroid_mm else None
        if not _centroid_in_plan_x_bounds(centroid, plan_x_bounds_mm):
            skipped_duplicate_copy += 1
            continue
        geo = comp.geometry_features or {}
        length_mm = geo.get("length_mm")
        if length_mm is None or float(length_mm) < min_length_mm:
            skipped_short += 1
            continue

        section = _parse_section_from_text(comp.annotation_text)
        if section:
            width_mm, depth_mm = section
            section_source = "entity_annotation"
        else:
            width_mm, depth_mm = draw_w, draw_d
            section_source = draw_src

        qty = compute_beam_quantity(float(length_mm), width_mm, depth_mm)
        beam_idx += 1
        beams.append(
            {
                "beam_id": f"BEAM-{beam_idx:03d}",
                "component_id": comp.component_id,
                "layer": comp.layer,
                "entity_type": comp.entity_type,
                "length_mm": round(float(length_mm), 2),
                "length_m": qty.length_m,
                "width_mm": qty.width_mm,
                "depth_mm": qty.depth_mm,
                "section_source": section_source,
                "concrete_m3": qty.concrete_m3,
                "shuttering_m2": qty.shuttering_m2,
                "confidence": comp.confidence,
                "review_required": comp.review_required,
                "centroid_mm": centroid,
                "geometry_wkt": comp.geometry_wkt,
                "calculation_trace": qty.trace,
            }
        )

    totals = {
        "beam_count": len(beams),
        "total_length_m": round(sum(b["length_m"] for b in beams), 3),
        "concrete_m3": round(sum(b["concrete_m3"] for b in beams), 6),
        "shuttering_m2": round(sum(b["shuttering_m2"] for b in beams), 6),
        "default_section_mm": f"{draw_w}x{draw_d}",
        "default_section_source": draw_src,
        "skipped_short": skipped_short,
        "skipped_low_confidence": skipped_low_conf,
        "skipped_duplicate_copy": skipped_duplicate_copy,
        "plan_x_bounds_mm": list(plan_x_bounds_mm) if plan_x_bounds_mm else None,
    }
    notes = {
        "engine": "beam_quantity_v1",
        "min_length_mm": min_length_mm,
        "min_confidence": min_confidence,
        **totals,
    }
    return beams, notes
