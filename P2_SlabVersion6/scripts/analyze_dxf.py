"""Quick DXF audit for benchmark drawings."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import ezdxf
from ezdxf import bbox

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sdie.ingestion.dxf_reader import load_drawing
from sdie.ingestion.layer_discovery import discover_drawing_layers


def analyze(path: Path) -> dict:
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()

    entity_counts: Counter = Counter()
    layer_entity_counts: Counter = Counter()
    layer_types: dict[str, Counter] = defaultdict(Counter)
    texts: list[dict] = []
    closed_polys: list[dict] = []
    lines_by_layer: Counter = Counter()

    for e in msp:
        t = e.dxftype()
        layer = e.dxf.layer
        entity_counts[t] += 1
        layer_entity_counts[layer] += 1
        layer_types[layer][t] += 1

        if t in ("TEXT", "MTEXT"):
            content = e.dxf.text if t == "TEXT" else e.text
            texts.append(
                {
                    "type": t,
                    "layer": layer,
                    "text": (content or "").strip()[:120],
                    "x": round(e.dxf.insert.x, 3),
                    "y": round(e.dxf.insert.y, 3),
                }
            )

        if t == "LWPOLYLINE" and e.closed:
            try:
                area = abs(e.area()) if hasattr(e, "area") else None
            except Exception:
                area = None
            closed_polys.append(
                {
                    "layer": layer,
                    "vertices": len(e),
                    "area": round(area, 3) if area else None,
                    "handle": e.dxf.handle,
                }
            )

        if t == "LINE":
            lines_by_layer[layer] += 1

    # Extents
    try:
        ext = bbox.extents(msp, fast=True)
        extents = {
            "min": [round(ext.extmin.x, 3), round(ext.extmin.y, 3)],
            "max": [round(ext.extmax.x, 3), round(ext.extmax.y, 3)],
            "width": round(ext.size.x, 3),
            "height": round(ext.size.y, 3),
        }
    except Exception:
        extents = None

    # Units from header
    insunits = doc.header.get("$INSUNITS", 0)
    unit_names = {
        0: "unitless",
        1: "inches",
        2: "feet",
        3: "mm",
        4: "cm",
        5: "m",
        6: "km",
    }

    # Thickness-like text
    thk_keywords = []
    for t in texts:
        txt = t["text"].upper()
        if any(k in txt for k in ("THK", "THICK", "SLAB", "RCC", "MM", "CONC")):
            thk_keywords.append(t)

    return {
        "file": path.name,
        "dxf_version": doc.dxfversion,
        "insunits": insunits,
        "insunits_name": unit_names.get(insunits, f"code_{insunits}"),
        "layer_count": len(doc.layers),
        "layers": sorted(layer_entity_counts.keys()),
        "entity_counts": dict(entity_counts.most_common()),
        "entities_per_layer": dict(layer_entity_counts.most_common()),
        "layer_entity_breakdown": {
            k: dict(v.most_common()) for k, v in sorted(layer_types.items())
        },
        "extents": extents,
        "closed_lwpolyline_count": len(closed_polys),
        "closed_polys_by_layer": dict(
            Counter(p["layer"] for p in closed_polys).most_common()
        ),
        "largest_closed_polys": sorted(
            [p for p in closed_polys if p["area"]],
            key=lambda p: p["area"],
            reverse=True,
        )[:15],
        "thickness_related_text": thk_keywords[:40],
        "sample_texts": texts[:50],
        "total_text_count": len(texts),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="DXF layer/entity audit (V6)")
    parser.add_argument("dxf", type=Path, nargs="?", help="Input DXF")
    parser.add_argument("-o", "--output", type=Path, default=None)
    parser.add_argument("--project-id", default="INIZIO")
    args = parser.parse_args()
    dxf = args.dxf or Path(
        ROOT / "Data Source" / "TestInput" / "TrustOffice_FF_LayerTest_RAG.dxf"
    )
    out = args.output or ROOT / "data" / "audits" / f"{dxf.stem}_audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    result = analyze(dxf)
    doc, _meta = load_drawing(dxf)
    plan = discover_drawing_layers(doc.modelspace(), project_id=args.project_id)
    result["v6_layer_plan"] = {
        "method": plan.method,
        "structural_layers": list(plan.structural_layers),
        "annotation_layers": list(plan.annotation_layers),
        "frame_layers": list(plan.frame_layers),
        "cutout_layers": list(plan.cutout_layers),
        "notes": plan.notes,
    }
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result["v6_layer_plan"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
