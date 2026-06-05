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
    parser = argparse.ArgumentParser(description="SDIE v4 knowledge-driven slab pipeline")
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
        help="Use v3.3 rule classifier instead of v4 RAG+DeepSeek",
    )
    parser.add_argument(
        "--no-deepseek",
        action="store_true",
        help="Disable DeepSeek component classification (rule+RAG only)",
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
        default="INIZIO",
        help="Project ID for RAG/atlas context (INIZIO, TRUST_OFFICE, MANOHAR)",
    )
    args = parser.parse_args()

    config = PipelineConfig(
        project_id=args.project_id,
        structural_layers=tuple(args.layers),
        detection_mode=args.mode,
        min_slab_area_m2=args.min_area,
        merge_beam_grid_to_estimator_bays=True,
        slab_edge_expand_mm=args.edge_expand_mm,
        enable_deepseek_refinement=args.llm,
        enable_deepseek_component_classification=not args.no_deepseek,
        deepseek_model=args.deepseek_model,
        use_semantic_pipeline=not args.legacy_geometry,
        use_v4_pipeline=not args.legacy_geometry and not args.v3_semantic,
        enable_rag_classification=not args.v3_semantic,
    )
    result = run_pipeline(args.dxf.resolve(), args.output.resolve(), config)
    print(json.dumps({"totals": result["totals"], "outputs": result["output_files"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
