"""Import estimator Excel workbooks from Data Source/Ground Truths into data/ground_truth/."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sdie.atlas.builder import build_atlas_samples_from_dxf
from sdie.atlas.store import load_atlas, save_atlas
from sdie.rag.excel_ingest import ingest_all_projects
from sdie.validation.component_gt import iter_gt_drawing_specs


def _build_tagged_atlas(
    manifest_path: Path,
    project_root: Path,
    output: Path,
    *,
    fresh: bool,
    merge_project_ids: set[str] | None = None,
    project_ids: set[str] | None = None,
) -> dict:
    if fresh:
        by_id: dict[str, object] = {}
    elif merge_project_ids:
        by_id = {
            s.sample_id: s
            for s in load_atlas(output)
            if s.project_id not in merge_project_ids
        }
    else:
        by_id = {s.sample_id: s for s in load_atlas(output)}

    per_project: dict[str, int] = defaultdict(int)
    supervised_counts: dict[str, int] = defaultdict(int)

    for spec in iter_gt_drawing_specs(manifest_path, project_root):
        if project_ids and spec.project_id not in project_ids:
            continue
        if not spec.supervised_type and not spec.primary:
            continue
        dxf = spec.dxf_path
        supervised = spec.supervised_type
        samples = build_atlas_samples_from_dxf(
            dxf,
            project_id=spec.project_id,
            supervised_component_type=supervised,
        )
        for s in samples:
            by_id[s.sample_id] = s
        per_project[spec.project_id] += len(samples)
        label = supervised or "rule"
        if supervised:
            supervised_counts[supervised] += len(samples)
        print(f"{spec.project_id} / {dxf.name}: {len(samples)} samples ({label})")

    merged = list(by_id.values())
    save_atlas(merged, output)
    print(f"Atlas saved: {output} ({len(merged)} total samples, fresh={fresh})")
    return {
        "total_samples": len(merged),
        "per_project": dict(per_project),
        "supervised_counts": dict(supervised_counts),
        "fresh": fresh,
        "merged_projects": sorted(merge_project_ids) if merge_project_ids else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import project Excel workbooks → data/ground_truth JSON"
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
        "--data-source",
        type=Path,
        default=ROOT / "Data Source",
        help="Root for legacy Ground Truths/ workbooks only",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=ROOT / "data" / "ground_truth",
    )
    parser.add_argument(
        "--atlas-output",
        type=Path,
        default=ROOT / "data" / "atlas" / "component_atlas.json",
    )
    parser.add_argument(
        "--build-atlas",
        action="store_true",
        help="Build atlas from manifest teach drawings",
    )
    parser.add_argument(
        "--fresh-atlas",
        action="store_true",
        help="Replace atlas entirely (drops all projects)",
    )
    parser.add_argument(
        "--merge-atlas",
        nargs="+",
        default=[],
        metavar="PROJECT_ID",
        help="Replace atlas samples for these project_ids only",
    )
    parser.add_argument(
        "--atlas-project-id",
        action="append",
        default=[],
        metavar="ID",
        help="Only build atlas from these manifest project_ids",
    )
    parser.add_argument(
        "--build-kb",
        action="store_true",
        help="After import, rebuild structural knowledge base",
    )
    args = parser.parse_args()

    summary = ingest_all_projects(
        manifest_path=args.manifest,
        data_source_root=args.data_source,
        output_dir=args.output,
    )
    print(json.dumps(summary, indent=2))

    if args.build_atlas:
        merge_ids = set(args.merge_atlas) if args.merge_atlas else None
        project_ids = set(args.atlas_project_id) if args.atlas_project_id else None
        atlas_summary = _build_tagged_atlas(
            args.manifest,
            args.project_root,
            args.atlas_output,
            fresh=args.fresh_atlas,
            merge_project_ids=merge_ids,
            project_ids=project_ids,
        )
        summary["atlas"] = atlas_summary

    if args.build_kb:
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build_knowledge_base.py")],
            check=True,
            cwd=ROOT,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
