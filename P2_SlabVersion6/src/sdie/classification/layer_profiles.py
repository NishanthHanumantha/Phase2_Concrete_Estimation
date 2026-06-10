"""Per-project layer profiles learned from manifest supervised teaching DXFs."""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sdie.classification.types import ComponentType
from sdie.inference.generic import is_generic_project
from sdie.validation.component_gt import (
    DEFAULT_ANNOTATION_LAYERS,
    DEFAULT_STRUCTURAL_LAYERS,
    extract_entities_from_dxf,
    iter_gt_drawing_specs,
    supervised_type_from_drawing,
)

# Layers where component type must be resolved by geometry, not layer name alone.
SOFT_LAYER_HINTS: frozenset[str] = frozenset(
    {"S_FRAMES", "STR-BEAM", "S-BEAM", "S-BEAM-IDEN"}
)

# High-confidence global layer → type (same across projects unless overridden).
HARD_GLOBAL_LAYER_HINTS: dict[str, ComponentType] = {
    "S-COLS": ComponentType.COLUMN,
    "S-COL HATCH": ComponentType.COLUMN,
    "S-COL": ComponentType.COLUMN,
    "S-BEAM": ComponentType.BEAM,
    "S-SHEARWALL": ComponentType.SHEAR_WALL,
    "S-SHEAR": ComponentType.SHEAR_WALL,
    "S-WALL": ComponentType.SHEAR_WALL,
    "A-FLOR-IDEN": ComponentType.SLAB,
    "S-BEAM-IDEN": ComponentType.BEAM,
    "STR-CUTOUT": ComponentType.OPENING,
    "SUNK SLAB": ComponentType.OPENING,
    "S-SUNKEN HATCH": ComponentType.OPENING,
    "STR-BEAM": ComponentType.BEAM,
    "S-COLUMN": ComponentType.COLUMN,
    "Wall": ComponentType.STRUCTURAL_WALL,
    "STR-RC WALL HATCH": ComponentType.SHEAR_WALL,
}

DEFAULT_PROFILES_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "layer_profiles.json"
)


@dataclass(frozen=True)
class LayerRule:
    project_id: str
    layer: str
    component_type: str
    confidence: float
    entity_type: str | None = None
    source: str = "learned"
    sample_count: int = 0


def default_profiles_path() -> Path:
    return DEFAULT_PROFILES_PATH


def _profile_key(project_id: str, layer: str, entity_type: str | None) -> str:
    return f"{project_id}|{layer}|{entity_type or '*'}"


def learn_profiles_from_manifest(
    manifest_path: Path,
    project_root: Path,
    *,
    min_samples: int = 5,
    min_fraction: float = 0.55,
    project_ids: set[str] | None = None,
) -> list[LayerRule]:
    """
    Learn (project, layer[, entity_type]) → component type from supervised DXFs.

    Uses tagged_beam / tagged_column / tagged_shearwall / tagged_slab drawings only.
    """
    layer_counts: dict[tuple[str, str, str, str], int] = defaultdict(int)
    layer_totals: dict[tuple[str, str, str], int] = defaultdict(int)

    for spec in iter_gt_drawing_specs(manifest_path, project_root):
        if project_ids and spec.project_id not in project_ids:
            continue
        gt_type = spec.supervised_type
        if not gt_type:
            continue
        entities = extract_entities_from_dxf(
            spec.dxf_path,
            structural_layers=DEFAULT_STRUCTURAL_LAYERS,
            annotation_layers=DEFAULT_ANNOTATION_LAYERS,
            supervised_fallback_type=gt_type,
        )
        for ent in entities:
            layer = ent.layer or ""
            etype = ent.entity_type or ""
            layer_counts[(spec.project_id, layer, etype, gt_type)] += 1
            layer_totals[(spec.project_id, layer, etype)] += 1
            layer_counts[(spec.project_id, layer, "*", gt_type)] += 1
            layer_totals[(spec.project_id, layer, "*")] += 1

    rules: list[LayerRule] = []
    seen: set[tuple[str, str, str, str]] = set()

    for (pid, layer, etype, gt_type), count in sorted(
        layer_counts.items(), key=lambda x: -x[1]
    ):
        total = layer_totals[(pid, layer, etype)]
        if total < min_samples:
            continue
        fraction = count / total
        if fraction < min_fraction:
            continue
        dedupe = (pid, layer, etype, gt_type)
        if dedupe in seen:
            continue
        seen.add(dedupe)
        entity_type = None if etype == "*" else etype
        rules.append(
            LayerRule(
                project_id=pid,
                layer=layer,
                component_type=gt_type,
                confidence=round(min(0.98, 0.7 + fraction * 0.28), 3),
                entity_type=entity_type,
                source="supervised_dxf",
                sample_count=count,
            )
        )

    return rules


def _rules_to_payload(rules: list[LayerRule]) -> list[dict[str, Any]]:
    return [
        {
            "project_id": r.project_id,
            "layer": r.layer,
            "entity_type": r.entity_type,
            "component_type": r.component_type,
            "confidence": r.confidence,
            "source": r.source,
            "sample_count": r.sample_count,
        }
        for r in rules
    ]


