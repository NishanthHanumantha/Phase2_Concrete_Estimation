"""Live progress bar for teach_all_projects.py background run."""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

STEPS = [
    ("Excel -> ground_truth JSON", 12, lambda s: s["ground_truth_ok"]),
    ("Tagged atlas build", 23, lambda s: s["atlas_ok"]),
    ("Knowledge base rebuild", 10, lambda s: s["kb_ok"]),
    ("Pipeline INIZIO + DeepSeek", 28, lambda s: s["inizio_ok"]),
    ("Pipeline TRUST_OFFICE + DeepSeek", 17, lambda s: s["trust_ok"]),
    ("Pipeline MANOHAR + DeepSeek", 10, lambda s: s["manohar_ok"]),
]

PIPELINE_OUTPUTS = {
    "inizio_ok": ROOT / "Output/Project1 - Inizio/Inizio Slab with tag_results.json",
    "trust_ok": ROOT
    / "Output/Project2 - TrustOffice/Trust office Slab & Beam with tag_results.json",
    "manohar_ok": ROOT
    / "Output/Project3 - Manohar/Manohar slab - beam -column with tag_results.json",
}


def _read_terminal_log() -> str:
    term_dir = Path.home() / ".cursor" / "projects"
    # Search recent terminal logs for teach_all_projects
    candidates = []
    for base in term_dir.glob("*/terminals/*.txt"):
        try:
            text = base.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "teach_all_projects.py" in text:
            candidates.append((base.stat().st_mtime, text))
    if not candidates:
        return ""
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def collect_status() -> dict:
    log = _read_terminal_log()
    gt_dir = ROOT / "data" / "ground_truth"
    gt_files = list(gt_dir.glob("*.json")) if gt_dir.exists() else []
    ground_truth_ok = len(gt_files) >= 3 and not (gt_dir / "Inizio_B2_LayerTest1.json").exists()

    atlas_path = ROOT / "data/atlas/component_atlas.json"
    kb_path = ROOT / "data/knowledge_base/structural_kb.json"
    atlas_ok = atlas_path.is_file() and atlas_path.stat().st_size > 1000
    kb_ok = kb_path.is_file() and kb_path.stat().st_size > 500

    status = {
        "ground_truth_ok": ground_truth_ok,
        "atlas_ok": atlas_ok,
        "kb_ok": kb_ok,
        "complete": "=== Complete ===" in log,
        "running_step4": "Step 4" in log or (kb_ok and not any(
            PIPELINE_OUTPUTS[k].is_file() for k in PIPELINE_OUTPUTS
        )),
    }
    for key, path in PIPELINE_OUTPUTS.items():
        status[key] = path.is_file()

    if atlas_path.is_file():
        try:
            data = json.loads(atlas_path.read_text(encoding="utf-8"))
            status["atlas_samples"] = data.get("sample_count", len(data.get("samples", [])))
        except Exception:
            status["atlas_samples"] = None
    else:
        status["atlas_samples"] = None

    # Infer active step from log tail
    if "Run: MANOHAR" in log:
        status["active"] = "MANOHAR pipeline"
    elif "Run: TRUST_OFFICE" in log:
        status["active"] = "TRUST_OFFICE pipeline"
    elif "Run: INIZIO" in log or (kb_ok and not status["inizio_ok"]):
        status["active"] = "INIZIO pipeline (may take 20-40 min)"
    elif not kb_ok:
        status["active"] = "Building knowledge base"
    elif not atlas_ok:
        status["active"] = "Building atlas"
    elif not ground_truth_ok:
        status["active"] = "Importing Excel"
    elif status["complete"]:
        status["active"] = "Finished"
    else:
        status["active"] = "Waiting / classifying"

    return status


def progress_pct(status: dict) -> int:
    if status.get("complete"):
        return 100
    pct = 0
    for _name, weight, done_fn in STEPS:
        if done_fn(status):
            pct += weight
    # Partial credit while first pipeline running
    if status["kb_ok"] and not status["inizio_ok"] and not status["trust_ok"]:
        pct = min(pct + 8, 99)
    return min(pct, 100)


def render_bar(pct: int, width: int = 40) -> str:
    filled = int(width * pct / 100)
    bar = "#" * filled + "-" * (width - filled)
    return f"[{bar}] {pct:3d}%"


def render_once() -> str:
    status = collect_status()
    pct = progress_pct(status)
    lines = [
        "",
        "SDIE v4 - teach_all_projects.py progress",
        render_bar(pct),
        f"Active: {status['active']}",
        "",
    ]
    for name, weight, done_fn in STEPS:
        mark = "[x]" if done_fn(status) else "[ ]"
        lines.append(f"  {mark} {name} ({weight}%)")
    if status.get("atlas_samples"):
        lines.append(f"\nAtlas samples: {status['atlas_samples']:,}")
    lines.append(f"Updated: {datetime.now().strftime('%H:%M:%S')}")
    if pct < 100:
        lines.append("Tip: INIZIO step scans large atlas - slow but running.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser(description="Progress bar for teach_all_projects")
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Refresh every 5 seconds until 100%%",
    )
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args()

    if not args.watch:
        print(render_once())
        return 0

    try:
        while True:
            text = render_once()
            # Clear screen (ANSI); works in most terminals
            sys.stdout.write("\033[2J\033[H" + text)
            sys.stdout.flush()
            status = collect_status()
            if status.get("complete") or progress_pct(status) >= 100:
                if all(status.get(k) for k in PIPELINE_OUTPUTS):
                    break
            if status["inizio_ok"] and status["trust_ok"] and status["manohar_ok"]:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped watching.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
