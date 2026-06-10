"""ML-style train/test accuracy metrics for the Tagged Files_2 / Raw files_2 split."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sdie.benchmark.metrics import accuracy_pct, within_tolerance
from sdie.project_knowledge.paths import resolve_manifest_dxf_path
from sdie.validation.component_gt import (
    BUSINESS_COMPONENT_TYPES,
    QUANTITY_PHASE_TYPES,
    build_entity_ground_truth,
    load_manifest,
)

RAW_TEST_ROOT_REL = "Revised Project Knowledge/Raw files_2"
TAGGED_ROOT_REL = "Revised Project Knowledge/Tagged Files_2"
PHASE_TARGET_F1_PCT = 85.0
COUNT_TOLERANCE = 2


def _mean_accuracy(values: list[float | None]) -> float | None:
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return round(sum(nums) / len(nums), 1)


def eval_fragment_from_train_metrics(train_metrics: dict[str, Any]) -> dict[str, Any]:
    """Convert a saved train_metrics.json chunk into an eval_report fragment."""
    summary = train_metrics.get("summary") or {}
    evaluated = summary.get("entities_evaluated") or summary.get("evaluated") or 0
    return {
        "summary": {
            "gt_entities": evaluated,
            "evaluated": evaluated,
            "missing_predictions": summary.get("missing_predictions", 0),
            "correct": summary.get("correct", 0),
            "accuracy_pct": summary.get("accuracy_pct", 0),
        },
        "confusion": train_metrics.get("confusion") or {},
        "gt_corpus": train_metrics.get("gt_corpus"),
    }


def merge_eval_reports(*reports: dict[str, Any]) -> dict[str, Any]:
    """Merge disjoint train-eval fragments (e.g. first 10 + remaining 37 drawings)."""
    classes = list(BUSINESS_COMPONENT_TYPES)
    pred_labels = classes + ["Other"]
    confusion: dict[str, dict[str, int]] = {
        exp: {pred: 0 for pred in pred_labels} for exp in classes
    }
    correct = 0
    evaluated = 0
    missing_pred = 0
    gt_entities = 0

    for report in reports:
        summary = report.get("summary") or {}
        correct += int(summary.get("correct") or 0)
        evaluated += int(summary.get("evaluated") or 0)
        missing_pred += int(summary.get("missing_predictions") or 0)
        gt_entities += int(summary.get("gt_entities") or summary.get("entities_evaluated") or 0)
        conf = report.get("confusion") or {}
        for exp in classes:
            row = conf.get(exp) or {}
            for pred in pred_labels:
                confusion[exp][pred] += int(row.get(pred) or 0)

    per_class: dict[str, dict[str, float | int]] = {}
    for ctype in classes:
        tp = confusion[ctype][ctype]
        fp = sum(confusion[other][ctype] for other in classes if other != ctype)
        fn = sum(confusion[ctype][other] for other in pred_labels if other != ctype)
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
            "gt_entities": gt_entities,
            "evaluated": evaluated,
            "missing_predictions": missing_pred,
            "correct": correct,
            "accuracy_pct": round(accuracy, 1),
        },
        "per_class": per_class,
        "confusion": confusion,
    }


def format_train_metrics(eval_report: dict[str, Any]) -> dict[str, Any]:
    """Wrap component-classification eval as ML train-split metrics."""
    summary = eval_report.get("summary", {})
    per_class = eval_report.get("per_class", {})
    slab_beam_f1 = [
        per_class.get(t, {}).get("f1_pct")
        for t in QUANTITY_PHASE_TYPES
        if per_class.get(t, {}).get("f1_pct") is not None
    ]
    phase_f1 = _mean_accuracy(slab_beam_f1)
    return {
        "split": "train",
        "corpus": "Tagged Files_2",
        "metric_type": "entity_classification",
        "ground_truth": "manifest_supervised_flags",
        "summary": {
            "entities_evaluated": summary.get("evaluated", 0),
            "correct": summary.get("correct", 0),
            "accuracy_pct": summary.get("accuracy_pct", 0),
            "missing_predictions": summary.get("missing_predictions", 0),
            "slab_beam_mean_f1_pct": phase_f1,
        },
        "per_class": per_class,
        "confusion": eval_report.get("confusion"),
        "targets": {
            "accuracy_pct_min": PHASE_TARGET_F1_PCT,
            "slab_f1_pct_min": PHASE_TARGET_F1_PCT,
            "beam_f1_pct_min": PHASE_TARGET_F1_PCT,
        },
        "quality_checks": _train_quality_checks(summary, per_class, phase_f1),
        "quality_pass": None,
        "mode": eval_report.get("mode"),
        "gt_corpus": eval_report.get("gt_corpus"),
    }


def _train_quality_checks(
    summary: dict[str, Any],
    per_class: dict[str, Any],
    phase_f1: float | None,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    acc = summary.get("accuracy_pct")
    if acc is not None:
        checks.append(
            {
                "check": "train_accuracy_pct",
                "value": acc,
                "target": f">= {PHASE_TARGET_F1_PCT}",
                "pass": float(acc) >= PHASE_TARGET_F1_PCT,
            }
        )
    for ctype in QUANTITY_PHASE_TYPES:
        f1 = per_class.get(ctype, {}).get("f1_pct")
        if f1 is not None:
            checks.append(
                {
                    "check": f"train_{ctype.lower()}_f1_pct",
                    "value": f1,
                    "target": f">= {PHASE_TARGET_F1_PCT}",
                    "pass": float(f1) >= PHASE_TARGET_F1_PCT,
                }
            )
    if phase_f1 is not None:
        checks.append(
            {
                "check": "train_slab_beam_mean_f1_pct",
                "value": phase_f1,
                "target": f">= {PHASE_TARGET_F1_PCT}",
                "pass": phase_f1 >= PHASE_TARGET_F1_PCT,
            }
        )
    return checks


def _find_teach_drawing(
    manifest: dict[str, Any],
    project_root: Path,
    *,
    component_folder: str,
    floor_token: str,
    project_hint: str | None = None,
) -> Path | None:
    """Match a teach DXF by component folder and floor token (e.g. ST10)."""
    token = floor_token.upper()
    hint = (project_hint or "").upper()
    candidates: list[tuple[int, Path]] = []

    def _score(stem: str) -> int:
        s = 0
        if hint == "INIZIO":
            if "INIZIO" in stem or "_I_" in stem or stem.startswith("BT_I"):
                s += 10
            if "TO_" in stem or "_TO_" in stem:
                s -= 5
        if hint == "TRUST OFFICE" or hint == "TO":
            if "TO_" in stem or "_TO_" in stem:
                s += 10
            if "INIZIO" in stem:
                s -= 5
        # Prefer exact floor token boundary (ST1 not ST13)
        if re.search(rf"{re.escape(token)}(?!\d)", stem):
            s += 5
        return s

    for project in manifest.get("projects", []):
        for drawing in project.get("drawings", []):
            if drawing.get("component_folder") != component_folder:
                continue
            rel = drawing.get("dxf") or ""
            stem = Path(rel).stem.upper()
            if token not in stem:
                continue
            path = resolve_manifest_dxf_path(project_root, rel)
            if path.exists():
                candidates.append((_score(stem), path))

    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[0])
    return candidates[0][1]


def discover_raw_test_pair(
    raw_stem: str,
    manifest_path: Path,
    project_root: Path,
) -> dict[str, Any] | None:
    """
    Auto-pair a Raw files_2 DXF to teach references for test accuracy.

    Inizio_Raw_{n}  → SlabTag_Inizio_ST{n} + BT_I_ST{n} / BeamTAG_I_ST{n}
    TrustOffice_*   → SlabTag_TO_ST* / BeamTag_TO_ST* (best-effort by suffix)
    """
    manifest = load_manifest(manifest_path)
    pair: dict[str, Any] = {"raw_stem": raw_stem, "method": "auto"}

    m = re.match(r"Inizio_Raw_(\d+)$", raw_stem, re.I)
    if m:
        floor = f"ST{m.group(1)}"
        pair["project"] = "Inizio"
        pair["floor"] = floor
        slab = _find_teach_drawing(
            manifest, project_root,
            component_folder="Slab", floor_token=floor, project_hint="Inizio",
        )
        beam = _find_teach_drawing(
            manifest, project_root,
            component_folder="Beam", floor_token=floor, project_hint="Inizio",
        )
        if slab:
            pair["slab_teach"] = str(slab.relative_to(project_root)).replace("\\", "/")
        if beam:
            pair["beam_teach"] = str(beam.relative_to(project_root)).replace("\\", "/")
        return pair if pair.get("slab_teach") or pair.get("beam_teach") else None

    if raw_stem.upper().startswith("TRUSTOFFICE"):
        pair["project"] = "Trust Office"
        suffix_map = {
            "GF": "ST1",
            "FF": "ST2",
            "TERRACEF": "ST3",
        }
        for key, floor in suffix_map.items():
            if key in raw_stem.upper().replace("_", ""):
                pair["floor"] = floor
                slab = _find_teach_drawing(
                    manifest, project_root,
                    component_folder="Slab", floor_token=f"TO_{floor}",
                    project_hint="Trust Office",
                )
                beam = _find_teach_drawing(
                    manifest, project_root,
                    component_folder="Beam", floor_token=f"TO_{floor}",
                    project_hint="Trust Office",
                )
                if slab:
                    pair["slab_teach"] = str(slab.relative_to(project_root)).replace("\\", "/")
                if beam:
                    pair["beam_teach"] = str(beam.relative_to(project_root)).replace("\\", "/")
                return pair if pair.get("slab_teach") or pair.get("beam_teach") else None
    return None


def teach_reference_counts(
    pair: dict[str, Any],
    manifest_path: Path,
    project_root: Path,
) -> dict[str, Any]:
    """Entity + quantity reference counts from paired teach drawings."""
    manifest = load_manifest(manifest_path)
    refs: dict[str, Any] = {"pair": pair}
    entity_ref: dict[str, int] = {}
    qty_ref: dict[str, int] = {}

    for key, ctype in (("slab_teach", "Slab"), ("beam_teach", "Beam")):
        rel = pair.get(key)
        if not rel:
            continue
        dxf = project_root / rel
        if not dxf.exists():
            continue
        for project in manifest.get("projects", []):
            pid = project["project_id"]
            for drawing in project.get("drawings", []):
                if drawing.get("dxf") != rel:
                    continue
                from sdie.validation.component_gt import GtDrawingSpec, supervised_type_from_drawing

                spec = GtDrawingSpec(
                    project_id=pid,
                    drawing_id=drawing.get("drawing_id", dxf.stem),
                    dxf_path=dxf,
                    supervised_type=supervised_type_from_drawing(drawing),
                )
                gt = build_entity_ground_truth(spec)
                entity_ref[ctype] = len(gt)
                qty_ref[f"{ctype.lower()}_count"] = len(gt)
                refs[f"{key}_entities"] = len(gt)
                break
    refs["entity_reference"] = entity_ref
    refs["quantity_reference"] = qty_ref
    return refs


def _count_accuracy(actual: int, expected: int) -> dict[str, Any]:
    acc = accuracy_pct(float(actual), float(expected))
    delta = actual - expected
    return {
        "actual": actual,
        "expected": expected,
        "delta": delta,
        "accuracy_pct": acc,
        "within_tolerance": abs(delta) <= COUNT_TOLERANCE,
    }


def build_test_file_metrics(
    results_path: Path,
    *,
    manifest_path: Path,
    project_root: Path,
    pair: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Test-split accuracy for one raw pipeline results.json."""
    results = json.loads(results_path.read_text(encoding="utf-8"))
    stem = results_path.stem.replace("_results", "")
    pair = pair or discover_raw_test_pair(stem, manifest_path, project_root)
    inference = results.get("inference_metrics") or {}
    cls = inference.get("classification") or {}
    by_type = cls.get("by_type") or {}
    totals = results.get("totals") or {}

    out: dict[str, Any] = {
        "split": "test",
        "corpus": "Raw files_2",
        "metric_type": "paired_teach_reference",
        "raw_drawing": stem,
        "pair": pair,
        "classification_proxy": {
            "entities_total": cls.get("entities_total"),
            "by_type": by_type,
            "mean_confidence_slab_beam": cls.get("mean_confidence_slab_beam"),
            "unknown_pct": cls.get("unknown_pct"),
        },
        "quantities": {
            "slab_count": totals.get("slab_count"),
            "beam_count": totals.get("beam_count"),
            "slab_area_m2": totals.get("area_m2"),
            "beam_total_length_m": totals.get("beam_total_length_m"),
        },
        "reference_accuracy": None,
        "quality_pass": None,
    }

    if not pair:
        out["metric_type"] = "inference_proxy"
        out["note"] = "No teach pair found; only confidence proxy metrics available"
        out["quality_checks"] = inference.get("quality_checks") or []
        out["quality_pass"] = inference.get("quality_pass")
        return out

    refs = teach_reference_counts(pair, manifest_path, project_root)
    out["teach_reference"] = refs
    entity_ref = refs.get("entity_reference") or {}
    checks: list[dict[str, Any]] = []

    ref_acc: dict[str, Any] = {"entity_count": {}, "quantity_count": {}}
    for ctype in QUANTITY_PHASE_TYPES:
        expected_ent = entity_ref.get(ctype)
        predicted_ent = by_type.get(ctype)
        if expected_ent is not None and predicted_ent is not None:
            row = _count_accuracy(int(predicted_ent), int(expected_ent))
            ref_acc["entity_count"][ctype] = row
            checks.append(
                {
                    "check": f"test_{ctype.lower()}_entity_count_accuracy",
                    "value": row["accuracy_pct"],
                    "target": f">= {PHASE_TARGET_F1_PCT}",
                    "pass": row["accuracy_pct"] is not None
                    and row["accuracy_pct"] >= PHASE_TARGET_F1_PCT,
                }
            )

        qkey = f"{ctype.lower()}_count"
        expected_qty = refs.get("quantity_reference", {}).get(qkey)
        predicted_qty = totals.get(qkey) or totals.get("slab_count" if ctype == "Slab" else "beam_count")
        if expected_qty is not None and predicted_qty is not None:
            row = _count_accuracy(int(predicted_qty), int(expected_qty))
            ref_acc["quantity_count"][ctype] = row
            checks.append(
                {
                    "check": f"test_{ctype.lower()}_quantity_count_accuracy",
                    "value": row["accuracy_pct"],
                    "target": f">= {PHASE_TARGET_F1_PCT}",
                    "pass": row["accuracy_pct"] is not None
                    and row["accuracy_pct"] >= PHASE_TARGET_F1_PCT,
                }
            )

    out["reference_accuracy"] = ref_acc
    out["quality_checks"] = checks
    out["quality_pass"] = all(c["pass"] for c in checks) if checks else None
    acc_vals = [
        r.get("accuracy_pct")
        for group in ref_acc.values()
        if isinstance(group, dict)
        for r in group.values()
        if isinstance(r, dict) and r.get("accuracy_pct") is not None
    ]
    out["summary"] = {
        "mean_reference_accuracy_pct": _mean_accuracy(acc_vals),
        "checks_passed": sum(1 for c in checks if c["pass"]),
        "checks_total": len(checks),
    }
    return out