def save_profiles(rules: list[LayerRule], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": "1",
        "soft_layers": sorted(SOFT_LAYER_HINTS),
        "hard_global_layers": {
            k: v.value for k, v in HARD_GLOBAL_LAYER_HINTS.items()
        },
        "rules": _rules_to_payload(rules),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def save_profiles_merging_projects(
    rules: list[LayerRule],
    path: Path,
    *,
    merge_project_ids: set[str],
) -> Path:
    """Replace rules for merge_project_ids only; keep other projects unchanged."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_profiles(path) if path.exists() else {}
    kept = [
        rule
        for rule in existing.get("rules", [])
        if rule.get("project_id") not in merge_project_ids
    ]
    payload = {
        "version": existing.get("version", "1"),
        "soft_layers": existing.get("soft_layers") or sorted(SOFT_LAYER_HINTS),
        "hard_global_layers": existing.get("hard_global_layers")
        or {k: v.value for k, v in HARD_GLOBAL_LAYER_HINTS.items()},
        "rules": kept + _rules_to_payload(rules),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_profiles(path: Path | None = None) -> dict[str, Any]:
    profile_path = path or default_profiles_path()
    if not profile_path.exists():
        return {"rules": [], "soft_layers": list(SOFT_LAYER_HINTS), "hard_global_layers": {}}
    return json.loads(profile_path.read_text(encoding="utf-8"))


def _index_rules(rules: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_project: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rule in rules:
        by_project[rule["project_id"]].append(rule)
    return by_project


def resolve_layer_rule(
    project_id: str,
    layer: str,
    entity_type: str,
    *,
    profiles: dict[str, Any] | None = None,
) -> tuple[ComponentType | None, float, str] | None:
    """Best matching layer rule — project-specific or cross-project when generic."""
    data = profiles or load_profiles()
    soft = set(data.get("soft_layers") or SOFT_LAYER_HINTS)
    generic = is_generic_project(project_id)

    def _project_ok(rule: dict[str, Any]) -> bool:
        return generic or rule.get("project_id") == project_id

    best_typed: tuple[float, ComponentType, str] | None = None
    for rule in data.get("rules") or []:
        if not _project_ok(rule):
            continue
        if rule.get("layer") != layer:
            continue
        r_etype = rule.get("entity_type")
        if not r_etype or r_etype != entity_type:
            continue
        try:
            ctype = ComponentType(rule["component_type"])
        except ValueError:
            continue
        conf = float(rule["confidence"])
        pid = rule.get("project_id", "")
        reason = (
            f"layer_profile:{layer}:{entity_type}@{pid}"
            if generic
            else f"layer_profile:{layer}:{entity_type}"
        )
        if best_typed is None or conf > best_typed[0]:
            best_typed = (conf, ctype, reason)

    if best_typed:
        return best_typed[1], best_typed[0], best_typed[2]

    best_any: tuple[float, ComponentType, str] | None = None
    for rule in data.get("rules") or []:
        if not _project_ok(rule):
            continue
        if rule.get("layer") != layer:
            continue
        if rule.get("entity_type"):
            continue
        conf = float(rule.get("confidence", 0))
        if layer in soft and conf < 0.95:
            continue
        try:
            ctype = ComponentType(rule["component_type"])
        except ValueError:
            continue
        pid = rule.get("project_id", "")
        reason = (
            f"layer_profile:{layer}@{pid}" if generic else f"layer_profile:{layer}"
        )
        if best_any is None or conf > best_any[0]:
            best_any = (conf, ctype, reason)

    if best_any:
        return best_any[1], best_any[0], best_any[2]
    return None


def _merged_hard_layers(data: dict[str, Any]) -> dict[str, str]:
    """Profile hard globals plus code defaults (profile wins on conflict)."""
    hard = {k: v.value for k, v in HARD_GLOBAL_LAYER_HINTS.items()}
    for layer, ctype_str in (data.get("hard_global_layers") or {}).items():
        hard[layer] = ctype_str
    return hard


def resolve_hard_global_layer(
    layer: str,
    entity_type: str,
    *,
    profiles: dict[str, Any] | None = None,
) -> tuple[ComponentType | None, float, str] | None:
    data = profiles or load_profiles()
    soft = set(data.get("soft_layers") or SOFT_LAYER_HINTS)
    hard = _merged_hard_layers(data)
    if layer in soft:
        return None
    ctype_str = hard.get(layer)
    if not ctype_str:
        return None
    if layer in ("S-COLS", "S-COL HATCH", "S-COL") and entity_type not in (
        "HATCH",
        "LWPOLYLINE",
        "INSERT",
        "CIRCLE",
    ):
        if entity_type in ("TEXT", "MTEXT", "DIMENSION"):
            return None
    try:
        return ComponentType(ctype_str), 0.92, f"hard_layer:{layer}"
    except ValueError:
        return None


def merged_layer_hints_for_project(
    project_id: str,
    *,
    profiles: dict[str, Any] | None = None,
) -> dict[str, ComponentType]:
    """Layer hint map: hard globals + best teach rule per layer (all projects when generic)."""
    data = profiles or load_profiles()
    soft = set(data.get("soft_layers") or SOFT_LAYER_HINTS)
    hints: dict[str, ComponentType] = {}
    for layer, ctype_str in _merged_hard_layers(data).items():
        if layer in soft:
            continue
        try:
            hints[layer] = ComponentType(ctype_str)
        except ValueError:
            pass
    generic = is_generic_project(project_id)
    best_by_layer: dict[str, tuple[float, ComponentType]] = {}
    for rule in data.get("rules") or []:
        if not generic and rule.get("project_id") != project_id:
            continue
        layer = rule.get("layer") or ""
        if layer in soft or rule.get("entity_type"):
            continue
        conf = float(rule.get("confidence", 0))
        if conf < 0.75:
            continue
        try:
            ctype = ComponentType(rule["component_type"])
        except ValueError:
            continue
        prev = best_by_layer.get(layer)
        if prev is None or conf > prev[0]:
            best_by_layer[layer] = (conf, ctype)
    for layer, (_, ctype) in best_by_layer.items():
        hints[layer] = ctype
    return hints
