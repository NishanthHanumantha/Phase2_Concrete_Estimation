"""Epic 1 — Build V4 Component Knowledge Base (RAG corpus)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sdie.rag.builder import build_knowledge_base


def main() -> int:
    parser = argparse.ArgumentParser(description="Build SDIE v4 structural knowledge base")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=ROOT / "data" / "knowledge_base" / "structural_kb.json",
    )
    parser.add_argument(
        "--atlas",
        type=Path,
        default=ROOT / "data" / "atlas" / "component_atlas.json",
    )
    args = parser.parse_args()
    kb = build_knowledge_base(
        project_root=ROOT,
        atlas_path=args.atlas,
        output_path=args.output,
    )
    print(
        f"Knowledge base: {args.output}\n"
        f"  layers={len(kb.layer_knowledge)} "
        f"annotations={len(kb.annotation_knowledge)} "
        f"patterns={len(kb.pattern_knowledge)} "
        f"estimator_mappings={len(kb.estimator_mappings)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
