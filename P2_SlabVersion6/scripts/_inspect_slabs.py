"""Quick slab duplicate / count analysis for one results file."""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    stem = sys.argv[1] if len(sys.argv) > 1 else "Inizio_63F_Raw_Layer_Revised1"
    out_dir = ROOT / "Output" / "Inizio_63F_Beam_Output"
    results_path = out_dir / f"{stem}_results.json"
    overlay_path = out_dir / f"{stem}_overlay.html"

    results = json.loads(results_path.read_text(encoding="utf-8"))
    html = overlay_path.read_text(encoding="utf-8")
    slabs = results.get("slabs") or []

    print("=== RESULTS JSON ===")
    print(f"Slab count: {len(slabs)}")
    print(f"Total area m2: {sum(s.get('area_m2', 0) for s in slabs):.3f}")
    print(f"Total concrete m3: {sum(s.get('concrete_m3', 0) for s in slabs):.3f}")

    poly_ids = re.findall(r'data-slab-id="(SLAB-\d+)"', html)
    print("\n=== OVERLAY HTML ===")
    print(f"Slab polygons: {len(poly_ids)}")
    print(f"Unique slab IDs in SVG: {len(set(poly_ids))}")

    print("\nStrategies:", dict(Counter(s.get("strategy") for s in slabs)))
    print("Thicknesses:", dict(Counter(s.get("thickness_mm") for s in slabs)))

    small = [s for s in slabs if s.get("area_m2", 0) < 5]
    print(f"\nSlabs < 5 m2: {len(small)}")
    for s in sorted(small, key=lambda x: x.get("area_m2", 0)):
        c = s.get("centroid_cm") or [0, 0]
        print(
            f"  {s['slab_id']}: {s['area_m2']:.3f} m2, thk={s.get('thickness_mm')}, "
            f"centroid=({c[0]:.0f},{c[1]:.0f})"
        )

    # duplicate by area only
    area_groups: dict[float, list[str]] = defaultdict(list)
    for s in slabs:
        area_groups[round(s.get("area_m2", 0), 3)].append(s["slab_id"])
    area_dups = {k: v for k, v in area_groups.items() if len(v) > 1}
    print(f"\nDuplicate area groups: {len(area_dups)}")
    for area, ids in sorted(area_dups.items(), key=lambda x: -len(x[1])):
        print(f"  {area} m2 x{len(ids)}: {ids}")

    # duplicate by bounds
    bounds_groups: dict[str, list[str]] = defaultdict(list)
    for s in slabs:
        b = s.get("bounds_cm")
        if b:
            key = ",".join(f"{x:.1f}" for x in b[:4])
            bounds_groups[key].append(s["slab_id"])
    bounds_dups = {k: v for k, v in bounds_groups.items() if len(v) > 1}
    print(f"\nExact duplicate bounds: {len(bounds_dups)}")

    # cluster by similar centroid (within 50cm) and same area
    clusters: list[list[dict]] = []
    used = set()
    for i, s in enumerate(slabs):
        if i in used:
            continue
        cluster = [s]
        used.add(i)
        c1 = s.get("centroid_cm") or [0, 0]
        a1 = round(s.get("area_m2", 0), 2)
        for j, t in enumerate(slabs):
            if j in used:
                continue
            c2 = t.get("centroid_cm") or [0, 0]
            a2 = round(t.get("area_m2", 0), 2)
            dist = ((c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2) ** 0.5
            if a1 == a2 and dist < 50:
                cluster.append(t)
                used.add(j)
        if len(cluster) > 1:
            clusters.append(cluster)

    print(f"\nSpatial duplicate clusters (same area, centroid <50cm): {len(clusters)}")
    unique_est = len(slabs)
    for cl in clusters:
        ids = [s["slab_id"] for s in cl]
        c = cl[0].get("centroid_cm") or [0, 0]
        print(f"  {ids} @ area={cl[0]['area_m2']:.3f}, centroid=({c[0]:.0f},{c[1]:.0f})")
        unique_est -= len(cl) - 1

    print(f"\nEstimated unique slabs (after dedup clusters): ~{unique_est}")

    # large slabs only
    large = [s for s in slabs if s.get("area_m2", 0) >= 10]
    print(f"\nSlabs >= 10 m2: {len(large)}")
    for s in sorted(large, key=lambda x: -x.get("area_m2", 0)):
        c = s.get("centroid_cm") or [0, 0]
        print(f"  {s['slab_id']}: {s['area_m2']:.2f} m2, thk={s.get('thickness_mm')}, ({c[0]:.0f},{c[1]:.0f})")


if __name__ == "__main__":
    main()
