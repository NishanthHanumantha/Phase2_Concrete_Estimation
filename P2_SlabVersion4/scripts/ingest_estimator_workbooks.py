"""Import estimator Excel workbooks from Data Source/Ground Truths into data/ground_truth/."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sdie.atlas.builder import build_atlas_samples_from_dxf
from sdie.atlas.store import load_atlas, save_atlas
from sdie.rag.atlas_select import select_atlas_dxfs
from sdie.rag.excel_ingest import ingest_all_projects


def _build_tagged_atlas(
    manifest_path: Path,
    data_source: Path,
    output: Path,
    *,
    fresh: bool,
) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_id = {} if fresh else {s.sample_id: s for s in load_atlas(output)}
    per_project: dict[str, int] = {}

    for project in manifest.get("projects", []):
        folder = data_source / project["dxf_folder"]
        dxfs = select_atlas_dxfs(folder)
        pid = project["project_id"]
        count = 0
        for dxf in dxfs:
            samples = build_atlas_samples_from_dxf(
                dxf.resolve(), project_id=pid
            )
            for s in samples:
                by_id[s.sample_id] = s
            count += len(samples)
            print(f"{pid} / {dxf.name}: {len(samples)} samples")
        per_project[pid] = count

    merged = list(by_id.values())
    save_atlas(merged, output)
    print(f"Atlas saved: {output} ({len(merged)} total samples, fresh={fresh})")
    return {"total_samples": len(merged), "per_project": per_project, "fresh": fresh}


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
        "--data-source",
        type=Path,
        default=ROOT / "Data Source",
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
        help="Build atlas from tagged DXFs only (excludes RAW + Inizio_B2)",
    )
    parser.add_argument(
        "--fresh-atlas",
        action="store_true",
        help="Replace atlas entirely (recommended after corpus change)",
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
        atlas_summary = _build_tagged_atlas(
            args.manifest,
            args.data_source,
            args.atlas_output,
            fresh=args.fresh_atlas,
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
