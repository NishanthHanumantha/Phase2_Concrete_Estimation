"""Evaluate 4-class component classification against manifest entity GT."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sdie.atlas.store import load_atlas
from sdie.classification.classifier import classify_entities
from sdie.classification.rag_classifier import classify_entities_v4, classify_entities_v5
from sdie.ingestion.dxf_reader import load_drawing
from sdie.classification.types import ClassifiedComponent
from sdie.rag.store import load_knowledge_base
from sdie.validation.component_gt import (
    BUSINESS_COMPONENT_TYPES,
    EntityGroundTruth,
    extract_entities_from_dxf,
    iter_gt_drawing_specs,
    load_all_entity_ground_truth,
    normalize_business_type,
    summarize_gt_corpus,
)


@dataclass
class ClassificationRun:
    project_id: str
    dxf_path: Path
    components: list[ClassifiedComponent]


def _classify_drawing(
    dxf_path: Path,
    project_id: str,
    *,
    use_v4: bool,
    use_v5: bool,
    enable_deepseek: bool,
    atlas_by_project: dict[str, list],
    kb: Any | None,
) -> list[ClassifiedComponent]:
    entities = extract_entities_from_dxf(dxf_path)
    atlas = atlas_by_project.get(project_id, [])
    if use_v5 and kb is not None:
        doc, meta = load_drawing(dxf_path)
        classified, _notes = classify_entities_v5(
            entities,
            kb=kb,
            atlas=atlas,
            project_id=project_id,
            msp=doc.modelspace(),
            meta=meta,
            drawing_name=dxf_path.name,
            enable_deepseek=enable_deepseek,
        )
        return classified
    if use_v4:
        classified, _notes = classify_entities_v4(
            entities,
            kb=kb,
            atlas=atlas,
            project_id=project_id,
            enable_deepseek=enable_deepseek,
        )
        return classified
    return classify_entities(entities, atlas=atlas, project_id=project_id)


def run_classification_on_gt_drawings(
    manifest_path: Path,
    data_source: Path,
    *,
    use_v4: bool = True,
    use_v5: bool = True,
    enable_deepseek: bool = True,
    atlas_path: Path | None = None,
    kb_path: Path | None = None,
    gt: list[EntityGroundTruth] | None = None,
) -> list[ClassificationRun]:
    runs: list[ClassificationRun] = []
    seen: set[Path] = set()
    specs = iter_gt_drawing_specs(manifest_path, data_source)
    if gt is not None:
        needed = {(row.source_drawing, row.project_id) for row in gt}
        specs = [
            s
            for s in specs
            if (s.dxf_path.name, s.project_id) in needed
        ]

    project_ids = {s.project_id for s in specs}
    atlas_by_project = {
        pid: load_atlas(atlas_path, project_id=pid) for pid in project_ids
    }
    kb = load_knowledge_base(kb_path) if use_v4 else None

    for spec in specs:
        if spec.dxf_path in seen:
            continue
        seen.add(spec.dxf_path)
        components = _classify_drawing(
            spec.dxf_path,
            spec.project_id,
            use_v4=use_v4,
            use_v5=use_v5 and use_v4,
            enable_deepseek=enable_deepseek,
            atlas_by_project=atlas_by_project,
            kb=kb,
        )
        runs.append(
            ClassificationRun(
                project_id=spec.project_id,
                dxf_path=spec.dxf_path,
                components=components,
            )
        )
    return runs


def _prediction_index(runs: list[ClassificationRun]) -> dict[tuple[str, str], ClassifiedComponent]:
    """Key: (source_drawing filename, entity_id)."""
    idx: dict[tuple[str, str], ClassifiedComponent] = {}
    for run in runs:
        stem = run.dxf_path.name
        for comp in run.components:
            idx[(stem, comp.component_id)] = comp
    return idx


def evaluate_components(
    gt: list[EntityGroundTruth],
    runs: list[ClassificationRun],
) -> dict[str, Any]:
    pred_idx = _prediction_index(runs)
    classes = list(BUSINESS_COMPONENT_TYPES)

    confusion: dict[str, dict[str, int]] = {
        exp: {pred: 0 for pred in classes + ["Other"]} for exp in classes
    }
    missing_pred = 0
    errors: list[dict[str, Any]] = []
    correct = 0
    evaluated = 0

    layer_errors: Counter = Counter()
    type_pair_errors: Counter = Counter()

    for row in gt:
        comp = pred_idx.get((row.source_drawing, row.entity_id))
        if comp is None:
            missing_pred += 1
            continue
        evaluated += 1
        expected = row.expected_type
        predicted = normalize_business_type(comp.component_type.value)
        if predicted not in confusion[expected]:
            predicted = "Other"
        confusion[expected][predicted] += 1
        if predicted == expected:
            correct += 1
        else:
            errors.append(
                {
                    "entity_id": row.entity_id,
                    "project_id": row.project_id,
                    "drawing": row.source_drawing,
                    "expected": expected,
                    "predicted": predicted,
                    "raw_predicted": comp.component_type.value,
                    "layer": row.layer,
                    "entity_type": row.entity_type,
                    "confidence": comp.confidence,
                    "evidence": comp.evidence[:4],
                }
            )
            layer_errors[row.layer] += 1
            type_pair_errors[(expected, predicted)] += 1

    per_class: dict[str, dict[str, float | int]] = {}
    for ctype in classes:
        tp = confusion[ctype][ctype]
        fp = sum(confusion[other][ctype] for other in classes if other != ctype)
        fn = sum(confusion[ctype][other] for other in classes + ["Other"] if other != ctype)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        per_class[ctype] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision_pct": round(precision * 100, 1),
            "recall_pct": round(recall * 100, 1),
            "f1_pct": round(f1 * 100, 1),
        }

    accuracy = (correct / evaluated * 100) if evaluated else 0.0
    return {
        "summary": {
            "gt_entities": len(gt),
            "evaluated": evaluated,
            "missing_predictions": missing_pred,
            "correct": correct,
            "accuracy_pct": round(accuracy, 1),
        },
        "per_class": per_class,
        "confusion": confusion,
        "top_layer_errors": layer_errors.most_common(15),
        "top_type_pair_errors": [
            {"expected": a, "predicted": b, "count": n}
            for (a, b), n in type_pair_errors.most_common(20)
        ],
        "sample_errors": errors[:50],
        "error_count": len(errors),
    }


def full_evaluation(
    manifest_path: Path,
    data_source: Path,
    *,
    include_primary_slab: bool = True,
    component_tagged_only: bool = False,
    use_v4: bool = True,
    use_v5: bool = True,
    enable_deepseek: bool = True,
    atlas_path: Path | None = None,
    kb_path: Path | None = None,
) -> dict[str, Any]:
    gt = load_all_entity_ground_truth(
        manifest_path,
        data_source,
        include_primary_slab=include_primary_slab,
        component_tagged_only=component_tagged_only,
    )
    runs = run_classification_on_gt_drawings(
        manifest_path,
        data_source,
        use_v4=use_v4,
        use_v5=use_v5 and use_v4,
        enable_deepseek=enable_deepseek,
        atlas_path=atlas_path,
        kb_path=kb_path,
        gt=gt,
    )
    report = evaluate_components(gt, runs)
    report["gt_corpus"] = summarize_gt_corpus(gt)
    report["mode"] = {
        "use_v4": use_v4,
        "use_v5": use_v5 and use_v4,
        "enable_deepseek": enable_deepseek,
        "include_primary_slab": include_primary_slab,
        "component_tagged_only": component_tagged_only,
    }
    return report
