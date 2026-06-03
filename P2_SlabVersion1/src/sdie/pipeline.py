from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from sdie.config import PipelineConfig
from sdie.detection.beam_frame import detect_beam_frame_slab
from sdie.detection.beam_grid import (
    count_orthogonal_frame_lines,
    detect_beam_grid_slabs,
)
from sdie.detection.region import detect_closed_regions
from sdie.geometry.segments import collect_segments
from sdie.ingestion.dxf_reader import load_drawing
from sdie.quantity.slab import compute_slab_quantity
from sdie.thickness.parser import (
    extract_default_thickness_mm,
    extract_thk_labels,
    nearest_thickness_mm,
)
from sdie.validation.overlay import write_svg_overlay


def run_pipeline(
    dxf_path: Path,
    output_dir: Path,
    config: PipelineConfig | None = None,
) -> dict:
    config = config or PipelineConfig()
    output_dir.mkdir(parents=True, exist_ok=True)

    doc, meta = load_drawing(dxf_path)
    msp = doc.modelspace()

    default_mm, note_text = extract_default_thickness_mm(
        msp, config.annotation_layers
    )
    if default_mm == 200 and config.default_thickness_mm != 200:
        default_mm = config.default_thickness_mm
    thk_labels = extract_thk_labels(msp, config.annotation_layers)

    area_factor = meta.area_to_m2_factor
    poly_layers = config.polygonize_layers or config.structural_layers
    detection_mode = config.detection_mode
    detection_notes: dict = {"mode": detection_mode}

    candidates = []
    frame_layers = config.structural_layers

    if detection_mode in ("auto", "beam_grid"):
        h_count, v_count = count_orthogonal_frame_lines(msp, frame_layers)
        detection_notes["frame_line_count"] = {
            "horizontal": h_count,
            "vertical": v_count,
        }
        try_grid = detection_mode == "beam_grid" or (
            h_count >= 80 and v_count >= 60
        )
        if try_grid:
            grid_candidates = detect_beam_grid_slabs(
                msp,
                frame_layers=frame_layers,
                annotation_layers=config.annotation_layers,
                area_to_m2_factor=area_factor,
                min_area_m2=config.min_slab_area_m2,
                min_horizontal_span_mm=config.grid_min_horizontal_span_mm,
                min_vertical_span_mm=config.grid_min_vertical_span_mm,
                axis_cluster_tol_mm=config.grid_axis_cluster_tol_mm,
                slab_face_expand_mm=config.grid_slab_face_expand_mm,
                void_label_radius_mm=config.grid_void_label_radius_mm,
                id_prefix="SLAB",
            )
            detection_notes["beam_grid_count"] = len(grid_candidates)
            detection_notes["beam_grid_total_area_m2"] = round(
                sum(c.area_m2 for c in grid_candidates), 3
            )
            if grid_candidates:
                candidates = grid_candidates
                detection_notes["selected"] = "beam_grid_bay"

    if not candidates and detection_mode in ("auto", "region"):
        segments = collect_segments(msp, poly_layers)
        region_candidates = detect_closed_regions(
            segments,
            cm2_to_m2=area_factor,
            min_area_m2=config.min_slab_area_m2,
            id_prefix="SLAB",
        )
        region_total = sum(c.area_m2 for c in region_candidates)
        detection_notes["region_polygon_count"] = len(region_candidates)
        detection_notes["region_total_area_m2"] = round(region_total, 3)

        use_beam_frame = detection_mode == "beam_frame" or (
            detection_mode == "auto"
            and (
                not region_candidates
                or region_total > 150.0
                or any(c.area_m2 > 120.0 for c in region_candidates)
            )
        )
        if not use_beam_frame:
            candidates = region_candidates
            detection_notes["selected"] = "region_polygonize"
        else:
            detection_notes["region_rejected"] = (
                "no closed regions, or areas too large (likely wrong layers)"
            )

    if not candidates:
        candidates = detect_beam_frame_slab(
            msp,
            frame_layers=frame_layers,
            annotation_layers=config.annotation_layers,
            area_to_m2_factor=area_factor,
            edge_expand_mm=config.slab_edge_expand_mm,
            id_prefix="SLAB",
        )
        detection_notes["selected"] = "beam_frame_bbox"

    slabs: list[dict] = []
    for cand in candidates:
        thk_mm, thk_src, thk_dist, thk_conf = nearest_thickness_mm(
            (cand.centroid_cm[0], cand.centroid_cm[1]),
            thk_labels,
            default_mm,
            config.thickness_label_radius_m,
        )
        qty = compute_slab_quantity(
            cand.area_m2,
            thk_mm,
            shuttering_equals_soffit=config.shuttering_equals_soffit,
        )
        slabs.append(
            {
                "slab_id": cand.slab_id,
                "strategy": cand.strategy,
                "area_m2": qty.area_m2,
                "thickness_mm": thk_mm,
                "thickness_source": thk_src,
                "thickness_label_distance_cm": round(thk_dist, 2),
                "thickness_confidence": thk_conf,
                "concrete_m3": qty.concrete_m3,
                "shuttering_m2": qty.shuttering_m2,
                "calculation_trace": qty.trace,
                "centroid_cm": cand.centroid_cm,
                "bounds_cm": cand.bounds_cm,
                "polygon_wkt": cand.polygon_wkt,
            }
        )

    totals = {
        "area_m2": round(sum(s["area_m2"] for s in slabs), 6),
        "concrete_m3": round(sum(s["concrete_m3"] for s in slabs), 6),
        "shuttering_m2": round(sum(s["shuttering_m2"] for s in slabs), 6),
        "slab_count": len(slabs),
    }

    result = {
        "engine": "SDIE",
        "version": "0.1.0",
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "source_dxf": str(dxf_path),
        "drawing_meta": asdict(meta),
        "config": {
            "structural_layers": list(config.structural_layers),
            "polygonize_layers": list(poly_layers),
            "annotation_layers": list(config.annotation_layers),
            "detection_mode": detection_mode,
            "coordinate_unit": meta.coordinate_unit,
            "area_to_m2_factor": meta.area_to_m2_factor,
            "min_slab_area_m2": config.min_slab_area_m2,
        },
        "detection_notes": detection_notes,
        "notes": {
            "default_thickness_mm": default_mm,
            "default_note_text": note_text,
            "local_thk_label_count": len(thk_labels),
        },
        "slabs": slabs,
        "totals": totals,
    }

    stem = dxf_path.stem
    json_path = output_dir / f"{stem}_results.json"
    svg_path = output_dir / f"{stem}_overlay.svg"
    summary_path = output_dir / f"{stem}_summary.txt"

    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_svg_overlay(
        svg_path, slabs, meta.extents, title=f"SDIE — {dxf_path.name}"
    )

    summary_lines = [
        f"SDIE Slab Estimation — {dxf_path.name}",
        f"Processed: {result['processed_at']}",
        f"Structural layers: {', '.join(config.structural_layers)}",
        f"Default thickness: {default_mm} mm",
        "",
        f"Slabs detected: {totals['slab_count']}",
        f"Total area:      {totals['area_m2']:.3f} m²",
        f"Total concrete:  {totals['concrete_m3']:.3f} m³",
        f"Total shuttering:{totals['shuttering_m2']:.3f} m²",
        "",
    ]
    for s in slabs:
        summary_lines.append(
            f"  {s['slab_id']}: {s['area_m2']:.3f} m², "
            f"{s['thickness_mm']} mm ({s['thickness_source']}), "
            f"{s['concrete_m3']:.3f} m³"
        )
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    result["output_files"] = {
        "json": str(json_path),
        "svg": str(svg_path),
        "summary": str(summary_path),
    }
    return result
