"""Evaluate Slab/Beam/Column/Shear Wall classification vs manifest entity GT."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sdie.validation.component_eval import full_evaluation
from sdie.validation.component_gt import BUSINESS_COMPONENT_TYPES


def _print_report(report: dict) -> None:
    mode = report.get("mode", {})
    print("=== COMPONENT CLASSIFICATION EVALUATION ===")
    print(
        f"Mode: v4={mode.get('use_v4')} deepseek={mode.get('enable_deepseek')} "
        f"tagged_only={mode.get('component_tagged_only')} "
        f"include_primary_slab={mode.get('include_primary_slab')}"
    )
    print()

    corpus = report.get("gt_corpus", {})
    print("=== GT CORPUS ===")
    print(f"Total GT entities: {corpus.get('total_entities', 0)}")
    for ctype, n in sorted((corpus.get("by_type") or {}).items()):
        print(f"  {ctype}: {n}")
    print("By drawing:")
    for drawing, n in sorted((corpus.get("by_drawing") or {}).items()):
        print(f"  {drawing}: {n}")
    print()

    summary = report.get("summary", {})
    print("=== OVERALL ===")
    print(f"Evaluated:  {summary.get('evaluated', 0)}")
    print(f"Correct:    {summary.get('correct', 0)}")
    print(f"Accuracy:   {summary.get('accuracy_pct', 0)}%")
    print(f"Missing:    {summary.get('missing_predictions', 0)}")
    print(f"Errors:     {report.get('error_count', 0)}")
    print()

    print("=== PER CLASS (precision / recall / F1) ===")
    for ctype in BUSINESS_COMPONENT_TYPES:
        row = report.get("per_class", {}).get(ctype, {})
        print(
            f"  {ctype:12} P={row.get('precision_pct', 0):5.1f}% "
            f"R={row.get('recall_pct', 0):5.1f}% F1={row.get('f1_pct', 0):5.1f}% "
            f"(tp={row.get('tp', 0)} fp={row.get('fp', 0)} fn={row.get('fn', 0)})"
        )
    print()

    print("=== CONFUSION MATRIX (rows=expected, cols=predicted) ===")
    confusion = report.get("confusion", {})
    cols = list(BUSINESS_COMPONENT_TYPES) + ["Other"]
    header = "           " + "".join(f"{c:>12}" for c in cols)
    print(header)
    for exp in BUSINESS_COMPONENT_TYPES:
        row = confusion.get(exp, {})
        vals = "".join(f"{row.get(c, 0):>12}" for c in cols)
        print(f"{exp:12}{vals}")
    print()

    print("=== TOP TYPE PAIR ERRORS ===")
    for item in report.get("top_type_pair_errors", [])[:12]:
        print(
            f"  {item['expected']} -> {item['predicted']}: {item['count']}"
        )
    print()

    print("=== TOP LAYERS WITH ERRORS ===")
    for layer, n in report.get("top_layer_errors", [])[:10]:
        print(f"  {layer}: {n}")
    print()

    print("=== SAMPLE ERRORS (first 15) ===")
    for err in report.get("sample_errors", [])[:15]:
        print(
            f"  {err['drawing']} {err['entity_id']}: "
            f"expected {err['expected']} got {err['predicted']} "
            f"({err['layer']}, conf={err['confidence']})"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate 4-class component classification against manifest GT"
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
        "-o",
        "--output",
        type=Path,
        default=ROOT / "Output" / "component_classification_eval.json",
    )
    parser.add_argument(
        "--tagged-only",
        action="store_true",
        help="Only tagged_beam/column/shearwall drawings (recommended baseline)",
    )
    parser.add_argument(
        "--no-primary-slab",
        action="store_true",
        help="Skip primary drawing THK-annotation slab GT",
    )
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Rule+atlas only (no v4 RAG/DeepSeek)",
    )
    parser.add_argument(
        "--no-deepseek",
        action="store_true",
        help="v5/v4 RAG but skip DeepSeek API calls",
    )
    parser.add_argument(
        "--v4-only",
        action="store_true",
        help="Use v4 classifier instead of v5 structural reasoning",
    )
    parser.add_argument(
        "--drawing",
        action="append",
        default=[],
        metavar="STEM",
        help="Only eval drawings whose filename contains STEM (repeatable)",
    )
    args = parser.parse_args()

    from sdie.validation.component_gt import load_all_entity_ground_truth

    gt = load_all_entity_ground_truth(
        args.manifest,
        args.project_root,
        include_primary_slab=not args.no_primary_slab,
        component_tagged_only=args.tagged_only,
    )
    if args.drawing:
        needles = [d.lower() for d in args.drawing]
        gt = [r for r in gt if any(n in r.source_drawing.lower() for n in needles)]

    from sdie.validation.component_eval import (
        evaluate_components,
        run_classification_on_gt_drawings,
        summarize_gt_corpus,
    )

    runs = run_classification_on_gt_drawings(
        args.manifest,
        args.project_root,
        use_v4=not args.baseline,
        use_v5=not args.baseline and not args.v4_only,
        enable_deepseek=not args.no_deepseek and not args.baseline,
        atlas_path=args.atlas,
        kb_path=args.kb,
        gt=gt,
    )
    report = evaluate_components(gt, runs)
    report["gt_corpus"] = summarize_gt_corpus(gt)
    report["mode"] = {
        "use_v4": not args.baseline,
        "use_v5": not args.baseline and not args.v4_only,
        "enable_deepseek": not args.no_deepseek and not args.baseline,
        "include_primary_slab": not args.no_primary_slab,
        "component_tagged_only": args.tagged_only,
        "drawing_filter": args.drawing,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    _print_report(report)
    print(f"Full report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
