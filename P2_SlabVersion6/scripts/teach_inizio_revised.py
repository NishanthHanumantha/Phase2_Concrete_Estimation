"""Teach INIZIO from Revised Project Knowledge, then run inference on the raw plan."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sdie.project_knowledge.paths import inizio_raw_dxf_path


def _run(cmd: list[str], *, label: str) -> None:
    print(f"\n=== {label} ===")
    print(" ".join(str(c) for c in cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild INIZIO teach artifacts from Revised Project Knowledge"
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=ROOT,
    )
    parser.add_argument(
        "--skip-teach",
        action="store_true",
        help="Skip layer profiles / atlas / KB rebuild",
    )
    parser.add_argument(
        "--skip-inference",
        action="store_true",
        help="Only rebuild teach artifacts",
    )
    parser.add_argument(
        "--no-deepseek",
        action="store_true",
        help="Disable DeepSeek entirely (default: DeepSeek for ambiguous components only)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=ROOT / "Output" / "Inizio_Revised",
    )
    args = parser.parse_args()

    raw_dxf = inizio_raw_dxf_path(args.project_root)
    if not raw_dxf.is_file():
        raise FileNotFoundError(f"INIZIO raw DXF not found: {raw_dxf}")

    if not args.skip_teach:
        _run(
            [
                sys.executable,
                str(ROOT / "scripts" / "build_layer_profiles.py"),
                "--project-root",
                str(args.project_root),
                "--project-id",
                "INIZIO",
                "--merge-projects",
                "INIZIO",
            ],
            label="Layer profiles (INIZIO merge)",
        )
        _run(
            [
                sys.executable,
                str(ROOT / "scripts" / "ingest_estimator_workbooks.py"),
                "--project-root",
                str(args.project_root),
                "--build-atlas",
                "--merge-atlas",
                "INIZIO",
                "--atlas-project-id",
                "INIZIO",
                "--build-kb",
            ],
            label="Atlas + knowledge base (INIZIO merge)",
        )

    if args.skip_inference:
        print("\nTeach complete (inference skipped).")
        return 0

    args.output.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "run_pipeline.py"),
        str(raw_dxf),
        "-o",
        str(args.output),
        "--project-id",
        "INIZIO",
        "--mode",
        "auto",
        "--auto-layers",
        "--min-area",
        "0.4",
    ]
    if args.no_deepseek:
        cmd.append("--no-deepseek")
    else:
        print("DeepSeek: enabled for ambiguous components only (not slab LLM refinement)")

    _run(cmd, label="Raw inference")
    results_path = args.output / f"{raw_dxf.stem}_results.json"
    if results_path.exists():
        data = json.loads(results_path.read_text(encoding="utf-8"))
        print(json.dumps(data.get("totals", {}), indent=2))
    print(f"\nOutput: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
