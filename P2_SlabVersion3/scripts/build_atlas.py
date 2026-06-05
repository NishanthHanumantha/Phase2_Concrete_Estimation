"""Epic 1 — Build Component Atlas from tagged DXF drawings."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sdie.atlas.builder import build_atlas_samples_from_dxf
from sdie.atlas.store import load_atlas, save_atlas


def main() -> int:
    parser = argparse.ArgumentParser(description="Build SDIE Component Atlas")
    parser.add_argument("dxfs", nargs="+", type=Path, help="Tagged DXF files")
    parser.add_argument("--project-id", default="INIZIO")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=ROOT / "data" / "atlas" / "component_atlas.json",
    )
    parser.add_argument("--merge", action="store_true", help="Merge with existing atlas")
    args = parser.parse_args()

    existing = load_atlas(args.output) if args.merge else []
    by_id = {s.sample_id: s for s in existing}
    for dxf in args.dxfs:
        samples = build_atlas_samples_from_dxf(
            dxf.resolve(), project_id=args.project_id
        )
        for s in samples:
            by_id[s.sample_id] = s
        print(f"{dxf.name}: {len(samples)} samples")

    merged = list(by_id.values())
    out = save_atlas(merged, args.output)
    print(f"Atlas saved: {out} ({len(merged)} total samples)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
