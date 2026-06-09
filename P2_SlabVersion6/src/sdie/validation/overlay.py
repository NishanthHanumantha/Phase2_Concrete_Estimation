from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from shapely import wkt
from shapely.geometry.base import BaseGeometry

from sdie.classification.types import ClassifiedComponent, ComponentType

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

COMPONENT_COLORS: dict[str, str] = {
    ComponentType.BEAM.value: "#FF9800",
    ComponentType.COLUMN.value: "#E91E63",
    ComponentType.STRUCTURAL_WALL.value: "#9C27B0",
    ComponentType.SHEAR_WALL.value: "#673AB7",
    ComponentType.LIFT_CORE.value: "#00BCD4",
    ComponentType.STAIR_CORE.value: "#009688",
    ComponentType.SHAFT.value: "#795548",
    ComponentType.OPENING.value: "#78909C",
    ComponentType.SLAB.value: "#4CAF50",
    ComponentType.UNKNOWN.value: "#757575",
}

SLAB_STATUS_STYLES: dict[str, dict[str, str | float]] = {
    "matched": {"fill": "#2E7D32", "stroke": "#A5D6A7", "opacity": 0.55},
    "weak": {"fill": "#F9A825", "stroke": "#FFE082", "opacity": 0.55},
    "extra": {"fill": "#AD1457", "stroke": "#F48FB1", "opacity": 0.5},
    "none": {"fill": DEFAULT_FILL, "stroke": "#B0BEC5", "opacity": 0.45},
}

EXCLUSION_TYPES = frozenset(
    t.value
    for t in ComponentType.non_slab_types()
    if t != ComponentType.BEAM
)


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


def _slab_style(slab: dict) -> dict[str, str | float]:
    status = slab.get("gt_status")
    if status in SLAB_STATUS_STYLES:
        return SLAB_STATUS_STYLES[status]
    thk = slab.get("thickness_mm")
    if isinstance(thk, int) and thk in THICKNESS_COLORS:
        color = THICKNESS_COLORS[thk]
        return {"fill": color, "stroke": color, "opacity": 0.45}
    return SLAB_STATUS_STYLES["none"]


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
    extra_attrs: str = "",
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
            f'stroke="{stroke}" stroke-width="{stroke_width}"{extra_attrs}/>'
        )


def _iter_geoms(geom: BaseGeometry) -> list[BaseGeometry]:
    if geom.is_empty:
        return []
    if geom.geom_type in ("Polygon", "LineString", "Point"):
        return [geom]
    if hasattr(geom, "geoms"):
        out: list[BaseGeometry] = []
        for g in geom.geoms:
            out.extend(_iter_geoms(g))
        return out
    return []


def _append_linestring(
    parts: list[str],
    geom,
    tx,
    ty,
    *,
    stroke: str,
    stroke_width: float,
    opacity: float = 1.0,
    dash: str | None = None,
    extra_attrs: str = "",
) -> None:
    for g in _iter_geoms(geom):
        if g.geom_type != "LineString":
            continue
        coords = " ".join(f"{tx(x):.2f},{ty(y):.2f}" for x, y in g.coords)
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        parts.append(
            f'<polyline points="{coords}" fill="none" stroke="{stroke}" '
            f'stroke-width="{stroke_width}" stroke-opacity="{opacity}"{dash_attr}{extra_attrs}/>'
        )


def _append_classified_geom(
    parts: list[str],
    geom_wkt: str | None,
    centroid_mm: tuple[float, float] | None,
    tx,
    ty,
    *,
    stroke: str,
    stroke_width: float,
    fill: str | None = None,
    fill_opacity: float = 0.2,
    dash: str | None = None,
    extra_attrs: str = "",
) -> None:
    if geom_wkt:
        try:
            geom = wkt.loads(geom_wkt)
        except Exception:
            geom = None
    elif centroid_mm:
        from shapely.geometry import Point

        geom = Point(centroid_mm)
    else:
        return

    if geom is None or geom.is_empty:
        return

    if geom.geom_type == "Point":
        cx, cy = tx(geom.x), ty(geom.y)
        parts.append(
            f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="4" fill="{stroke}" '
            f'fill-opacity="0.8"{extra_attrs}/>'
        )
        return

    if geom.geom_type == "LineString" or (
        hasattr(geom, "geoms") and all(g.geom_type == "LineString" for g in geom.geoms)
    ):
        _append_linestring(
            parts,
            geom,
            tx,
            ty,
            stroke=stroke,
            stroke_width=stroke_width,
            dash=dash,
            extra_attrs=extra_attrs,
        )
        return

    _append_polygon_parts(
        parts,
        geom,
        tx,
        ty,
        fill=fill or stroke,
        fill_opacity=fill_opacity,
        stroke=stroke,
        stroke_width=stroke_width,
        extra_attrs=extra_attrs,
    )


