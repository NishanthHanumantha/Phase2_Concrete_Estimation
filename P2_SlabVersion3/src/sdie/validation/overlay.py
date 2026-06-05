from __future__ import annotations

import html
from pathlib import Path

from shapely import wkt

THICKNESS_COLORS: dict[int, str] = {
    125: "#81C784",
    150: "#66BB6A",
    175: "#4CAF50",
    200: "#2196F3",
    225: "#7E57C2",
    275: "#FF9800",
    300: "#F44336",
}
DEFAULT_FILL = "#607D8B"


def _slab_bounds(polys: list) -> tuple[float, float, float, float]:
    xmin = min(p.bounds[0] for p in polys)
    ymin = min(p.bounds[1] for p in polys)
    xmax = max(p.bounds[2] for p in polys)
    ymax = max(p.bounds[3] for p in polys)
    return xmin, ymin, xmax, ymax


def _resolve_view_bounds(
    polys: list,
    extents: dict | None,
    *,
    crop_to_slabs: bool,
) -> tuple[float, float, float, float]:
    if crop_to_slabs and polys:
        xmin, ymin, xmax, ymax = _slab_bounds(polys)
    elif extents:
        xmin, ymin = extents["min"]
        xmax, ymax = extents["max"]
    else:
        xmin, ymin, xmax, ymax = _slab_bounds(polys)

    pad = max((xmax - xmin), (ymax - ymin)) * 0.03 or 500.0
    return xmin - pad, ymin - pad, xmax + pad, ymax + pad


def _label_policy(slab_count: int) -> tuple[bool, float]:
    """Return (show_labels, min_area_m2_for_label)."""
    if slab_count <= 35:
        return True, 0.0
    if slab_count <= 100:
        return True, 12.0
    return False, 0.0


def _stroke_width(slab_count: int) -> float:
    if slab_count <= 40:
        return 1.5
    if slab_count <= 120:
        return 0.8
    return 0.35


def _color_for_slab(slab: dict, index: int) -> str:
    thk = slab.get("thickness_mm")
    if isinstance(thk, int) and thk in THICKNESS_COLORS:
        return THICKNESS_COLORS[thk]
    return DEFAULT_FILL


def _polygon_svg_coords(poly, tx, ty) -> str:
    return " ".join(f"{tx(x):.2f},{ty(y):.2f}" for x, y in poly.exterior.coords)


def _append_polygon_parts(
    parts: list[str],
    geom,
    tx,
    ty,
    *,
    fill: str,
    fill_opacity: float,
    stroke: str,
    stroke_width: float,
) -> None:
    if geom is None or geom.is_empty:
        return
    geoms = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
    for poly in geoms:
        if poly.geom_type != "Polygon":
            continue
        coords = _polygon_svg_coords(poly, tx, ty)
        parts.append(
            f'<polygon points="{coords}" fill="{fill}" fill-opacity="{fill_opacity}" '
            f'stroke="{stroke}" stroke-width="{stroke_width}"/>'
        )


