from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from sdie.classification.layer_profiles import load_profiles, merged_layer_hints_for_project
from sdie.inference.generic import is_generic_project

# Layer-name families used when the drawing has no CLI override.
_FRAME_NAME = re.compile(
    r"(?:^|[-_])(?:S[-_]?FRAMES?|STR[-_]?BEAM|S[-_]?BEAM|BEAM|FRAME)(?:$|[-_])",
    re.I,
)
_ANNOTATION_NAME = re.compile(
    r"(?:ANNO|IDEN|FLOR|THK|NOTE|TEXT|DIM)",
    re.I,
)
_CUTOUT_NAME = re.compile(r"(?:CUTOUT|VOID|SUNK|OPENING|SHAFT)", re.I)

_STRUCTURAL_ENTITY_TYPES = frozenset({"LINE", "LWPOLYLINE", "HATCH", "POLYLINE"})
_ANNOTATION_ENTITY_TYPES = frozenset({"TEXT", "MTEXT", "ATTRIB"})


@dataclass(frozen=True)
class LayerStats:
    layer: str
    total: int = 0
    lines: int = 0
    polylines: int = 0
    text: int = 0
    hatches: int = 0

    @property
    def structural_score(self) -> float:
        return self.lines * 3.0 + self.polylines * 2.0 + self.hatches


@dataclass
class DrawingLayerPlan:
    """Resolved layer sets for one drawing run (V6 discovery)."""

    structural_layers: tuple[str, ...]
    annotation_layers: tuple[str, ...]
    cutout_layers: tuple[str, ...] = ()
    frame_layers: tuple[str, ...] = ()
    method: str = "discovered"
    notes: dict = field(default_factory=dict)


def scan_layer_stats(msp) -> dict[str, LayerStats]:
    """Single pass over modelspace — entity counts per layer."""
    buckets: dict[str, dict[str, int]] = defaultdict(lambda: Counter())
    for entity in msp:
        layer = entity.dxf.layer
        etype = entity.dxftype()
        buckets[layer]["total"] += 1
        if etype == "LINE":
            buckets[layer]["lines"] += 1
        elif etype in ("LWPOLYLINE", "POLYLINE"):
            buckets[layer]["polylines"] += 1
        elif etype in _ANNOTATION_ENTITY_TYPES:
            buckets[layer]["text"] += 1
        elif etype == "HATCH":
            buckets[layer]["hatches"] += 1

    return {
        layer: LayerStats(
            layer=layer,
            total=counts["total"],
            lines=counts["lines"],
            polylines=counts["polylines"],
            text=counts["text"],
            hatches=counts["hatches"],
        )
        for layer, counts in buckets.items()
    }


def _project_layer_boost(
    layer: str,
    project_id: str,
    profiles: dict,
) -> float:
    hints = merged_layer_hints_for_project(project_id, profiles=profiles)
    hard = profiles.get("hard_global_layers") or {}
    boost = 1.0
    if layer in hints or layer in hard:
        boost = 1.35
    generic = is_generic_project(project_id)
    for rule in profiles.get("rules") or []:
        if not generic and rule.get("project_id") != project_id:
            continue
        if rule.get("layer") != layer:
            continue
        ctype = (rule.get("component_type") or "").lower()
        if ctype in ("beam", "shear wall", "column", "structural wall"):
            boost = max(boost, 1.0 + float(rule.get("confidence", 0.8)) * 0.5)
    return boost