def _classified_overlay_items(
    classified: list[ClassifiedComponent],
) -> list[dict[str, Any]]:
    return [
        {
            "id": c.component_id,
            "type": c.component_type.value,
            "layer": c.layer,
            "entity_type": c.entity_type,
            "geometry_wkt": c.geometry_wkt,
            "centroid_mm": list(c.centroid_mm) if c.centroid_mm else None,
            "confidence": round(c.confidence, 1),
            "annotation_text": c.annotation_text,
        }
        for c in classified
    ]


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

    def tx(x: float) -> float:
        return (x - xmin) / w * svg_w if w else 0.0

    def ty(y: float) -> float:
        return svg_h - (y - ymin) / h * svg_h if h else 0.0

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" '
        f'viewBox="0 0 {svg_w} {svg_h}">',
        '<rect width="100%" height="100%" fill="#121212"/>',
    ]

    if excluded_wkt:
        ex_geom = wkt.loads(excluded_wkt)
        _append_polygon_parts(
            parts,
            ex_geom,
            tx,
            ty,
            fill="#FF9800",
            fill_opacity=0.12,
            stroke="#FFB74D",
            stroke_width=0.6,
        )

    for i, slab in enumerate(slabs):
        poly = polys[i]
        style = _slab_style(slab)
        coords = " ".join(f"{tx(x):.2f},{ty(y):.2f}" for x, y in poly.exterior.coords)
        dash = ' stroke-dasharray="6 3"' if slab.get("gt_status") == "extra" else ""
        parts.append(
            f'<polygon class="slab-poly" data-slab-id="{html.escape(slab["slab_id"])}" '
            f'points="{coords}" fill="{style["fill"]}" fill-opacity="{style["opacity"]}" '
            f'stroke="{style["stroke"]}" stroke-width="{stroke}"{dash}/>'
        )
        if show_labels and slab["area_m2"] >= min_label_area:
            cx, cy = slab["centroid_cm"]
            label = f'{slab["slab_id"]}'
            if slab.get("gt_id"):
                label = f'{slab["gt_id"]}'
            parts.append(
                f'<text x="{tx(cx):.1f}" y="{ty(cy):.1f}" fill="#fff" font-size="9" '
                f'text-anchor="middle" dominant-baseline="middle" '
                f'font-family="Segoe UI, sans-serif" paint-order="stroke" '
                f'stroke="#000" stroke-width="2" pointer-events="none">'
                f'{html.escape(label)}</text>'
            )

    parts.append("</svg>")
    return "\n".join(parts)


def _beams_overlay_items(beams: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "beam_id": b.get("beam_id"),
            "component_id": b.get("component_id"),
            "layer": b.get("layer"),
            "length_m": b.get("length_m"),
            "width_mm": b.get("width_mm"),
            "depth_mm": b.get("depth_mm"),
            "concrete_m3": b.get("concrete_m3"),
            "confidence": b.get("confidence"),
            "geometry_wkt": b.get("geometry_wkt"),
            "centroid_mm": b.get("centroid_mm"),
        }
        for b in beams
    ]


