"""Run SDIE slab pipeline on a DXF file."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sdie.config import PipelineConfig
from sdie.pipeline import run_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="SDIE slab quantity pipeline")
    parser.add_argument("dxf", type=Path, help="Input DXF path")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output directory",
    )
    parser.add_argument(
        "--layers",
        nargs="+",
        default=["S_FRAMES", "STR-CUTOUT"],
        help="Structural layers for beam-grid / polygonize",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "region", "beam_frame", "beam_grid"],
        default="auto",
        help="Slab detection strategy",
    )
    parser.add_argument(
        "--edge-expand-mm",
        type=float,
        default=None,
        help="Expand slab bbox to outer face (mm); default half beam width",
    )
    parser.add_argument(
        "--min-area",
        type=float,
        default=10.0,
        help="Minimum slab area m²",
    )
    args = parser.parse_args()

    config = PipelineConfig(
        structural_layers=tuple(args.layers),
        detection_mode=args.mode,
        min_slab_area_m2=args.min_area,
        slab_edge_expand_mm=args.edge_expand_mm,
    )
    result = run_pipeline(args.dxf.resolve(), args.output.resolve(), config)
    print(json.dumps({"totals": result["totals"], "outputs": result["output_files"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
