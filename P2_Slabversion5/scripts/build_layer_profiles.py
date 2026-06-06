"""Learn per-project layer profiles from manifest supervised teaching DXFs."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sdie.classification.layer_profiles import (
    default_profiles_path,
    learn_profiles_from_manifest,
    save_profiles,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build data/layer_profiles.json")
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
        default=default_profiles_path(),
    )
    parser.add_argument("--min-samples", type=int, default=5)
    parser.add_argument("--min-fraction", type=float, default=0.55)
    args = parser.parse_args()

    rules = learn_profiles_from_manifest(
        args.manifest,
        args.data_source,
        min_samples=args.min_samples,
        min_fraction=args.min_fraction,
    )
    out = save_profiles(rules, args.output)

    by_project: dict[str, list] = {}
    for r in rules:
        by_project.setdefault(r.project_id, []).append(
            {
                "layer": r.layer,
                "entity_type": r.entity_type,
                "type": r.component_type,
                "confidence": r.confidence,
                "n": r.sample_count,
            }
        )

    summary = {
        "output": str(out),
        "rule_count": len(rules),
        "by_project": by_project,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