def build_diagnostic_svg(
    slabs: list[dict],
    extents: dict | None,
    *,
    classified: list[ClassifiedComponent] | None = None,
    excluded_wkt: str | None = None,
    beams: list[dict[str, Any]] | None = None,
    crop_to_slabs: bool = True,
) -> tuple[str, int, int, float, float, float, float]:
    """Build layered SVG for the diagnostic viewer. Returns svg + view metadata."""
    if not slabs:
        empty = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 80">'
            '<text x="10" y="40" fill="#ccc" font-size="14">No slabs detected</text></svg>'
        )
        return empty, 400, 80, 0, 0, 400, 80

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

    def tx(x: float) -> float:
        return (x - xmin) / w * svg_w if w else 0.0

    def ty(y: float) -> float:
        return svg_h - (y - ymin) / h * svg_h if h else 0.0

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" '
        f'viewBox="0 0 {svg_w} {svg_h}" id="overlay-svg">',
        '<rect width="100%" height="100%" fill="#1a1a1a"/>',
        '<g id="layer-beams" data-layer="beams">',
    ]

    if excluded_wkt:
        ex_geom = wkt.loads(excluded_wkt)
        _append_polygon_parts(
            parts,
            ex_geom,
            tx,
            ty,
            fill="#FF9800",
            fill_opacity=0.1,
            stroke="#FFB74D",
            stroke_width=0.5,
        )
    parts.append("</g>")

    if beams:
        parts.append('<g id="layer-beam-quantities" data-layer="beam-quantities">')
        for beam in beams:
            beam_id = html.escape(str(beam.get("beam_id", "")))
            comp_id = html.escape(str(beam.get("component_id", "")))
            attrs = (
                f' class="beam-qty" data-beam-id="{beam_id}" '
                f'data-component-id="{comp_id}"'
            )
            centroid = beam.get("centroid_mm")
            _append_classified_geom(
                parts,
                beam.get("geometry_wkt"),
                tuple(centroid) if centroid else None,
                tx,
                ty,
                stroke="#1E88E5",
                stroke_width=2.2,
                extra_attrs=attrs,
            )
            if centroid and len(centroid) >= 2:
                parts.append(
                    f'<text x="{tx(centroid[0]):.1f}" y="{ty(centroid[1]):.1f}" '
                    f'fill="#BBDEFB" font-size="8" text-anchor="middle" '
                    f'dominant-baseline="middle" font-family="Segoe UI, sans-serif" '
                    f'paint-order="stroke" stroke="#0D47A1" stroke-width="2" '
                    f'pointer-events="none">{beam_id}</text>'
                )
        parts.append("</g>")

    if classified:
        by_type: dict[str, list[ClassifiedComponent]] = {}
        for comp in classified:
            by_type.setdefault(comp.component_type.value, []).append(comp)

        parts.append('<g id="layer-exclusions" data-layer="exclusions">')
        for comp in classified:
            if comp.component_type.value not in EXCLUSION_TYPES:
                continue
            color = COMPONENT_COLORS.get(comp.component_type.value, "#B71C1C")
            _append_classified_geom(
                parts,
                comp.geometry_wkt,
                comp.centroid_mm,
                tx,
                ty,
                stroke=color,
                stroke_width=1.2,
                fill=color,
                fill_opacity=0.35,
            )
        parts.append("</g>")

        for comp_type, items in sorted(by_type.items()):
            layer_id = comp_type.lower().replace(" ", "-")
            parts.append(
                f'<g id="layer-{layer_id}" data-layer="classified" '
                f'data-component-type="{html.escape(comp_type)}" style="display:none">'
            )
            color = COMPONENT_COLORS.get(comp_type, "#888")
            for comp in items:
                low_conf = comp.confidence < 45
                dash = "4 3" if low_conf else None
                attrs = (
                    f' data-comp-id="{html.escape(comp.component_id)}" '
                    f'data-comp-type="{html.escape(comp_type)}" '
                    f'data-layer-name="{html.escape(comp.layer)}" '
                    f'data-confidence="{comp.confidence:.1f}"'
                )
                sw = 0.8 if comp_type == ComponentType.BEAM.value else 1.0
                _append_classified_geom(
                    parts,
                    comp.geometry_wkt,
                    comp.centroid_mm,
                    tx,
                    ty,
                    stroke=color,
                    stroke_width=sw,
                    fill=color,
                    fill_opacity=0.15 if comp_type != ComponentType.BEAM.value else 0.0,
                    dash=dash,
                    extra_attrs=attrs,
                )
            parts.append("</g>")

    parts.append('<g id="layer-slabs" data-layer="slabs">')
    for slab in slabs:
        poly = wkt.loads(slab["polygon_wkt"])
        style = _slab_style(slab)
        coords = " ".join(f"{tx(x):.2f},{ty(y):.2f}" for x, y in poly.exterior.coords)
        dash = ' stroke-dasharray="8 4"' if slab.get("gt_status") == "extra" else ""
        parts.append(
            f'<polygon class="slab-poly" data-slab-id="{html.escape(slab["slab_id"])}" '
            f'points="{coords}" fill="{style["fill"]}" fill-opacity="{style["opacity"]}" '
            f'stroke="{style["stroke"]}" stroke-width="{stroke}"{dash}/>'
        )
        if show_labels and slab["area_m2"] >= min_label_area:
            cx, cy = slab["centroid_cm"]
            label = slab.get("gt_id") or slab["slab_id"]
            parts.append(
                f'<text x="{tx(cx):.1f}" y="{ty(cy):.1f}" fill="#fff" font-size="9" '
                f'text-anchor="middle" dominant-baseline="middle" '
                f'font-family="Segoe UI, sans-serif" paint-order="stroke" '
                f'stroke="#000" stroke-width="2" pointer-events="none">'
                f'{html.escape(str(label))}</text>'
            )
    parts.append("</g>")
    parts.append("</svg>")
    return "\n".join(parts), svg_w, svg_h, xmin, ymin, xmax, ymax


