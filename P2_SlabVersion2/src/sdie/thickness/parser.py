from __future__ import annotations

import math
import re
from dataclasses import dataclass

from ezdxf.entities import DXFEntity

NOTE_RE = re.compile(r"ALL\s+SLABS\s+ARE\s+(\d+)\s*mm\s*THK", re.I)
THK_RE = re.compile(r"(\d+)\s*THK", re.I)


@dataclass
class ThicknessLabel:
    value_mm: int
    text: str
    xy_cm: tuple[float, float]


def parse_text_content(entity: DXFEntity) -> str:
    if entity.dxftype() == "TEXT":
        return (entity.dxf.text or "").strip()
    if entity.dxftype() == "MTEXT":
        return (entity.text or "").strip()
    return ""


def extract_default_thickness_mm(msp, layers: tuple[str, ...]) -> tuple[int, str | None]:
    for entity in msp:
        if entity.dxf.layer not in layers:
            continue
        text = parse_text_content(entity)
        m = NOTE_RE.search(text)
        if m:
            return int(m.group(1)), text
    for entity in msp:
        if entity.dxf.layer not in layers:
            continue
        if entity.dxftype() not in ("TEXT", "MTEXT"):
            continue
        text = parse_text_content(entity).upper()
        if "U.N.O" in text or "GENERAL" in text:
            m = THK_RE.search(text)
            if m:
                return int(m.group(1)), text
    return 200, None


def extract_thk_labels(msp, layers: tuple[str, ...]) -> list[ThicknessLabel]:
    labels: list[ThicknessLabel] = []
    for entity in msp:
        if entity.dxf.layer not in layers:
            continue
        if entity.dxftype() not in ("TEXT", "MTEXT"):
            continue
        text = parse_text_content(entity)
        m = THK_RE.search(text.upper())
        if not m:
            continue
        labels.append(
            ThicknessLabel(
                value_mm=int(m.group(1)),
                text=text,
                xy_cm=(entity.dxf.insert.x, entity.dxf.insert.y),
            )
        )
    return labels


def nearest_thickness_mm(
    centroid_cm: tuple[float, float],
    labels: list[ThicknessLabel],
    default_mm: int,
    radius_m: float,
    *,
    max_label_distance_mm: float | None = None,
) -> tuple[int, str, float, float]:
    if not labels:
        return default_mm, "default_note", 0.0, 0.95

    cx, cy = centroid_cm
    best = None
    best_d_cm = float("inf")
    for lb in labels:
        d = math.hypot(cx - lb.xy_cm[0], cy - lb.xy_cm[1])
        if d < best_d_cm:
            best_d_cm = d
            best = lb

    if best is None:
        return default_mm, "default_note", 0.0, 0.95

    # Drawing coordinates are mm (see drawing_meta.coordinate_unit).
    max_dist_mm = float("inf")
    if max_label_distance_mm is not None:
        max_dist_mm = max_label_distance_mm
    elif radius_m > 0:
        max_dist_mm = radius_m * 1000.0

    if best_d_cm > max_dist_mm:
        return default_mm, "default_note", best_d_cm, 0.75

    conf = 0.95
    if max_dist_mm < float("inf") and max_dist_mm > 0:
        conf = max(0.6, 0.95 - (best_d_cm / max_dist_mm) * 0.25)
    return best.value_mm, best.text, best_d_cm, round(conf, 3)
