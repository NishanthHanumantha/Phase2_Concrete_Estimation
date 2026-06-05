from __future__ import annotations

import re

from sdie.classification.types import ComponentType
from sdie.ingestion.entity_extractor import DrawingEntity

THK_RE = re.compile(r"\b(\d+)\s*(?:mm\s*)?THK\b", re.I)
BEAM_TAG_RE = re.compile(r"\(?\s*(\d+)\s*[xX]\s*(\d+)\s*\)?", re.I)

VOID_KEYWORDS: dict[str, ComponentType] = {
    "STAIRCASE": ComponentType.STAIR_CORE,
    "STAIR": ComponentType.STAIR_CORE,
    "LIFT": ComponentType.LIFT_CORE,
    "LIFT PIT": ComponentType.LIFT_CORE,
    "HEADROOM": ComponentType.LIFT_CORE,
    "SHAFT": ComponentType.SHAFT,
    "CORE": ComponentType.LIFT_CORE,
    "SUNK": ComponentType.OPENING,
    "OPENING": ComponentType.OPENING,
    "CUTOUT": ComponentType.OPENING,
    "VOID": ComponentType.OPENING,
}

WALL_KEYWORDS = ("WALL", "SHEAR", "SW", "RETAINING")


def build_geometry_features(entity: DrawingEntity) -> dict:
    feats: dict = {
        "entity_type": entity.entity_type,
        "layer": entity.layer,
    }
    if entity.length_mm is not None:
        feats["length_mm"] = round(entity.length_mm, 2)
    if entity.area_mm2 is not None:
        feats["area_mm2"] = round(entity.area_mm2, 2)
    if entity.aspect_ratio is not None:
        feats["aspect_ratio"] = round(entity.aspect_ratio, 3)
    if entity.bounds_mm:
        minx, miny, maxx, maxy = entity.bounds_mm
        feats["width_mm"] = round(maxx - minx, 2)
        feats["height_mm"] = round(maxy - miny, 2)
    return feats


def build_annotation_features(entity: DrawingEntity) -> dict:
    feats: dict = {}
    text = (entity.text or "").upper()
    if not text:
        return feats
    feats["text_upper"] = text
    if THK_RE.search(text):
        feats["has_thk"] = True
        m = THK_RE.search(text)
        if m:
            feats["thk_mm"] = int(m.group(1))
    if BEAM_TAG_RE.search(text):
        feats["has_beam_tag"] = True
    for kw, ctype in VOID_KEYWORDS.items():
        if kw in text:
            feats["void_keyword"] = kw
            feats["void_component_hint"] = ctype.value
            break
    for kw in WALL_KEYWORDS:
        if kw in text:
            feats["wall_keyword"] = kw
            break
    return feats


def beam_enclosure_score(entity: DrawingEntity) -> float:
    """Higher when line is long and slender — typical beam centerline."""
    if entity.entity_type != "LINE" or entity.length_mm is None:
        return 0.0
    if entity.length_mm < 1500:
        return 0.2
    ar = entity.aspect_ratio or 1.0
    if ar >= 4.0:
        return 0.9
    if ar >= 2.0:
        return 0.7
    return 0.4


def column_compactness_score(entity: DrawingEntity) -> float:
    if entity.entity_type not in ("LWPOLYLINE", "HATCH"):
        return 0.0
    if entity.area_mm2 is None or entity.area_mm2 < 100:
        return 0.1
    ar = entity.aspect_ratio or 1.0
    if ar <= 2.0 and entity.area_mm2 < 2_500_000:
        return 0.85
    return 0.4


def wall_continuity_score(entity: DrawingEntity) -> float:
    if entity.entity_type != "LINE":
        return 0.0
    if entity.length_mm and entity.length_mm >= 3000:
        return 0.75
    return 0.3
