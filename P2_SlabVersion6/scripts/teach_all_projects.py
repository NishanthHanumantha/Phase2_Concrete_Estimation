"""Ingest teach corpora, rebuild KB/atlas, run pipeline on each project's inference DXF."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sdie.project_knowledge.paths import inizio_raw_dxf_path

RUNS = [
    {
        "project_id": "INIZIO",
        "dxf_fn": inizio_raw_dxf_path,
        "output": ROOT / "Output/Inizio_Revised",
        "auto_layers": True,
        "min_area": 0.4,
    },
    {
        "project_id": "TRUST_OFFICE",
        "dxf": ROOT
        / "Data Source/Project2 - TrustOffice/Trust office Slab & Beam with tag.dxf",
        "output": ROOT / "Output/Project2 - TrustOffice",
        "layers": ["S_FRAMES", "STR-CUTOUT"],
        "min_area": 0.4,
    },
    {
        "project_id": "MANOHAR",
        "dxf": ROOT
        / "Data Source/Project3 - Manohar/Manohar slab - beam -column with tag.dxf",
        "output": ROOT / "Output/Project3 - Manohar",
        "layers": ["S_FRAMES", "STR-CUTOUT"],
        "min_area": 0.4,
    },
]


def main() -> int:
    print("=== Step 1: Excel import + full atlas refresh + knowledge base ===")
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "ingest_estimator_workbooks.py"),
            "--build-atlas",
            "--fresh-atlas",
            "--build-kb",
        ],
        cwd=ROOT,
        check=True,
    )

    print("\n=== Step 2: INIZIO Revised teach (merge layer profiles + atlas) ===")
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "teach_inizio_revised.py"), "--skip-inference"],
        cwd=ROOT,
        check=True,
    )

    kb_path = ROOT / "data" / "knowledge_base" / "structural_kb.json"
    kb = json.loads(kb_path.read_text(encoding="utf-8"))
    print(
        f"KB: patterns={len(kb.get('pattern_knowledge', []))} "
        f"estimator_mappings={len(kb.get('estimator_mappings', []))}"
    )

    print("\n=== Step 3: Pipeline runs ===")
    results = []
    for run in RUNS:
        run["output"].mkdir(parents=True, exist_ok=True)
        dxf = run["dxf_fn"](ROOT) if "dxf_fn" in run else run["dxf"]
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "run_pipeline.py"),
            str(dxf),
            "-o",
            str(run["output"]),
            "--project-id",
            run["project_id"],
            "--mode",
            "auto",
            "--min-area",
            str(run["min_area"]),
        ]
        if run.get("auto_layers"):
            cmd.append("--auto-layers")
        else:
            cmd.extend(["--layers", *run["layers"]])
        print("Run:", run["project_id"], dxf.name)
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        if proc.returncode != 0:
            print(proc.stderr or proc.stdout)
            proc.check_returncode()
        summary = json.loads(proc.stdout)
        deepseek = {}
        results_path = run["output"] / f"{dxf.stem}_results.json"
        if results_path.exists():
            data = json.loads(results_path.read_text(encoding="utf-8"))
            deepseek = data.get("detection_notes", {}).get("classification", {})
        results.append(
            {
                "project_id": run["project_id"],
                "drawing": dxf.name,
                "totals": summary.get("totals"),
                "deepseek": deepseek,
            }
        )
        print(json.dumps(results[-1], indent=2))

    print("\n=== Complete ===")
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
