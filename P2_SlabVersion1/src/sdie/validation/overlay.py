from __future__ import annotations

from pathlib import Path

from shapely import wkt


def write_svg_overlay(
    path: Path,
    slabs: list[dict],
    extents: dict | None,
    *,
    title: str = "SDIE Slab Detection",
) -> None:
    if not slabs:
        path.write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg"><text x="10" y="20">{title}: no slabs</text></svg>',
            encoding="utf-8",
        )
        return

    polys = [wkt.loads(s["polygon_wkt"]) for s in slabs]
    if extents:
        xmin, ymin = extents["min"]
        xmax, ymax = extents["max"]
    else:
        xmin = min(p.bounds[0] for p in polys)
        ymin = min(p.bounds[1] for p in polys)
        xmax = max(p.bounds[2] for p in polys)
        ymax = max(p.bounds[3] for p in polys)

    pad = max((xmax - xmin), (ymax - ymin)) * 0.05 or 100
    xmin -= pad
    ymin -= pad
    xmax += pad
    ymax += pad
    w = xmax - xmin
    h = ymax - ymin
    svg_w, svg_h = 1200, 900

    def tx(x: float) -> float:
        return (x - xmin) / w * svg_w if w else 0

    def ty(y: float) -> float:
        return svg_h - (y - ymin) / h * svg_h if h else 0

    colors = ["#4CAF50", "#2196F3", "#FF9800", "#9C27B0", "#00BCD4"]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">',
        f'<rect width="100%" height="100%" fill="#1e1e1e"/>',
        f'<text x="12" y="24" fill="#fff" font-size="14" font-family="sans-serif">{title}</text>',
    ]

    for i, slab in enumerate(slabs):
        poly = wkt.loads(slab["polygon_wkt"])
        color = colors[i % len(colors)]
        coords = " ".join(f"{tx(x):.2f},{ty(y):.2f}" for x, y in poly.exterior.coords)
        parts.append(
            f'<polygon points="{coords}" fill="{color}" fill-opacity="0.35" '
            f'stroke="{color}" stroke-width="2"/>'
        )
        cx, cy = slab["centroid_cm"]
        label = f'{slab["slab_id"]} {slab["area_m2"]:.1f}m² {slab["thickness_mm"]}mm'
        parts.append(
            f'<text x="{tx(cx):.1f}" y="{ty(cy):.1f}" fill="#fff" font-size="11" '
            f'font-family="sans-serif">{label}</text>'
        )

    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")
