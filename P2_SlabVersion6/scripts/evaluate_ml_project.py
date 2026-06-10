"""ML-style train (X) + test (Y) accuracy report for SDIE V6."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sdie.atlas.store import load_atlas
from sdie.rag.store import load_knowledge_base
from sdie.validation.component_eval import (
    ClassificationRun,
    evaluate_components,
)
from sdie.validation.component_gt import (
    iter_gt_drawing_specs,
    load_all_entity_ground_truth,
    summarize_gt_corpus,
)
from sdie.validation.ml_project_metrics import (
    build_ml_project_report,
    build_test_corpus_metrics,
    eval_fragment_from_train_metrics,
    format_train_metrics,
    merge_eval_reports,
)


def _run_train_evaluation(
    manifest_path: Path,
    project_root: Path,
    *,
    atlas_path: Path,
    kb_path: Path,
    enable_deepseek: bool,
    max_drawings: int | None = None,
    skip_drawings: int = 0,
) -> dict:
    """Train eval with per-drawing progress lines for batch monitoring."""
    gt = load_all_entity_ground_truth(
        manifest_path,
        project_root,
        include_primary_slab=False,
        component_tagged_only=True,
        slab_beam_only=True,
    )
    needed = {(row.source_drawing, row.project_id) for row in gt}
    specs = [
        s
        for s in iter_gt_drawing_specs(manifest_path, project_root)
        if (s.dxf_path.name, s.project_id) in needed
    ]
    total_drawings = len(specs)
    if skip_drawings:
        specs = specs[skip_drawings:]
    if max_drawings is not None:
        specs = specs[:max_drawings]
    selected = {s.dxf_path.name for s in specs}
    gt = [row for row in gt if row.source_drawing in selected]
    project_ids = {s.project_id for s in specs}
    atlas_by_project = {
        pid: load_atlas(atlas_path, project_id=pid) for pid in project_ids
    }
    kb = load_knowledge_base(kb_path)

    from sdie.validation.component_eval import _classify_drawing

    runs: list[ClassificationRun] = []
    batch_total = len(specs)
    for i, spec in enumerate(specs, start=1):
        global_idx = skip_drawings + i
        print(
            f"[{global_idx}/{total_drawings}] START {spec.dxf_path.name}",
            flush=True,
        )
        components = _classify_drawing(
            spec.dxf_path,
            spec.project_id,
            use_v4=True,
            use_v5=True,
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
        print(
            f"[{global_idx}/{total_drawings}] DONE {spec.dxf_path.name}",
            flush=True,
        )

    report = evaluate_components(gt, runs)
    report["gt_corpus"] = summarize_gt_corpus(gt)
    report["mode"] = {
        "use_v4": True,
        "use_v5": True,
        "enable_deepseek": enable_deepseek,
        "include_primary_slab": False,
        "component_tagged_only": True,
        "slab_beam_only": True,
        "max_drawings": max_drawings,
        "skip_drawings": skip_drawings,
        "drawings_in_batch": batch_total,
        "drawings_total": total_drawings,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "ML project metrics: train accuracy on Tagged Files_2 (X), "
            "test accuracy on Raw files_2 (Y)"
        )
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "Data Source" / "projects_manifest.json",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=ROOT,
    )
    parser.add_argument(
        "--atlas",
        type=Path,
        default=ROOT / "data" / "atlas" / "component_atlas.json",
    )
    parser.add_argument(
        "--kb",
        type=Path,
        default=ROOT / "data" / "knowledge_base" / "structural_kb.json",
    )
    parser.add_argument(
        "--test-results-dir",
        type=Path,
        default=ROOT / "Output" / "RawFiles2_TestRun",
        help="Folder with per-raw-drawing pipeline outputs (*_results.json)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=ROOT / "Output" / "ml_eval" / "ml_project_report.json",
    )
    parser.add_argument("--train-only", action="store_true")
    parser.add_argument("--test-only", action="store_true")
    parser.add_argument(
        "--no-deepseek",
        action="store_true",
        help="Skip DeepSeek during train eval (faster)",
    )
    parser.add_argument(
        "--max-drawings",
        type=int,
        default=None,
        metavar="N",
        help="Train eval: only first N teach drawings (faster sample)",
    )
    parser.add_argument(
        "--skip-drawings",
        type=int,
        default=0,
        metavar="N",
        help="Train eval: skip first N teach drawings (resume partial run)",
    )
    parser.add_argument(
        "--merge-from",
        type=Path,
        default=None,
        metavar="JSON",
        help="Merge saved train_metrics.json from a prior partial run into final report",
    )
    args = parser.parse_args()

    run_train = not args.test_only
    run_test = not args.train_only

    train_metrics = None
    test_metrics = None

    if run_train:
        print("=== TRAIN (X): Tagged Files_2 entity classification ===")
        if args.skip_drawings:
            print(f"  Skipping first {args.skip_drawings} teach drawings")
        if args.max_drawings:
            print(f"  Limiting train eval to first {args.max_drawings} drawings")
        if args.merge_from:
            print(f"  Will merge prior metrics from {args.merge_from}")
        eval_report = _run_train_evaluation(
            args.manifest,
            args.project_root,
            atlas_path=args.atlas,
            kb_path=args.kb,
            enable_deepseek=not args.no_deepseek,
            max_drawings=args.max_drawings,
            skip_drawings=args.skip_drawings,
        )
        if args.merge_from and args.merge_from.exists():
            prior = json.loads(args.merge_from.read_text(encoding="utf-8"))
            prior_fragment = eval_fragment_from_train_metrics(prior)
            eval_report = merge_eval_reports(prior_fragment, eval_report)
            full_gt = load_all_entity_ground_truth(
                args.manifest,
                args.project_root,
                include_primary_slab=False,
                component_tagged_only=True,
                slab_beam_only=True,
            )
            eval_report["gt_corpus"] = summarize_gt_corpus(full_gt)
            mode = eval_report.get("mode") or {}
            mode["merged_from"] = str(args.merge_from).replace("\\", "/")
            eval_report["mode"] = mode
        train_metrics = format_train_metrics(eval_report)
        checks = train_metrics.get("quality_checks") or []
        train_metrics["quality_pass"] = all(c["pass"] for c in checks) if checks else None
        summary = train_metrics["summary"]
        print(
            f"  Accuracy: {summary.get('accuracy_pct')}%  "
            f"Slab+Beam mean F1: {summary.get('slab_beam_mean_f1_pct')}%  "
            f"Pass: {train_metrics.get('quality_pass')}"
        )
        train_path = args.output.parent / "train_metrics.json"
        train_path.parent.mkdir(parents=True, exist_ok=True)
        train_path.write_text(json.dumps(train_metrics, indent=2), encoding="utf-8")
        print(f"  Wrote {train_path}")

    if not run_test:
        test_path = args.output.parent / "test_metrics.json"
        if test_path.exists():
            test_metrics = json.loads(test_path.read_text(encoding="utf-8"))

    if run_test:
        print("=== TEST (Y): Raw files_2 vs paired teach reference ===")
        test_metrics = build_test_corpus_metrics(
            args.test_results_dir,
            manifest_path=args.manifest,
            project_root=args.project_root,
        )
        print(
            f"  Files: {test_metrics.get('files_evaluated')}  "
            f"Paired: {test_metrics.get('files_paired')}  "
            f"Mean ref accuracy: {test_metrics.get('mean_reference_accuracy_pct')}%"
        )
        test_path = args.output.parent / "test_metrics.json"
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.write_text(json.dumps(test_metrics, indent=2), encoding="utf-8")
        print(f"  Wrote {test_path}")

    report = build_ml_project_report(train_metrics, test_metrics)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nCombined ML report: {args.output}")
    print(f"Overall pass: {report.get('overall_pass')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
