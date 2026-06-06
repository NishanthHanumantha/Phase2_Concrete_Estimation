from __future__ import annotations

import json
from pathlib import Path

from sdie.atlas.store import load_atlas
from sdie.classification.layer_profiles import (
    HARD_GLOBAL_LAYER_HINTS,
    load_profiles,
)
from sdie.rag.schema import (
    AnnotationKnowledge,
    EstimatorMapping,
    LayerKnowledge,
    StructuralKnowledgeBase,
)
from sdie.rag.store import save_knowledge_base


def _ingest_ground_truth_mappings(
    kb: StructuralKnowledgeBase,
    ground_truth_dir: Path,
) -> int:
    count = 0
    if not ground_truth_dir.exists():
        return 0
    for gt_file in ground_truth_dir.glob("*.json"):
        if gt_file.name == "README.md":
            continue
        try:
            data = json.loads(gt_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        project_id = data.get("project_id", data.get("drawing_id", gt_file.stem))
        source = data.get("source_dxf", gt_file.stem)
        expected = data.get("expected_total", {})
        if expected.get("slab_count"):
            kb.estimator_mappings.append(
                EstimatorMapping(
                    project_id=project_id,
                    drawing_signal=f"ground_truth:{gt_file.stem}",
                    estimator_component=f"Slab count {expected['slab_count']}",
                    component_type="Slab",
                    source_drawing=source,
                )
            )
            count += 1
        if expected.get("area_m2"):
            kb.estimator_mappings.append(
                EstimatorMapping(
                    project_id=project_id,
                    drawing_signal=f"total_area:{expected['area_m2']}",
                    estimator_component=f"Total slab area {expected['area_m2']} m2",
                    component_type="Slab",
                    source_drawing=source,
                )
            )
            count += 1
    return count


def build_knowledge_base(
    *,
    project_root: Path | None = None,
    atlas_path: Path | None = None,
    output_path: Path | None = None,
) -> StructuralKnowledgeBase:
    """
    Epic 1 — Build Component Knowledge Base from atlas, layer hints, ground truth.
    """
    root = project_root or Path(__file__).resolve().parents[3]
    kb = StructuralKnowledgeBase()

    profiles = load_profiles()
    for layer, ctype in HARD_GLOBAL_LAYER_HINTS.items():
        kb.layer_knowledge.append(
            LayerKnowledge(
                layer=layer,
                component_type=ctype.value,
                project_id="GLOBAL",
                confidence=0.92,
                source="hard_layer_hints",
            )
        )
    for rule in profiles.get("rules") or []:
        kb.layer_knowledge.append(
            LayerKnowledge(
                layer=rule["layer"],
                component_type=rule["component_type"],
                project_id=rule["project_id"],
                confidence=float(rule.get("confidence", 0.85)),
                source="layer_profile",
            )
        )

    for pattern, interpretation, hint in (
        (r"\d+\s*THK", "slab_thickness_local", "Slab"),
        (r"STAIRCASE|STAIR", "stair_core_void", "Stair Core"),
        (r"LIFT|HEADROOM", "lift_core_void", "Lift Core"),
        (r"SHAFT", "shaft_void", "Shaft"),
        (r"ALL SLABS ARE (\d+)mm", "default_slab_thickness_note", "Slab"),
    ):
        kb.annotation_knowledge.append(
            AnnotationKnowledge(
                pattern=pattern,
                interpretation=interpretation,
                component_hint=hint,
            )
        )

    atlas = load_atlas(atlas_path)
    seen_layers: set[tuple[str, str, str]] = set()
    pattern_counts: dict[tuple[str, str], int] = {}
    max_patterns_per_type = 20

    for sample in atlas:
        layer_key = (sample.project_id, sample.layer or "", sample.component_type)
        if sample.layer and layer_key not in seen_layers:
            seen_layers.add(layer_key)
            kb.layer_knowledge.append(
                LayerKnowledge(
                    layer=sample.layer,
                    component_type=sample.component_type,
                    project_id=sample.project_id,
                    confidence=min(1.0, sample.confidence),
                    source="atlas",
                )
            )
        if not sample.geometry_features:
            continue
        type_key = (sample.project_id, sample.component_type)
        if pattern_counts.get(type_key, 0) >= max_patterns_per_type:
            continue
        pattern_counts[type_key] = pattern_counts.get(type_key, 0) + 1
        kb.pattern_knowledge.append(
            {
                "project_id": sample.project_id,
                "layer": sample.layer,
                "component_type": sample.component_type,
                "geometry_features": sample.geometry_features,
                "source_drawing": sample.source_drawing,
            }
        )

    _ingest_ground_truth_mappings(kb, root / "data" / "ground_truth")
    save_knowledge_base(kb, output_path)
    return kb
