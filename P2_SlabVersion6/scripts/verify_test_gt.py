"""Compare TrustOffice_FF pipeline output vs TestGT Excel."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sdie.validation.gt_match import annotate_slabs_with_gt, greedy_match, load_gt_xlsx


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Compare pipeline output vs TestGT Excel")
    parser.add_argument(
        "--results",
        type=Path,
        default=ROOT / "Output/TestOutput_V4/TrustOffice_FF_LayerTest_RAG_results.json",
    )
    args = parser.parse_args()

    gt_path = ROOT / "Data Source/Ground Truths/TestGT/TrustOffice_FF_ExpectedOutput.xlsx"
    results_path = args.results

    gt = load_gt_xlsx(gt_path)
    results = json.loads(results_path.read_text(encoding="utf-8"))
    model = results["slabs"]
    totals = results["totals"]
    cfg = results.get("config", {})

    exp_area = sum(s["area_m2"] for s in gt)
    exp_conc = sum(s["concrete_m3"] for s in gt)

    print("=== TOTALS ===")
    print(f"Expected: {len(gt)} slabs, {exp_area:.3f} m2 area, {exp_conc:.3f} m3 concrete")
    print(
        f"Model:    {totals['slab_count']} slabs, {totals['area_m2']:.3f} m2 area, "
        f"{totals['concrete_m3']:.3f} m3 concrete"
    )
    print(f"min_slab_area_m2 config: {cfg.get('min_slab_area_m2')}")
    print()

    below_min = [s for s in gt if s["area_m2"] < cfg.get("min_slab_area_m2", 0)]
    print(f"GT slabs below min_slab_area_m2 ({cfg.get('min_slab_area_m2')}): {len(below_min)}")
    for s in below_min:
        print(f"  {s['id']}: {s['area_m2']:.3f} m2 ({s['length_m']}x{s['breadth_m']}m)")
    print()

    annotation = annotate_slabs_with_gt(model, gt)
    missed = annotation["missed"]
    weak = annotation["weak"]
    extra = annotation["extra"]
    partition = annotation.get("partition", [])

    print("=== MISSED GT SLABS (no model match within tolerance) ===")
    for entry in missed:
        err = entry.get("nearest_err_pct")
        print(
            f"  {entry['gt_id']}: expected {entry['expected_area_m2']:.3f} m2 "
            f"({entry.get('length_m')}x{entry.get('breadth_m')}m) nearest_err={err:.1f}%"
            if err is not None
            else f"  {entry['gt_id']}: expected {entry['expected_area_m2']:.3f} m2"
        )
    print()

    print("=== WEAK MATCHES (area/aspect not within strong-match band) ===")
    for entry in weak[:35]:
        if "slab_ids" in entry:
            print(
                f"  {entry['gt_id']} ({entry['expected_area_m2']:.3f}) -> "
                f"{entry['slab_ids']} ({entry['actual_area_m2']:.3f}) "
                f"err={entry['err_pct']:.1f}% [partition]"
            )
        else:
            print(
                f"  {entry['gt_id']} ({entry['expected_area_m2']:.3f}) -> "
                f"{entry['slab_id']} ({entry['actual_area_m2']:.3f}) "
                f"err={entry['err_pct']:.1f}%"
            )
    if len(weak) > 35:
        print(f"  ... and {len(weak) - 35} more")
    print()

    if partition:
        print(f"=== PARTITION MATCHES (GT bay = sum of model cells): {len(partition)} ===")
        for entry in partition[:10]:
            print(
                f"  {entry['gt_id']}: {entry['slab_ids']} total={entry['actual_area_m2']:.3f} "
                f"expected={entry['expected_area_m2']:.3f} err={entry['err_pct']:.1f}%"
            )
        print()

    print("=== EXTRA MODEL SLABS (no GT match) ===")
    for act in extra:
        print(f"  {act['slab_id']}: {act['area_m2']:.3f} m2 strategy={act.get('strategy')}")
    print()
    print("=== OVERLAY GT SUMMARY ===")
    print(json.dumps(annotation["summary"], indent=2))

    small = [s for s in gt if s["area_m2"] < 8]
    medium = [s for s in gt if 8 <= s["area_m2"] < 14]
    large = [s for s in gt if s["area_m2"] >= 14]
    print("=== GT SIZE BUCKETS ===")
    print(f"  small (<8 m2): {len(small)} slabs, {sum(s['area_m2'] for s in small):.3f} m2")
    print(f"  medium (8-14): {len(medium)} slabs, {sum(s['area_m2'] for s in medium):.3f} m2")
    print(f"  large (>=14): {len(large)} slabs, {sum(s['area_m2'] for s in large):.3f} m2")


if __name__ == "__main__":
    main()
