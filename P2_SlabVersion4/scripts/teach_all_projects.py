"""Ingest 3 estimator projects (tagged DXFs), rebuild KB/atlas, run DeepSeek pipeline."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

RUNS = [
    {
        "project_id": "INIZIO",
        "dxf": ROOT / "Data Source/Project1 - Inizio/Inizio Slab with tag.dxf",
        "output": ROOT / "Output/Project1 - Inizio",
        "layers": ["S-BEAM", "S_FRAMES"],
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
    print("=== Step 1–3: Excel + tagged atlas (fresh) + knowledge base ===")
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

    kb_path = ROOT / "data" / "knowledge_base" / "structural_kb.json"
    kb = json.loads(kb_path.read_text(encoding="utf-8"))
    print(
        f"KB: patterns={len(kb.get('pattern_knowledge', []))} "
        f"estimator_mappings={len(kb.get('estimator_mappings', []))}"
    )

    print("\n=== Step 4: Pipeline runs with DeepSeek (ambiguous entities only) ===")
    results = []
    for run in RUNS:
        run["output"].mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "run_pipeline.py"),
            str(run["dxf"]),
            "-o",
            str(run["output"]),
            "--project-id",
            run["project_id"],
            "--mode",
            "auto",
            "--layers",
            *run["layers"],
            "--min-area",
            str(run["min_area"]),
        ]
        print("Run:", run["project_id"], run["dxf"].name)
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        if proc.returncode != 0:
            print(proc.stderr or proc.stdout)
            proc.check_returncode()
        summary = json.loads(proc.stdout)
        deepseek = {}
        results_path = run["output"] / f"{run['dxf'].stem}_results.json"
        if results_path.exists():
            data = json.loads(results_path.read_text(encoding="utf-8"))
            deepseek = data.get("detection_notes", {}).get("classification", {})
        results.append(
            {
                "project_id": run["project_id"],
                "drawing": run["dxf"].name,
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
