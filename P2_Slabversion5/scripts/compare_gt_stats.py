"""Quick compare GT match stats across result JSON files."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sdie.validation.gt_match import annotate_slabs_with_gt, load_gt_xlsx


def main() -> None:
    gt = load_gt_xlsx(
        ROOT / "Data Source/Ground Truths/TestGT/TrustOffice_FF_ExpectedOutput.xlsx"
    )
    paths = sys.argv[1:] or [
        "Output/TestRun_V5_DeepSeek/TrustOffice_FF_LayerTest_RAG_results.json",
        "Output/TestRun_V5_fixed2/TrustOffice_FF_LayerTest_RAG_results.json",
    ]
    for rel in paths:
        path = ROOT / rel
        r = json.loads(path.read_text(encoding="utf-8"))
        ann = annotate_slabs_with_gt(r["slabs"], gt)
        s = ann["summary"]
        t = r["totals"]
        det = r.get("detection_notes", {})
        print(f"=== {path.name} ===")
        print(f"  area={t['area_m2']:.1f} m2  slabs={t['slab_count']}")
        print(
            f"  semantic_excl={det.get('semantic_exclusion_area_m2')} "
            f"parts={det.get('semantic_exclusion_parts')}"
        )
        print(
            f"  matched={s['matched_count']} weak={s['weak_count']} "
            f"missed={s['missed_count']} extra={s['extra_count']} "
            f"partition={s.get('partition_match_count', 0)}"
        )
        print()


if __name__ == "__main__":
    main()