def build_test_corpus_metrics(
    results_dir: Path,
    *,
    manifest_path: Path,
    project_root: Path,
) -> dict[str, Any]:
    """Aggregate test metrics across all raw pipeline runs in a folder."""
    per_file: list[dict[str, Any]] = []
    for path in sorted(results_dir.glob("*/*_results.json")):
        per_file.append(
            build_test_file_metrics(
                path,
                manifest_path=manifest_path,
                project_root=project_root,
            )
        )
    mean_acc = _mean_accuracy(
        [f.get("summary", {}).get("mean_reference_accuracy_pct") for f in per_file]
    )
    paired = [f for f in per_file if f.get("pair")]
    passed = [f for f in per_file if f.get("quality_pass") is True]
    return {
        "split": "test",
        "corpus": "Raw files_2",
        "files_evaluated": len(per_file),
        "files_paired": len(paired),
        "files_quality_pass": len(passed),
        "mean_reference_accuracy_pct": mean_acc,
        "target_accuracy_pct_min": PHASE_TARGET_F1_PCT,
        "per_file": per_file,
    }


def build_ml_project_report(
    train: dict[str, Any] | None,
    test: dict[str, Any] | None,
) -> dict[str, Any]:
    """Combined ML project report (train X + test Y)."""
    train_pass = None
    if train:
        checks = train.get("quality_checks") or []
        train["quality_pass"] = all(c["pass"] for c in checks) if checks else None
        train_pass = train["quality_pass"]

    test_pass = None
    if test:
        test_pass = (
            test.get("mean_reference_accuracy_pct") is not None
            and test["mean_reference_accuracy_pct"] >= PHASE_TARGET_F1_PCT
        )

    return {
        "project": "SDIE V6 slab_beam",
        "train_corpus": "Revised Project Knowledge/Tagged Files_2",
        "test_corpus": "Revised Project Knowledge/Raw files_2",
        "phase_targets": {
            "classification_f1_pct_min": PHASE_TARGET_F1_PCT,
            "reference_accuracy_pct_min": PHASE_TARGET_F1_PCT,
        },
        "train": train,
        "test": test,
        "overall_pass": (
            (train_pass is not False if train else True)
            and (test_pass is not False if test else True)
        ),
    }
