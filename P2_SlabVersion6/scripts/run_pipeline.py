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
    parser = argparse.ArgumentParser(description="SDIE v6 structural reasoning slab pipeline")
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
        default=None,
        help="Override structural layers (disables auto-discovery for framing)",
    )
    parser.add_argument(
        "--auto-layers",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Discover structural/annotation layers from the DXF (V6 default)",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "semantic", "region", "beam_frame", "beam_grid"],
        default="auto",
        help="Detection strategy (semantic = v3.3 component-first)",
    )
    parser.add_argument(
        "--legacy-geometry",
        action="store_true",
        help="Use geometry-first pipeline (no semantic/v4 stages)",
    )
    parser.add_argument(
        "--v3-semantic",
        action="store_true",
        help="Use v3.3 rule classifier instead of v4/v5 RAG+DeepSeek",
    )
    parser.add_argument(
        "--v4-only",
        action="store_true",
        help="Use v4 RAG classifier instead of v5 structural reasoning engine",
    )
    parser.add_argument(
        "--no-deepseek",
        action="store_true",
        help="Disable DeepSeek entirely (rules+RAG only for all entities)",
    )
    parser.add_argument(
        "--no-beam-quantities",
        action="store_true",
        help="Skip beam concrete/shuttering quantity takeoff",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable stage progress bar on stderr",
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
        default=0.4,
        help="Minimum slab area m²",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Refine slab bays with DeepSeek (semantic classification only)",
    )
    parser.add_argument(
        "--deepseek-model",
        default="deepseek-chat",
        help="DeepSeek-V3 API model (deepseek-chat, deepseek-reasoner, auto)",
    )
    parser.add_argument(
        "--project-id",
        default="GENERIC",
        help=(
            "Inference context: GENERIC (default) uses merged teach from all reference "
            "projects (INIZIO, TRUST_OFFICE, MANOHAR). Set a specific ID only for "
            "teach/eval runs on that corpus."
        ),
    )
    args = parser.parse_args()

    config = PipelineConfig(
        project_id=args.project_id,
        auto_discover_layers=args.auto_layers and not args.layers,
        structural_layers=tuple(args.layers) if args.layers else (),
        detection_mode=args.mode,
        min_slab_area_m2=args.min_area,
        merge_beam_grid_to_estimator_bays=True,
        slab_edge_expand_mm=args.edge_expand_mm,
        enable_deepseek_refinement=args.llm,
        enable_deepseek_component_classification=not args.no_deepseek,
        deepseek_model=args.deepseek_model,
        show_progress=not args.no_progress,
        use_semantic_pipeline=not args.legacy_geometry,
        use_v4_pipeline=not args.legacy_geometry and not args.v3_semantic,
        use_v5_pipeline=not args.legacy_geometry
        and not args.v3_semantic
        and not args.v4_only,
        enable_rag_classification=not args.v3_semantic,
        enable_beam_quantities=not args.no_beam_quantities,
    )
    result = run_pipeline(args.dxf.resolve(), args.output.resolve(), config)
    print(json.dumps({"totals": result["totals"], "outputs": result["output_files"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