def build_svg_content(
    slabs: list[dict],
    extents: dict | None,
    *,
    title: str = "SDIE Slab Detection",
    crop_to_slabs: bool = True,
    totals: dict | None = None,
    excluded_wkt: str | None = None,
) -> str:
    if not slabs:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 80">'
            f'<text x="10" y="40" fill="#ccc" font-size="14">{html.escape(title)}: no slabs</text></svg>'
        )

    polys = [wkt.loads(s["polygon_wkt"]) for s in slabs]
    xmin, ymin, xmax, ymax = _resolve_view_bounds(
        polys, extents, crop_to_slabs=crop_to_slabs
    )
    w = xmax - xmin
    h = ymax - ymin
    aspect = w / h if h else 1.0
    svg_h = 1600
    svg_w = max(1200, min(3200, int(svg_h * aspect)))

    show_labels, min_label_area = _label_policy(len(slabs))
    stroke = _stroke_width(len(slabs))
    fill_opacity = 0.55 if len(slabs) > 80 else 0.4

    def tx(x: float) -> float:
        return (x - xmin) / w * svg_w if w else 0.0

    def ty(y: float) -> float:
        return svg_h - (y - ymin) / h * svg_h if h else 0.0

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" '
        f'viewBox="0 0 {svg_w} {svg_h}">',
        '<rect width="100%" height="100%" fill="#121212"/>',
        f'<text x="16" y="28" fill="#e0e0e0" font-size="18" font-family="Segoe UI, sans-serif" '
        f'font-weight="600">{html.escape(title)}</text>',
    ]

    if totals:
        summary = (
            f'{totals.get("slab_count", len(slabs))} bays · '
            f'{totals.get("area_m2", 0):.1f} m² · '
            f'{totals.get("concrete_m3", 0):.1f} m³'
        )
        parts.append(
            f'<text x="16" y="50" fill="#9e9e9e" font-size="13" font-family="Segoe UI, sans-serif">'
            f'{html.escape(summary)}</text>'
        )

    if excluded_wkt:
        ex_geom = wkt.loads(excluded_wkt)
        _append_polygon_parts(
            parts,
            ex_geom,
            tx,
            ty,
            fill="#B71C1C",
            fill_opacity=0.45,
            stroke="#EF5350",
            stroke_width=0.5,
        )

    for i, slab in enumerate(slabs):
        poly = polys[i]
        color = _color_for_slab(slab, i)
        coords = " ".join(f"{tx(x):.2f},{ty(y):.2f}" for x, y in poly.exterior.coords)
        parts.append(
            f'<polygon points="{coords}" fill="{color}" fill-opacity="{fill_opacity}" '
            f'stroke="{color}" stroke-width="{stroke}" stroke-opacity="0.9"/>'
        )
        if show_labels and slab["area_m2"] >= min_label_area:
            cx, cy = slab["centroid_cm"]
            label = f'{slab["slab_id"]} {slab["thickness_mm"]}mm'
            parts.append(
                f'<text x="{tx(cx):.1f}" y="{ty(cy):.1f}" fill="#fff" font-size="10" '
                f'text-anchor="middle" dominant-baseline="middle" '
                f'font-family="Segoe UI, sans-serif" paint-order="stroke" '
                f'stroke="#000" stroke-width="3">{html.escape(label)}</text>'
            )

    legend_x = svg_w - 200
    legend_y = 24
    legend_h = 88 if excluded_wkt else 72
    parts.append(
        f'<rect x="{legend_x - 12}" y="{legend_y - 8}" width="188" height="{legend_h}" '
        f'fill="#1e1e1e" fill-opacity="0.85" rx="6"/>'
    )
    if excluded_wkt:
        parts.append(
            f'<rect x="{legend_x}" y="{legend_y + 58}" width="14" height="14" fill="#B71C1C" rx="2"/>'
            f'<text x="{legend_x + 22}" y="{legend_y + 70}" fill="#e0e0e0" font-size="11" '
            f'font-family="Segoe UI, sans-serif">Excluded (non-slab)</text>'
        )
    parts.append(
        f'<text x="{legend_x}" y="{legend_y + 10}" fill="#bdbdbd" font-size="12" '
        f'font-family="Segoe UI, sans-serif">Thickness</text>'
    )
    used_thk = sorted({s["thickness_mm"] for s in slabs})
    for j, thk in enumerate(used_thk[:4]):
        c = THICKNESS_COLORS.get(thk, DEFAULT_FILL)
        ly = legend_y + 28 + j * 16
        parts.append(
            f'<rect x="{legend_x}" y="{ly - 10}" width="14" height="14" fill="{c}" rx="2"/>'
            f'<text x="{legend_x + 22}" y="{ly + 2}" fill="#e0e0e0" font-size="11" '
            f'font-family="Segoe UI, sans-serif">{thk} mm</text>'
        )
    if not show_labels:
        parts.append(
            f'<text x="{legend_x}" y="{legend_y + 56}" fill="#757575" font-size="10" '
            f'font-family="Segoe UI, sans-serif">Labels hidden (dense grid)</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def write_svg_overlay(
    path: Path,
    slabs: list[dict],
    extents: dict | None,
    *,
    title: str = "SDIE Slab Detection",
    totals: dict | None = None,
) -> None:
    path.write_text(
        build_svg_content(slabs, extents, title=title, totals=totals),
        encoding="utf-8",
    )


def write_html_overlay_viewer(
    path: Path,
    svg_content: str,
    *,
    title: str = "SDIE Slab Overlay",
) -> None:
    """Self-contained HTML with pan/zoom for large dense overlays."""
    escaped_title = html.escape(title)
    # Embed SVG without xml declaration; escape for script safety not needed in body
    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{escaped_title}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; }}
    html, body {{ height: 100%; overflow: hidden; background: #0d0d0d; font-family: "Segoe UI", sans-serif; }}
    #toolbar {{
      position: fixed; top: 0; left: 0; right: 0; z-index: 10;
      display: flex; align-items: center; gap: 12px; padding: 10px 16px;
      background: rgba(20,20,20,0.92); border-bottom: 1px solid #333; color: #e0e0e0;
    }}
    #toolbar button {{
      background: #2a2a2a; color: #eee; border: 1px solid #444; border-radius: 6px;
      padding: 6px 14px; cursor: pointer; font-size: 13px;
    }}
    #toolbar button:hover {{ background: #383838; }}
    #hint {{ color: #888; font-size: 12px; margin-left: auto; }}
    #viewport {{
      position: absolute; top: 48px; left: 0; right: 0; bottom: 0;
      overflow: hidden; cursor: grab;
    }}
    #viewport.dragging {{ cursor: grabbing; }}
    #stage {{
      transform-origin: 0 0;
      display: inline-block;
    }}
    #stage svg {{ display: block; max-width: none; }}
  </style>
