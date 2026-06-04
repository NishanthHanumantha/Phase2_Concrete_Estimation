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
from shapely.ops import unary_union

from sdie.detection.exclusions import (
    build_beam_footprint_overlay,
    build_exclusion_catalog,
)
from sdie.detection.floor_zone import resolve_floor_zone
from sdie.detection.slab_by_label import detect_label_merged_slabs
from sdie.detection.region import detect_closed_regions
from sdie.geometry.segments import collect_segments
from sdie.ingestion.dxf_reader import load_drawing
from sdie.quantity.slab import compute_slab_quantity
from sdie.thickness.parser import (
    extract_default_thickness_mm,
    extract_thk_labels,
    nearest_thickness_mm,
)
from sdie.validation.overlay import write_overlay_outputs


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
    exclusion_union_wkt: str | None = None

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
            floor_bounds_y = None
            floor_zone = None
            if config.auto_floor_zone:
                floor_zone = resolve_floor_zone(
                    msp,
                    label_layers=config.floor_label_layers,
                    frame_layers=frame_layers,
                    bounds_y=config.floor_bounds_y,
                    mode=config.floor_zone_mode,
                    cluster_gap_mm=config.floor_cluster_gap_mm,
                    cluster_margin_mm=config.floor_cluster_margin_mm,
                )
                floor_bounds_y = floor_zone.bounds_y
                detection_notes["floor_zone"] = {
                    "method": floor_zone.method,
                    "label_count": floor_zone.label_count,
                    "cluster_count": floor_zone.cluster_count,
                    "included_satellite_clusters": floor_zone.included_satellite_clusters,
                    "notes": floor_zone.notes,
                }
            if floor_bounds_y is not None:
                detection_notes["floor_bounds_y_mm"] = [
                    round(v, 1) for v in floor_bounds_y
                ]

            exclusions = None
            if config.apply_slab_exclusions:
                beam_ex_layers = ()
                if not config.exclude_beam_footprints_from_quantity:
                    beam_ex_layers = (
                        config.beam_layers_for_exclusion or frame_layers
                    )
                exclusions = build_exclusion_catalog(
                    msp,
                    bounds_y=floor_bounds_y,
                    beam_layers=beam_ex_layers,
                    column_layers=config.column_exclusion_layers,
                    wall_layers=config.wall_exclusion_layers,
                    hatch_void_layers=config.hatch_void_layers,
                    label_box_layers=config.label_box_exclusion_layers,
                    annotation_layers=config.annotation_layers,
                    wall_half_width_mm=config.wall_half_width_mm,
                    area_to_m2_factor=area_factor,
                    include_void_label_buffers=config.include_void_label_buffers,
                )
                detection_notes["exclusion_area_m2"] = exclusions.area_m2
                detection_notes["exclusion_parts"] = len(
                    exclusions.parts
                )
                overlay_geoms = []
                if exclusions.union is not None and not exclusions.union.is_empty:
                    overlay_geoms.append(exclusions.union)
                beam_vis = build_beam_footprint_overlay(
                    msp,
                    frame_layers,
                    bounds_y=floor_bounds_y,
                    annotation_layers=config.annotation_layers,
                )
                if beam_vis is not None and not beam_vis.is_empty:
                    overlay_geoms.append(beam_vis)
                if overlay_geoms:
                    exclusion_union_wkt = unary_union(overlay_geoms).wkt

            label_bounds_y = floor_bounds_y
            if floor_zone is not None:
                label_bounds_y = floor_zone.thk_filter_bounds_y

            thk_in_floor = [
                lb
                for lb in thk_labels
                if label_bounds_y is None
                or (
                    label_bounds_y[0] <= lb.xy_cm[1] <= label_bounds_y[1]
                )
            ]
            if label_bounds_y is not None and label_bounds_y != floor_bounds_y:
                detection_notes["label_bounds_y_mm"] = [
                    round(v, 1) for v in label_bounds_y
                ]
            detection_notes["thk_labels_in_floor"] = len(thk_in_floor)

            expand = config.grid_slab_face_expand_mm
            if expand is None:
                expand = 55.0

            grid_candidates = detect_beam_grid_slabs(
                msp,
                frame_layers=frame_layers,
                annotation_layers=config.annotation_layers,
                area_to_m2_factor=area_factor,
                min_area_m2=config.min_slab_area_m2,
                min_horizontal_span_mm=config.grid_min_horizontal_span_mm,
                min_vertical_span_mm=config.grid_min_vertical_span_mm,
                axis_cluster_tol_mm=config.grid_axis_cluster_tol_mm,
                slab_face_expand_mm=expand,
                void_label_radius_mm=config.grid_void_label_radius_mm,
                bounds_y=floor_bounds_y,
                exclusions=exclusions,
                apply_exclusions=config.apply_slab_exclusions,
                id_prefix="SLAB",
            )
            detection_notes["beam_grid_cell_count"] = len(grid_candidates)
            detection_notes["beam_grid_total_area_m2"] = round(
                sum(c.area_m2 for c in grid_candidates), 3
            )

            merge_min_labels = config.min_thk_labels_for_merge
            if thk_in_floor and len(thk_in_floor) < merge_min_labels:
                merge_min_labels = max(10, int(len(thk_in_floor) * 0.5))

            label_merged: list = []
            if (
                config.merge_slabs_by_thk_labels
                and len(thk_in_floor) >= merge_min_labels
            ):
                label_merged = detect_label_merged_slabs(
                    msp,
                    frame_layers=frame_layers,
                    label_layers=config.floor_label_layers,
                    annotation_layers=config.annotation_layers,
                    area_to_m2_factor=area_factor,
                    min_area_m2=config.min_slab_area_m2,
                    bounds_y=label_bounds_y,
                    exclusions=exclusions,
                    slab_face_expand_mm=expand,
                    min_labels_for_strategy=config.min_thk_labels_for_merge,
                    id_prefix="SLAB",
                    grid_cells=grid_candidates,
                )
                detection_notes["label_merged_count"] = len(label_merged)
                detection_notes["label_merged_area_m2"] = round(
                    sum(c.area_m2 for c in label_merged), 3
                )

            geometric_selected = None
            if label_merged:
                geometric_selected = label_merged
                detection_notes["selected"] = "label_merged_bay"
            elif grid_candidates:
                geometric_selected = grid_candidates
                detection_notes["selected"] = "beam_grid_bay"

            if config.enable_deepseek_refinement and grid_candidates:
                from sdie.reasoning.slab_refinement import (
                    refine_slabs_with_deepseek,
                )

                llm_slabs, llm_notes = refine_slabs_with_deepseek(
                    msp,
                    drawing_name=dxf_path.name,
                    structural_layers=config.structural_layers,
                    annotation_layers=config.annotation_layers,
                    label_layers=config.floor_label_layers,
                    frame_layers=frame_layers,
                    grid_cells=grid_candidates,
                    merged_slabs=geometric_selected,
                    floor_bounds_y=floor_bounds_y,
                    frame_line_count=detection_notes.get(
                        "frame_line_count", {}
                    ),
                    exclusion_area_m2=detection_notes.get(
                        "exclusion_area_m2"
                    ),
                    geometric_notes={
                        k: detection_notes[k]
                        for k in (
                            "beam_grid_cell_count",
                            "beam_grid_total_area_m2",
                            "label_merged_count",
                            "label_merged_area_m2",
                            "thk_labels_in_floor",
                            "floor_zone",
                        )
                        if k in detection_notes
                    },
                    area_to_m2_factor=area_factor,
                    min_area_m2=config.min_slab_area_m2,
                    deepseek_model=config.deepseek_model,
                    deepseek_base_url=config.deepseek_base_url,
                    thk_labels_total=len(thk_labels),
                )
                detection_notes["llm_refinement"] = llm_notes
                ok_status = llm_notes.get("status") == "ok"
                if llm_slabs and ok_status:
                    candidates = llm_slabs
                    detection_notes["selected"] = "label_merged_bay_llm"
                else:
                    candidates = geometric_selected or []
                    if llm_notes.get("status") not in ("pending", "error", "no_merged_slabs"):
                        detection_notes["llm_fallback"] = llm_notes.get("status")
            else:
                candidates = geometric_selected or []

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
        if cand.thickness_mm is not None:
            thk_mm = cand.thickness_mm
            thk_src = "local_thk_label"
            thk_dist = 0.0
            thk_conf = 0.95
        else:
            thk_mm, thk_src, thk_dist, thk_conf = nearest_thickness_mm(
                (cand.centroid_cm[0], cand.centroid_cm[1]),
                thk_labels,
                default_mm,
                config.thickness_label_radius_m,
                max_label_distance_mm=config.thk_label_max_distance_mm,
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
    summary_path = output_dir / f"{stem}_summary.txt"

    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    overlay_files = write_overlay_outputs(
        stem,
        output_dir,
        slabs,
        meta.extents,
        title=f"SDIE — {dxf_path.name}",
        totals=totals,
        excluded_wkt=exclusion_union_wkt,
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
        "svg": overlay_files["svg"],
        "overlay_html": overlay_files["html"],
        "summary": str(summary_path),
    }
    return result