def discover_drawing_layers(
    msp,
    *,
    project_id: str = "GENERIC",
    profiles: dict | None = None,
    structural_override: tuple[str, ...] | None = None,
    min_frame_lines: int = 12,
) -> DrawingLayerPlan:
    """
    V6 layer resolution: scan the drawing + layer profiles instead of relying
    on a fixed CLI layer list (V5 defaulted to S_FRAMES even on Inizio sheets).
    """
    profiles = profiles if profiles is not None else load_profiles()
    stats = scan_layer_stats(msp)
    present = set(stats)

    notes: dict = {"layers_in_drawing": len(present)}

    # --- Annotation layers: text-bearing layers + known IDEN/ANNO names ---
    annotation: set[str] = set()
    for layer, st in stats.items():
        if st.text > 0 or _ANNOTATION_NAME.search(layer):
            annotation.add(layer)
    for fallback in ("G-ANNO-TEXT", "S-BEAM-IDEN", "A-FLOR-IDEN"):
        if fallback in present:
            annotation.add(fallback)

    # --- Cutout / void layers ---
    cutout: set[str] = set()
    for layer in present:
        if _CUTOUT_NAME.search(layer) or layer in ("STR-CUTOUT", "SUNK SLAB"):
            cutout.add(layer)

    # --- Structural / frame layers ---
    if structural_override:
        structural = {layer for layer in structural_override if layer in present}
        missing = [layer for layer in structural_override if layer not in present]
        method = "cli_override"
        notes["cli_override_missing"] = missing
    else:
        scored: list[tuple[float, str]] = []
        for layer, st in stats.items():
            if st.lines < min_frame_lines and st.polylines < 4:
                continue
            if st.text > st.lines and st.lines < 5:
                continue
            score = st.structural_score * _project_layer_boost(layer, project_id, profiles)
            if _FRAME_NAME.search(layer):
                score *= 1.8
            if layer in cutout:
                score *= 0.15
            if layer in annotation and st.lines < min_frame_lines:
                score *= 0.4
            scored.append((score, layer))

        scored.sort(reverse=True)
        notes["frame_candidates"] = [
            {"layer": layer, "score": round(score, 1), **stats[layer].__dict__}
            for score, layer in scored[:8]
        ]

        structural: set[str] = set()
        if scored:
            top_score = scored[0][0]
            threshold = max(top_score * 0.25, 30.0)
            for score, layer in scored:
                if score >= threshold:
                    structural.add(layer)
        method = "discovered"

    structural.update(cutout)

    # Primary beam-grid frame layer(s): highest line count among structural picks.
    frame_ranked = sorted(
        structural - cutout,
        key=lambda layer: stats[layer].lines if layer in stats else 0,
        reverse=True,
    )
    frame_layers = tuple(frame_ranked[:2]) if frame_ranked else tuple(structural)

    return DrawingLayerPlan(
        structural_layers=tuple(sorted(structural)),
        annotation_layers=tuple(sorted(annotation)),
        cutout_layers=tuple(sorted(cutout)),
        frame_layers=frame_layers or tuple(structural),
        method=method,
        notes=notes,
    )


def apply_layer_plan_to_config(config, msp) -> DrawingLayerPlan:
    """Resolve layers from the drawing (V6) and write them onto *config*."""
    override = config.structural_layers if config.structural_layers else None
    if config.auto_discover_layers:
        plan = discover_drawing_layers(
            msp,
            project_id=config.project_id,
            structural_override=override,
        )
    else:
        structural = config.structural_layers or ("S_FRAMES", "STR-CUTOUT")
        annotation = config.annotation_layers or (
            "G-ANNO-TEXT",
            "S-BEAM-IDEN",
            "A-FLOR-IDEN",
        )
        plan = DrawingLayerPlan(
            structural_layers=structural,
            annotation_layers=annotation,
            frame_layers=structural[:1] if structural else (),
            method="manual",
        )

    config.structural_layers = plan.structural_layers
    config.annotation_layers = plan.annotation_layers
    config.frame_layers = plan.frame_layers or plan.structural_layers
    if plan.cutout_layers:
        config.cutout_exclusion_layers = plan.cutout_layers
        config.hatch_void_layers = tuple(
            sorted(set(config.hatch_void_layers) | set(plan.cutout_layers))
        )
    config.layer_discovery_notes = {
        "method": plan.method,
        **plan.notes,
        "structural_layers": list(plan.structural_layers),
        "annotation_layers": list(plan.annotation_layers),
        "frame_layers": list(config.frame_layers),
        "cutout_layers": list(plan.cutout_layers),
    }
    return plan


def classification_entity_layers(config) -> tuple[str, ...]:
    """
    Layers fed to entity extraction + component classification.

    V5 used full ``structural_layers`` (e.g. S_FRAMES + STR-CUTOUT). V6 auto-discovery
    keeps ``frame_layers`` narrow for beam-grid, but cutout/void/wall layers must still
    be classified as Opening / Lift Core / Stair Core (Trust Office terrace pattern).
    """
    layers: set[str] = set(config.structural_layers)
    layers.update(config.column_exclusion_layers)
    layers.update(config.hatch_void_layers)
    layers.update(config.cutout_exclusion_layers)
    if config.wall_exclusion_layers:
        layers.update(config.wall_exclusion_layers)
    return tuple(sorted(layers))