</head>
<body>
  <div id="toolbar">
    <strong>{escaped_title}</strong>
    <button type="button" id="zoom-in">Zoom +</button>
    <button type="button" id="zoom-out">Zoom −</button>
    <button type="button" id="fit">Fit to screen</button>
    <button type="button" id="reset">100%</button>
    <span id="hint">Scroll to zoom · Drag to pan</span>
  </div>
  <div id="viewport">
    <div id="stage">{svg_content}</div>
  </div>
  <script>
(function () {{
  const viewport = document.getElementById("viewport");
  const stage = document.getElementById("stage");
  const svg = stage.querySelector("svg");
  if (!svg) return;

  let scale = 1;
  let panX = 0;
  let panY = 0;
  let dragging = false;
  let lastX = 0;
  let lastY = 0;

  function applyTransform() {{
    stage.style.transform = `translate(${{panX}}px, ${{panY}}px) scale(${{scale}})`;
  }}

  function fitToScreen() {{
    const vb = svg.viewBox.baseVal;
    const sw = vb.width || svg.width.baseVal.value || 1200;
    const sh = vb.height || svg.height.baseVal.value || 900;
    const vw = viewport.clientWidth;
    const vh = viewport.clientHeight;
    scale = Math.min(vw / sw, vh / sh) * 0.95;
    panX = (vw - sw * scale) / 2;
    panY = (vh - sh * scale) / 2;
    applyTransform();
  }}

  function zoomAt(cx, cy, factor) {{
    const rect = viewport.getBoundingClientRect();
    const mx = cx - rect.left;
    const my = cy - rect.top;
    const newScale = Math.max(0.05, Math.min(40, scale * factor));
    panX = mx - (mx - panX) * (newScale / scale);
    panY = my - (my - panY) * (newScale / scale);
    scale = newScale;
    applyTransform();
  }}

  viewport.addEventListener("wheel", (e) => {{
    e.preventDefault();
    zoomAt(e.clientX, e.clientY, e.deltaY < 0 ? 1.15 : 1 / 1.15);
  }}, {{ passive: false }});

  viewport.addEventListener("mousedown", (e) => {{
    if (e.button !== 0) return;
    dragging = true;
    lastX = e.clientX;
    lastY = e.clientY;
    viewport.classList.add("dragging");
  }});
  window.addEventListener("mousemove", (e) => {{
    if (!dragging) return;
    panX += e.clientX - lastX;
    panY += e.clientY - lastY;
    lastX = e.clientX;
    lastY = e.clientY;
    applyTransform();
  }});
  window.addEventListener("mouseup", () => {{
    dragging = false;
    viewport.classList.remove("dragging");
  }});

  document.getElementById("zoom-in").onclick = () => {{
    const r = viewport.getBoundingClientRect();
    zoomAt(r.left + r.width / 2, r.top + r.height / 2, 1.25);
  }};
  document.getElementById("zoom-out").onclick = () => {{
    const r = viewport.getBoundingClientRect();
    zoomAt(r.left + r.width / 2, r.top + r.height / 2, 0.8);
  }};
  document.getElementById("fit").onclick = fitToScreen;
  document.getElementById("reset").onclick = () => {{
    scale = 1; panX = 20; panY = 20; applyTransform();
  }};

  window.addEventListener("resize", fitToScreen);
  fitToScreen();
}})();
  </script>
</body>
</html>
"""
    path.write_text(doc, encoding="utf-8")


def write_overlay_outputs(
    stem: str,
    output_dir: Path,
    slabs: list[dict],
    extents: dict | None,
    *,
    title: str,
    totals: dict | None = None,
    excluded_wkt: str | None = None,
) -> dict[str, str]:
    svg_path = output_dir / f"{stem}_overlay.svg"
    html_path = output_dir / f"{stem}_overlay.html"
    content = build_svg_content(
        slabs,
        extents,
        title=title,
        totals=totals,
        excluded_wkt=excluded_wkt,
    )
    svg_path.write_text(content, encoding="utf-8")
    write_html_overlay_viewer(html_path, content, title=title)
    return {"svg": str(svg_path), "html": str(html_path)}