def write_diagnostic_overlay_html(
    path: Path,
    *,
    title: str,
    svg_content: str,
    slabs: list[dict],
    classified_items: list[dict[str, Any]],
    gt_context: dict[str, Any] | None,
    component_type_counts: dict[str, int],
    totals: dict | None,
    beams: list[dict[str, Any]] | None = None,
    view_meta: tuple[int, int, float, float, float, float],
) -> None:
    """Self-contained diagnostic HTML with layers, GT summary, and slab inspection."""
    escaped_title = html.escape(title)
    slabs_json = json.dumps(slabs, ensure_ascii=False)
    classified_json = json.dumps(classified_items, ensure_ascii=False)
    gt_json = json.dumps(gt_context or {}, ensure_ascii=False)
    counts_json = json.dumps(component_type_counts, ensure_ascii=False)
    totals_json = json.dumps(totals or {}, ensure_ascii=False)
    beams_json = json.dumps(beams or [], ensure_ascii=False)
    svg_w, svg_h, xmin, ymin, xmax, ymax = view_meta

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{escaped_title}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; }}
    html, body {{ height: 100%; overflow: hidden; background: #111; color: #e8e8e8;
      font-family: "Segoe UI", system-ui, sans-serif; }}
    #app {{ display: grid; grid-template-columns: 300px 1fr; grid-template-rows: 48px 1fr; height: 100%; }}
    #toolbar {{
      grid-column: 1 / -1; display: flex; align-items: center; gap: 10px; padding: 8px 14px;
      background: #1c1c1c; border-bottom: 1px solid #333;
    }}
    #toolbar button {{
      background: #2d2d2d; color: #eee; border: 1px solid #444; border-radius: 5px;
      padding: 5px 12px; cursor: pointer; font-size: 12px;
    }}
    #toolbar button:hover {{ background: #3a3a3a; }}
    #toolbar .title {{ font-weight: 600; font-size: 14px; margin-right: 8px; }}
    #toolbar .hint {{ margin-left: auto; color: #888; font-size: 11px; }}
    #sidebar {{
      overflow-y: auto; background: #161616; border-right: 1px solid #2a2a2a; padding: 12px;
      font-size: 12px;
    }}
    #sidebar h3 {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em;
      color: #888; margin: 14px 0 8px; }}
    #sidebar h3:first-child {{ margin-top: 0; }}
    .layer-row {{ display: flex; align-items: center; gap: 8px; margin: 4px 0; }}
    .layer-row label {{ cursor: pointer; flex: 1; }}
    .swatch {{ width: 12px; height: 12px; border-radius: 2px; flex-shrink: 0; }}
    .stat-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 8px; }}
    .stat {{ background: #222; border-radius: 6px; padding: 8px; }}
    .stat .n {{ font-size: 18px; font-weight: 700; }}
    .stat .l {{ color: #999; font-size: 10px; }}
    .stat.matched .n {{ color: #66bb6a; }}
    .stat.weak .n {{ color: #ffca28; }}
    .stat.missed .n {{ color: #ef5350; }}
    .stat.extra .n {{ color: #ec407a; }}
    #slab-list, #beam-list, #issue-list {{ max-height: 160px; overflow-y: auto; }}
    .list-item.beam {{ border-left-color: #1E88E5; }}
    .beam-qty {{ cursor: pointer; }}
    .beam-qty:hover {{ stroke-width: 3.5; filter: brightness(1.2); }}
    .list-item {{
      padding: 6px 8px; margin: 3px 0; border-radius: 5px; background: #222; cursor: pointer;
      border-left: 3px solid #444;
    }}
    .list-item:hover {{ background: #2a2a2a; }}
    .list-item.matched {{ border-left-color: #66bb6a; }}
    .list-item.weak {{ border-left-color: #ffca28; }}
    .list-item.extra {{ border-left-color: #ec407a; }}
    .list-item.missed {{ border-left-color: #ef5350; }}
    #detail-panel {{
      background: #1e1e1e; border-radius: 6px; padding: 10px; margin-top: 8px; min-height: 80px;
      font-size: 11px; line-height: 1.5;
    }}
    #detail-panel .empty {{ color: #666; }}
    #viewport {{ position: relative; overflow: hidden; cursor: grab; background: #0d0d0d; }}
    #viewport.dragging {{ cursor: grabbing; }}
    #stage {{ transform-origin: 0 0; display: inline-block; }}
    #stage svg {{ display: block; max-width: none; }}
    .slab-poly {{ cursor: pointer; }}
    .slab-poly:hover {{ stroke-width: 2.5; filter: brightness(1.15); }}
    .filter-row {{ display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 6px; }}
    .filter-row button {{
      background: #2a2a2a; border: 1px solid #444; color: #ccc; border-radius: 4px;
      padding: 3px 8px; font-size: 10px; cursor: pointer;
    }}
    .filter-row button.active {{ background: #3949ab; border-color: #5c6bc0; color: #fff; }}
  </style>
</head>
<body>
  <div id="app">
    <div id="toolbar">
      <span class="title">{escaped_title}</span>
      <button type="button" id="zoom-in">Zoom +</button>
      <button type="button" id="zoom-out">Zoom −</button>
      <button type="button" id="fit">Fit</button>
      <button type="button" id="reset">100%</button>
      <span class="hint">Scroll zoom · Drag pan · Click slab or component</span>
    </div>
    <aside id="sidebar">
      <h3>Detection summary</h3>
      <div id="summary-stats"></div>
      <h3>Layers</h3>
      <div class="layer-row">
        <span class="swatch" style="background:#2E7D32"></span>
        <label><input type="checkbox" id="toggle-slabs" checked/> Slab bays (GT-colored)</label>
      </div>
      <div class="layer-row">
        <span class="swatch" style="background:#FFB74D"></span>
        <label><input type="checkbox" id="toggle-beams" checked/> Beam grid (footprint)</label>
      </div>
      <div class="layer-row">
        <span class="swatch" style="background:#1E88E5"></span>
        <label><input type="checkbox" id="toggle-beam-qty" checked/> Quantified beams (BEAM-xxx)</label>
      </div>
      <div class="layer-row">
        <span class="swatch" style="background:#E91E63"></span>
        <label><input type="checkbox" id="toggle-exclusions" checked/> Exclusions (cols/cores)</label>
      </div>
      <div class="layer-row">
        <span class="swatch" style="background:#FF9800"></span>
        <label><input type="checkbox" id="toggle-classified"/> Classified entities (by type)</label>
      </div>
      <div id="classified-toggles"></div>
      <h3>GT match legend</h3>
      <div class="layer-row"><span class="swatch" style="background:#2E7D32"></span><span>Matched (≤5% area)</span></div>
      <div class="layer-row"><span class="swatch" style="background:#F9A825"></span><span>Weak match (5–20%)</span></div>
      <div class="layer-row"><span class="swatch" style="background:#AD1457"></span><span>Extra model slab</span></div>
      <div class="layer-row"><span class="swatch" style="background:#ef5350"></span><span>Missed GT (listed only)</span></div>
      <h3>Inspect</h3>
      <div class="filter-row" id="slab-filters">
        <button type="button" data-filter="all" class="active">All</button>
        <button type="button" data-filter="matched">Matched</button>
        <button type="button" data-filter="weak">Weak</button>
        <button type="button" data-filter="extra">Extra</button>
      </div>
      <div id="slab-list"></div>
      <h3>Beams (Excel)</h3>
      <div id="beam-list"></div>
      <h3>Issues</h3>
      <div id="issue-list"></div>
      <div id="detail-panel"><div class="empty">Click a slab, beam, or classified entity for details.</div></div>
    </aside>
    <div id="viewport">
      <div id="stage">{svg_content}</div>
    </div>
  </div>
  <script>
(function () {{
  const SLABS = {slabs_json};
  const BEAMS = {beams_json};
  const CLASSIFIED = {classified_json};
  const GT = {gt_json};
  const COUNTS = {counts_json};
  const TOTALS = {totals_json};
  const VIEW = {{ svgW: {svg_w}, svgH: {svg_h}, xmin: {xmin}, ymin: {ymin}, xmax: {xmax}, ymax: {ymax} }};

  const viewport = document.getElementById("viewport");
  const stage = document.getElementById("stage");
  const svg = stage.querySelector("svg");
  const detail = document.getElementById("detail-panel");

  let scale = 1, panX = 0, panY = 0, dragging = false, lastX = 0, lastY = 0;
  let activeFilter = "all";

  function applyTransform() {{
    stage.style.transform = `translate(${{panX}}px, ${{panY}}px) scale(${{scale}})`;
  }}

  function fitToScreen() {{
    if (!svg) return;
    const vb = svg.viewBox.baseVal;
    const sw = vb.width || VIEW.svgW;
    const sh = vb.height || VIEW.svgH;
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

  function focusSlab(slabId) {{
    const slab = SLABS.find(s => s.slab_id === slabId);
    if (!slab || !svg) return;
    const cx = slab.centroid_cm[0];
    const cy = slab.centroid_cm[1];
    const w = VIEW.xmax - VIEW.xmin;
    const h = VIEW.ymax - VIEW.ymin;
    const sx = (cx - VIEW.xmin) / w * VIEW.svgW;
    const sy = VIEW.svgH - (cy - VIEW.ymin) / h * VIEW.svgH;
    const vw = viewport.clientWidth;
    const vh = viewport.clientHeight;
    scale = Math.min(vw, vh) * 0.35 / Math.max(VIEW.svgW, VIEW.svgH) * 4;
    panX = vw / 2 - sx * scale;
    panY = vh / 2 - sy * scale;
    applyTransform();
    showSlabDetail(slabId);
    document.querySelectorAll(".slab-poly").forEach(el => {{
      el.style.filter = el.dataset.slabId === slabId ? "brightness(1.4)" : "";
    }});
  }}

  function showSlabDetail(slabId) {{
    const s = SLABS.find(x => x.slab_id === slabId);
    if (!s) return;
    const lines = [
      `<strong>${{s.slab_id}}</strong>`,
      `Area: ${{s.area_m2?.toFixed(3)}} m² · Thk: ${{s.thickness_mm}} mm (${{s.thickness_source || "—"}})`,
      `Concrete: ${{s.concrete_m3?.toFixed(3)}} m³ · Strategy: ${{s.strategy || "—"}}`,
    ];
    if (s.gt_id) {{
      lines.push(`GT: <strong>${{s.gt_id}}</strong> (expected ${{s.gt_expected_area_m2?.toFixed(3)}} m², err ${{s.gt_area_err_pct}}%)`);
      lines.push(`Status: <strong>${{s.gt_status}}</strong>`);
    }} else if (s.gt_status === "extra") {{
      lines.push(`Status: <strong>extra</strong> — no matching GT slab`);
    }}
    detail.innerHTML = lines.join("<br/>");
  }}

  function focusBeam(beamId) {{
    const beam = BEAMS.find(b => b.beam_id === beamId);
    if (!beam || !svg) return;
    const c = beam.centroid_mm;
    if (!c || c.length < 2) return;
    const w = VIEW.xmax - VIEW.xmin;
    const h = VIEW.ymax - VIEW.ymin;
    const sx = (c[0] - VIEW.xmin) / w * VIEW.svgW;
    const sy = VIEW.svgH - (c[1] - VIEW.ymin) / h * VIEW.svgH;
    const vw = viewport.clientWidth;
    const vh = viewport.clientHeight;
    scale = Math.min(vw, vh) * 0.35 / Math.max(VIEW.svgW, VIEW.svgH) * 4;
    panX = vw / 2 - sx * scale;
    panY = vh / 2 - sy * scale;
    applyTransform();
    showBeamDetail(beamId);
    document.querySelectorAll(".beam-qty").forEach(el => {{
      el.style.filter = el.dataset.beamId === beamId ? "brightness(1.5)" : "";
    }});
    document.querySelectorAll(".slab-poly").forEach(el => {{ el.style.filter = ""; }});
  }}

  function showBeamDetail(beamId) {{
    const b = BEAMS.find(x => x.beam_id === beamId);
    if (!b) return;
    detail.innerHTML = [
      `<strong>${{b.beam_id}}</strong>`,
      `Layer: ${{b.layer || "—"}} · L=${{b.length_m?.toFixed(2)}} m`,
      `Section: ${{b.width_mm}}×${{b.depth_mm}} mm · Concrete: ${{b.concrete_m3?.toFixed(3)}} m³`,
      `Confidence: ${{b.confidence?.toFixed?.(1) ?? b.confidence}}%`,
      b.component_id ? `Entity: ${{b.component_id}}` : "",
    ].filter(Boolean).join("<br/>");
  }}

  function showCompDetail(el) {{
    detail.innerHTML = [
      `<strong>${{el.dataset.compId}}</strong>`,
      `Type: ${{el.dataset.compType}} · Layer: ${{el.dataset.layerName}}`,
      `Confidence: ${{el.dataset.confidence}}%`,
      el.dataset.compType !== "Beam" ? "(dashed = low confidence &lt;45%)" : "",
    ].filter(Boolean).join("<br/>");
  }}

  function renderSummary() {{
    const el = document.getElementById("summary-stats");
    const gt = GT.summary || {{}};
    const hasGt = gt.gt_count > 0;
    el.innerHTML = `
      <div class="stat-grid">
        <div class="stat"><div class="n">${{TOTALS.slab_count || SLABS.length}}</div><div class="l">Slabs</div></div>
        <div class="stat"><div class="n">${{TOTALS.beam_count || BEAMS.length}}</div><div class="l">Beams</div></div>
        <div class="stat"><div class="n">${{(TOTALS.area_m2 || 0).toFixed(0)}}</div><div class="l">Slab m²</div></div>
        <div class="stat"><div class="n">${{(TOTALS.concrete_m3 || 0).toFixed(0)}}</div><div class="l">Total m³</div></div>
        ${{hasGt ? `
        <div class="stat matched"><div class="n">${{gt.matched_count || 0}}</div><div class="l">GT matched</div></div>
        <div class="stat weak"><div class="n">${{gt.weak_count || 0}}</div><div class="l">Weak</div></div>
        <div class="stat missed"><div class="n">${{gt.missed_count || 0}}</div><div class="l">Missed GT</div></div>
        <div class="stat extra"><div class="n">${{gt.extra_count || 0}}</div><div class="l">Extra</div></div>` : ""}}
      </div>`;
  }}

  function renderBeamList() {{
    const list = document.getElementById("beam-list");
    if (!BEAMS.length) {{
      list.innerHTML = '<div class="empty" style="padding:6px">No beams quantified.</div>';
      return;
    }}
    const items = [...BEAMS].sort((a, b) => a.beam_id.localeCompare(b.beam_id));
    list.innerHTML = items.map(b => `
      <div class="list-item beam" data-beam-id="${{b.beam_id}}">
        ${{b.beam_id}} · L=${{b.length_m?.toFixed(1)}} m · ${{b.concrete_m3?.toFixed(2)}} m³
      </div>`).join("");
    list.querySelectorAll(".list-item").forEach(row => {{
      row.onclick = () => focusBeam(row.dataset.beamId);
    }});
  }}

  function renderSlabList() {{
    const list = document.getElementById("slab-list");
    const items = SLABS.filter(s => activeFilter === "all" || s.gt_status === activeFilter)
      .sort((a, b) => (a.gt_status || "").localeCompare(b.gt_status || "") || a.slab_id.localeCompare(b.slab_id));
    list.innerHTML = items.map(s => `
      <div class="list-item ${{s.gt_status || ""}}" data-slab-id="${{s.slab_id}}">
        ${{s.gt_id ? s.gt_id + " → " : ""}}${{s.slab_id}} · ${{s.area_m2?.toFixed(2)}} m²
      </div>`).join("");
    list.querySelectorAll(".list-item").forEach(row => {{
      row.onclick = () => focusSlab(row.dataset.slabId);
    }});
  }}

  function renderIssues() {{
    const list = document.getElementById("issue-list");
    const parts = [];
    (GT.missed || []).forEach(m => {{
      parts.push(`<div class="list-item missed">Missed ${{m.gt_id}}: ${{m.expected_area_m2?.toFixed(2)}} m²</div>`);
    }});
    (GT.weak || []).slice(0, 12).forEach(w => {{
      parts.push(`<div class="list-item weak" data-slab-id="${{w.slab_id}}">${{w.gt_id}} → ${{w.slab_id}} (${{w.err_pct}}%)</div>`);
    }});
    (GT.extra || []).slice(0, 12).forEach(e => {{
      parts.push(`<div class="list-item extra" data-slab-id="${{e.slab_id}}">${{e.slab_id}}: ${{e.area_m2?.toFixed(2)}} m²</div>`);
    }});
    list.innerHTML = parts.join("") || '<div class="empty" style="padding:6px">No GT issues loaded.</div>';
    list.querySelectorAll("[data-slab-id]").forEach(row => {{
      row.onclick = () => focusSlab(row.dataset.slabId);
    }});
  }}

  function renderClassifiedToggles() {{
    const host = document.getElementById("classified-toggles");
    const types = Object.keys(COUNTS).sort();
    host.innerHTML = types.map(t => {{
      const id = "toggle-type-" + t.toLowerCase().replace(/ /g, "-");
      return `<div class="layer-row" style="margin-left:12px">
        <label><input type="checkbox" class="type-toggle" data-type="${{t}}" id="${{id}}"/> ${{t}} (${{COUNTS[t]}})</label>
      </div>`;
    }}).join("");
  }}

  function setLayerVisible(id, visible) {{
    const g = document.getElementById(id);
    if (g) g.style.display = visible ? "" : "none";
  }}

  document.getElementById("toggle-slabs").onchange = e => setLayerVisible("layer-slabs", e.target.checked);
  document.getElementById("toggle-beams").onchange = e => setLayerVisible("layer-beams", e.target.checked);
  document.getElementById("toggle-beam-qty").onchange = e => setLayerVisible("layer-beam-quantities", e.target.checked);
  document.getElementById("toggle-exclusions").onchange = e => setLayerVisible("layer-exclusions", e.target.checked);
  document.getElementById("toggle-classified").onchange = e => {{
    document.querySelectorAll('[data-layer="classified"]').forEach(g => {{
      g.style.display = e.target.checked ? "" : "none";
    }});
    document.querySelectorAll(".type-toggle").forEach(cb => {{ cb.checked = e.target.checked; }});
  }};

  function bindTypeToggles() {{
    document.querySelectorAll(".type-toggle").forEach(cb => {{
      cb.onchange = () => {{
        const layerId = "layer-" + cb.dataset.type.toLowerCase().replace(/ /g, "-");
        setLayerVisible(layerId, cb.checked);
        document.getElementById("toggle-classified").checked =
          [...document.querySelectorAll(".type-toggle")].some(x => x.checked);
      }};
    }});
  }}

  document.querySelectorAll("#slab-filters button").forEach(btn => {{
    btn.onclick = () => {{
      document.querySelectorAll("#slab-filters button").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      activeFilter = btn.dataset.filter;
      renderSlabList();
    }};
  }});

  if (svg) {{
    svg.querySelectorAll(".slab-poly").forEach(poly => {{
      poly.addEventListener("click", ev => {{
        ev.stopPropagation();
        focusSlab(poly.dataset.slabId);
      }});
    }});
    svg.querySelectorAll("[data-comp-id]").forEach(el => {{
      el.addEventListener("click", ev => {{
        ev.stopPropagation();
        showCompDetail(el);
      }});
    }});
    svg.querySelectorAll(".beam-qty").forEach(el => {{
      el.addEventListener("click", ev => {{
        ev.stopPropagation();
        focusBeam(el.dataset.beamId);
      }});
    }});
  }}

  viewport.addEventListener("wheel", e => {{
    e.preventDefault();
    zoomAt(e.clientX, e.clientY, e.deltaY < 0 ? 1.15 : 1 / 1.15);
  }}, {{ passive: false }});
  viewport.addEventListener("mousedown", e => {{
    if (e.button !== 0) return;
    dragging = true; lastX = e.clientX; lastY = e.clientY;
    viewport.classList.add("dragging");
  }});
  window.addEventListener("mousemove", e => {{
    if (!dragging) return;
    panX += e.clientX - lastX; panY += e.clientY - lastY;
    lastX = e.clientX; lastY = e.clientY;
    applyTransform();
  }});
  window.addEventListener("mouseup", () => {{
    dragging = false; viewport.classList.remove("dragging");
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
  document.getElementById("reset").onclick = () => {{ scale = 1; panX = 20; panY = 20; applyTransform(); }};
  window.addEventListener("resize", fitToScreen);

  renderSummary();
  renderSlabList();
  renderBeamList();
  renderIssues();
  renderClassifiedToggles();
  bindTypeToggles();
  fitToScreen();
}})();
  </script>
</body>
</html>
"""
    path.write_text(doc, encoding="utf-8")


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


def write_overlay_outputs(
    stem: str,
    output_dir: Path,
    slabs: list[dict],
    extents: dict | None,
    *,
    title: str,
    totals: dict | None = None,
    excluded_wkt: str | None = None,
    classified: list[ClassifiedComponent] | None = None,
    gt_context: dict[str, Any] | None = None,
    component_type_counts: dict[str, int] | None = None,
    beams: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    svg_path = output_dir / f"{stem}_overlay.svg"
    html_path = output_dir / f"{stem}_overlay.html"

    overlay_slabs = (gt_context or {}).get("slabs", slabs)
    svg_content = build_svg_content(
        overlay_slabs,
        extents,
        title=title,
        totals=totals,
        excluded_wkt=excluded_wkt,
    )
    svg_path.write_text(svg_content, encoding="utf-8")

    classified_items = _classified_overlay_items(classified or [])
    overlay_beams = beams or []
    diag_svg, svg_w, svg_h, xmin, ymin, xmax, ymax = build_diagnostic_svg(
        overlay_slabs,
        extents,
        classified=classified,
        excluded_wkt=excluded_wkt,
        beams=overlay_beams,
    )
    write_diagnostic_overlay_html(
        html_path,
        title=title,
        svg_content=diag_svg,
        slabs=overlay_slabs,
        classified_items=classified_items,
        gt_context=gt_context,
        component_type_counts=component_type_counts or {},
        totals=totals,
        beams=_beams_overlay_items(overlay_beams),
        view_meta=(svg_w, svg_h, xmin, ymin, xmax, ymax),
    )
    return {"svg": str(svg_path), "html": str(html_path)}
