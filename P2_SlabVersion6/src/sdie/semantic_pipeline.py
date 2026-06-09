from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from shapely.ops import unary_union

from sdie.atlas.store import load_atlas
from sdie.benchmark.metrics import compute_benchmark_report
from sdie.classification.classifier import classify_entities
from sdie.classification.rag_classifier import classify_entities_v4, classify_entities_v5
from sdie.classification.types import ComponentType
from sdie.inference.generic import is_generic_project
from sdie.rag.store import load_knowledge_base
from sdie.config import PipelineConfig
from sdie.detection.beam_frame import detect_beam_frame_slab
from sdie.detection.beam_grid import count_orthogonal_frame_lines
from sdie.detection.exclusions import build_beam_footprint_overlay
from sdie.detection.floor_zone import resolve_floor_zone
from sdie.detection.region import detect_closed_regions
from sdie.detection.slab_intelligence import detect_slabs_after_classification
from sdie.geometry.segments import collect_segments
from sdie.graph.engine import build_structural_graph
from sdie.ingestion.dxf_reader import load_drawing
from sdie.ingestion.entity_extractor import extract_drawing_entities
from sdie.ingestion.layer_discovery import apply_layer_plan_to_config, classification_entity_layers
from sdie.model.building import build_semantic_model
from sdie.quantity.beam import compute_beam_quantities_from_classification
from sdie.quantity.slab import compute_slab_quantity
from sdie.reasoning.component_classification import refine_ambiguous_components
from sdie.reasoning.slab_refinement import refine_slabs_with_deepseek
from sdie.thickness.parser import (
    extract_default_thickness_mm,
    extract_thk_labels,
    nearest_thickness_mm,
)
from sdie.util.progress import progress_for, set_active
from sdie.validation.excel_export import export_results_to_excel
from sdie.validation.gt_match import annotate_slabs_with_gt, find_gt_xlsx_for_stem, load_gt_xlsx
from sdie.validation.overlay import write_overlay_outputs
from sdie.validation.review_queue import write_review_queue


def _load_ground_truth(config: PipelineConfig, stem: str) -> dict | None:
    if not config.ground_truth_path:
        candidate = (
            Path(__file__).resolve().parents[2]
            / "data"
            / "ground_truth"
            / f"{stem}.json"
        )
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
        return None
    path = Path(config.ground_truth_path)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def run_semantic_pipeline(
    dxf_path: Path,
    output_dir: Path,
    config: PipelineConfig | None = None,
) -> dict:
    """
    SDIE v5/v4/v3 semantic pipeline.
    v5: rule baseline → graph topology → DeepSeek structural reasoning → exclusions → slabs.
    """
    config = config or PipelineConfig()
    output_dir.mkdir(parents=True, exist_ok=True)
    progress = progress_for(config.show_progress)
    set_active(progress)
    if config.use_v5_pipeline and config.use_v4_pipeline:
        pipeline_id = "v5.0_structural_reasoning"
    elif config.use_v4_pipeline:
        pipeline_id = "v4.0_rag_deepseek"
    else:
        pipeline_id = "semantic_v3.3"

    progress.stage("Loading DXF", 2, dxf_path.name)
    doc, meta = load_drawing(dxf_path)
    msp = doc.modelspace()
    progress.stage("Loaded DXF", 8, meta.coordinate_unit)

    progress.stage("Discovering layers", 10)
    layer_plan = apply_layer_plan_to_config(config, msp)

    default_mm, note_text = extract_default_thickness_mm(
        msp, config.annotation_layers
    )
    if default_mm == 200 and config.default_thickness_mm != 200:
        default_mm = config.default_thickness_mm
    thk_labels = extract_thk_labels(msp, config.annotation_layers)

    area_factor = meta.area_to_m2_factor
    poly_layers = config.polygonize_layers or config.structural_layers
    frame_layers = config.frame_layers or config.structural_layers
    detection_notes: dict = {
        "pipeline": pipeline_id,
        "mode": config.detection_mode,
        "layer_discovery": config.layer_discovery_notes,
        "layer_plan_method": layer_plan.method,
    }

    floor_zone = None
    floor_bounds_y = config.floor_bounds_y
    if config.auto_floor_zone:
        progress.stage("Resolving floor zone", 12)
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

    progress.stage("Loading atlas", 15)
    atlas = load_atlas(config.atlas_path, project_id=config.project_id)
    detection_notes["atlas_sample_count"] = len(atlas)
    detection_notes["atlas_project_id"] = config.project_id
    detection_notes["inference_mode"] = (
        "generic" if is_generic_project(config.project_id) else "project_scoped"
    )

    entity_layers = classification_entity_layers(config)
    detection_notes["classification_entity_layers"] = list(entity_layers)
    progress.stage("Extracting entities", 18, f"layers={len(entity_layers)}")
    entities = extract_drawing_entities(
        msp,
        layers=entity_layers,
        include_text_layers=config.annotation_layers + config.floor_label_layers,
        bounds_y=floor_bounds_y,
    )
    progress.stage("Extracted entities", 25, f"n={len(entities)}")
    if config.use_v4_pipeline and config.enable_rag_classification:
        progress.stage("Loading knowledge base", 28)
        kb = load_knowledge_base(config.knowledge_base_path)
        detection_notes["knowledge_base"] = {
            "layer_entries": len(kb.layer_knowledge),
            "annotation_entries": len(kb.annotation_knowledge),
            "pattern_entries": len(kb.pattern_knowledge),
            "estimator_mappings": len(kb.estimator_mappings),
        }
        if config.use_v5_pipeline:
            progress.stage(
                "Classifying entities (v5)",
                30,
                f"n={len(entities)} deepseek={'ambiguous only' if config.enable_deepseek_component_classification else 'off'}",
            )
            classified, cls_notes = classify_entities_v5(
                entities,
                kb=kb,
                atlas=atlas,
                project_id=config.project_id,
                msp=msp,
                meta=meta,
                drawing_name=dxf_path.name,
                annotation_layers=config.annotation_layers,
                enable_deepseek=config.enable_deepseek_component_classification,
                deepseek_model=config.deepseek_model,
                deepseek_base_url=config.deepseek_base_url,
                batch_size=config.deepseek_classification_batch_size,
                ambiguity_threshold=config.v5_review_threshold,
            )
        else:
            progress.stage(
                "Classifying entities (v4)",
                30,
                f"n={len(entities)} deepseek={'ambiguous only' if config.enable_deepseek_component_classification else 'off'}",
            )
            classified, cls_notes = classify_entities_v4(
                entities,
                kb=kb,
                atlas=atlas,
                project_id=config.project_id,
                enable_deepseek=config.enable_deepseek_component_classification,
                deepseek_model=config.deepseek_model,
                deepseek_base_url=config.deepseek_base_url,
                batch_size=config.deepseek_classification_batch_size,
                ambiguity_threshold=config.component_confidence_threshold,
            )
        detection_notes["classification"] = cls_notes
        ambiguous_n = cls_notes.get("ambiguous_count", 0)
        ds = cls_notes.get("deepseek", {})
        if isinstance(ds, dict):
            progress.stage(
                "Classified entities",
                55,
                f"n={len(classified)} ambiguous={ambiguous_n} deepseek_updated={ds.get('updated', 0)}",
            )
        else:
            progress.stage("Classified entities", 55, f"n={len(classified)}")
    else:
        progress.stage("Classifying entities (rules)", 30, f"n={len(entities)}")
        classified = classify_entities(
            entities, atlas=atlas, project_id=config.project_id
        )
        ambiguous = [
            c
            for c in classified
            if c.component_type == ComponentType.UNKNOWN
            or c.confidence < config.component_confidence_threshold
        ]
        if config.enable_deepseek_component_classification and ambiguous:
            updated, llm_notes = refine_ambiguous_components(
                ambiguous,
                drawing_name=dxf_path.name,
                deepseek_model=config.deepseek_model,
                deepseek_base_url=config.deepseek_base_url,
            )
            detection_notes["component_llm"] = llm_notes
            by_id = {c.component_id: c for c in classified}
            for u in updated:
                by_id[u.component_id] = u
            classified = list(by_id.values())
        progress.stage("Classified entities", 55, f"n={len(classified)}")

    detection_notes["entity_count"] = len(entities)
    detection_notes["classified_count"] = len(classified)
    type_counts: dict[str, int] = {}
    for c in classified:
        type_counts[c.component_type.value] = (
            type_counts.get(c.component_type.value, 0) + 1
        )
    detection_notes["component_type_counts"] = type_counts
    review_count = sum(1 for c in classified if c.review_required)
    detection_notes["review_required_count"] = review_count
    detection_notes["low_confidence_pct"] = round(
        100.0 * sum(1 for c in classified if c.confidence < config.v5_review_threshold)
        / max(1, len(classified)),
        2,
    )

    plan_x_bounds = None
    if config.dedupe_plan_copies_x and floor_zone is not None:
        from sdie.detection.beam_grid import resolve_plan_x_bounds_from_thk_labels

        thk_band_y = floor_zone.thk_filter_bounds_y or floor_bounds_y
        plan_x_bounds = resolve_plan_x_bounds_from_thk_labels(
            thk_labels,
            thk_band_y,
        )
        if plan_x_bounds is not None:
            span = plan_x_bounds[1] - plan_x_bounds[0]
            detection_notes["primary_plan_x_bounds_mm"] = [
                round(plan_x_bounds[0], 1),
                round(plan_x_bounds[1], 1),
            ]
            # Labels repeat on every plan copy — skip filter when span covers whole sheet.
            if span > 25000.0:
                plan_x_bounds = None
                detection_notes["primary_plan_x_bounds_skipped"] = "wide_sheet_multi_copy"

    beams: list[dict] = []
    beam_notes: dict = {}
    if config.enable_beam_quantities:
        progress.stage("Computing beam quantities", 56)
        beams, beam_notes = compute_beam_quantities_from_classification(
            classified,
            msp=msp,
            annotation_layers=config.annotation_layers,
            min_length_mm=config.min_beam_length_mm,
            min_confidence=config.min_beam_confidence,
            default_width_mm=config.default_beam_width_mm,
            default_depth_mm=config.default_beam_depth_mm,
            plan_x_bounds_mm=plan_x_bounds,
        )
        if config.dedupe_plan_copies_x and len(beams) > 1:
            from sdie.quantity.beam import dedupe_plan_copy_beams

            before = len(beams)
            beams, removed = dedupe_plan_copy_beams(beams)
            beam_notes["plan_copy_dedup_removed"] = removed
            beam_notes["plan_copy_dedup_before"] = before
            beam_notes["beam_count"] = len(beams)
            beam_notes["total_length_m"] = round(
                sum(b["length_m"] for b in beams), 3
            )
            beam_notes["concrete_m3"] = round(
                sum(b["concrete_m3"] for b in beams), 6
            )
            beam_notes["shuttering_m2"] = round(
                sum(b["shuttering_m2"] for b in beams), 6
            )
        detection_notes["beam_quantities"] = beam_notes
        progress.stage(
            "Beam quantities ready",
            57,
            f"n={len(beams)} concrete={beam_notes.get('concrete_m3', 0)} m³",
        )

    progress.stage("Building structural graph", 58)
    graph = build_structural_graph(classified)
    detection_notes["structural_graph"] = graph.to_dict()
    progress.stage(
        "Structural graph ready",
        60,
        f"nodes={graph.node_count} edges={graph.edge_count}",
    )

    candidates = []
    exclusion_union_wkt: str | None = None
    slab_intel_notes: dict = {}

    if config.detection_mode in ("auto", "beam_grid", "semantic"):
        h_count, v_count = count_orthogonal_frame_lines(msp, frame_layers)
        detection_notes["frame_line_count"] = {
            "horizontal": h_count,
            "vertical": v_count,
        }
        try_semantic = config.detection_mode in ("semantic", "beam_grid") or (
            config.detection_mode == "auto" and h_count >= 80 and v_count >= 60
        )
        if try_semantic:
            progress.stage("Detecting slabs", 62)
            candidates, slab_intel_notes = detect_slabs_after_classification(
                msp,
                config=config,
                classified=classified,
                graph=graph,
                floor_zone=floor_zone,
                thk_labels=thk_labels,
                area_to_m2_factor=area_factor,
                frame_layers=frame_layers,
            )
            detection_notes.update(slab_intel_notes)
            progress.stage(
                "Slabs detected",
                82,
                f"n={len(candidates)} area={slab_intel_notes.get('total_slab_area_m2', '—')} m²",
            )

            if config.enable_deepseek_refinement and candidates:
                from sdie.detection.beam_grid import detect_beam_grid_slabs

                grid_for_llm = detect_beam_grid_slabs(
                    msp,
                    frame_layers=frame_layers,
                    annotation_layers=config.annotation_layers,
                    area_to_m2_factor=area_factor,
                    min_area_m2=config.min_slab_area_m2,
                    bounds_y=floor_bounds_y,
                    id_prefix="SLAB",
                )
                llm_slabs, llm_notes = refine_slabs_with_deepseek(
                    msp,
                    drawing_name=dxf_path.name,
                    structural_layers=config.structural_layers,
                    annotation_layers=config.annotation_layers,
                    label_layers=config.floor_label_layers,
                    frame_layers=frame_layers,
                    grid_cells=grid_for_llm,
                    merged_slabs=candidates,
                    floor_bounds_y=floor_bounds_y,
                    frame_line_count=detection_notes.get("frame_line_count", {}),
                    exclusion_area_m2=detection_notes.get("total_exclusion_area_m2"),
                    geometric_notes=slab_intel_notes,
                    area_to_m2_factor=area_factor,
                    min_area_m2=config.min_slab_area_m2,
                    deepseek_model=config.deepseek_model,
                    deepseek_base_url=config.deepseek_base_url,
                    thk_labels_total=len(thk_labels),
                )
                detection_notes["slab_llm_refinement"] = llm_notes
                if llm_slabs and llm_notes.get("status") == "ok":
                    candidates = llm_slabs
                    detection_notes["selected"] = detection_notes.get(
                        "selected", "semantic"
                    ) + "_llm"

    if not candidates and config.detection_mode in ("auto", "region"):
        segments = collect_segments(msp, poly_layers)
        candidates = detect_closed_regions(
            segments,
            cm2_to_m2=area_factor,
            min_area_m2=config.min_slab_area_m2,
            id_prefix="SLAB",
        )
        detection_notes["selected"] = "region_polygonize"

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

    progress.stage("Computing quantities", 85, f"slabs={len(candidates)}")
    slabs: list[dict] = []
    for cand in candidates:
        cand_thk = getattr(cand, "thickness_mm", None)
        if cand_thk is not None:
            thk_mm = cand_thk
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

    slab_concrete = sum(s["concrete_m3"] for s in slabs)
    beam_concrete = sum(b["concrete_m3"] for b in beams)
    slab_shuttering = sum(s["shuttering_m2"] for s in slabs)
    beam_shuttering = sum(b["shuttering_m2"] for b in beams)
    totals = {
        "area_m2": round(sum(s["area_m2"] for s in slabs), 6),
        "concrete_m3": round(slab_concrete + beam_concrete, 6),
        "shuttering_m2": round(slab_shuttering + beam_shuttering, 6),
        "slab_count": len(slabs),
        "slab_concrete_m3": round(slab_concrete, 6),
        "beam_count": len(beams),
        "beam_concrete_m3": round(beam_concrete, 6),
        "beam_total_length_m": round(sum(b["length_m"] for b in beams), 3),
    }

    floor_zone_dict = detection_notes.get("floor_zone")
    if floor_bounds_y:
        floor_zone_dict = floor_zone_dict or {}
        floor_zone_dict["bounds_y_mm"] = [round(v, 1) for v in floor_bounds_y]
    if floor_zone and floor_zone.thk_filter_bounds_y:
        floor_zone_dict = floor_zone_dict or {}
        floor_zone_dict["label_bounds_y_mm"] = [
            round(v, 1) for v in floor_zone.thk_filter_bounds_y
        ]

    building_model = build_semantic_model(
        project_id=config.project_id,
        source_drawing=dxf_path.name,
        classified=classified,
        graph=graph,
        floor_zone=floor_zone_dict,
        slab_quantities=slabs,
        beam_quantities=beams,
    )

    gt = _load_ground_truth(config, dxf_path.stem)
    benchmark = compute_benchmark_report(totals, gt)

    result = {
        "engine": "SDIE",
        "version": (
            "5.0.0"
            if config.use_v5_pipeline and config.use_v4_pipeline
            else ("4.0.0" if config.use_v4_pipeline else "3.3.0")
        ),
        "architecture": (
            "deepseek_structural_reasoning_engine"
            if config.use_v5_pipeline and config.use_v4_pipeline
            else (
                "knowledge_driven_rag_deepseek"
                if config.use_v4_pipeline
                else "structural_component_intelligence"
            )
        ),
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "source_dxf": str(dxf_path),
        "drawing_meta": asdict(meta),
        "config": {
            "structural_layers": list(config.structural_layers),
            "polygonize_layers": list(poly_layers),
            "annotation_layers": list(config.annotation_layers),
            "detection_mode": config.detection_mode,
            "semantic_pipeline": config.use_semantic_pipeline,
            "coordinate_unit": meta.coordinate_unit,
            "area_to_m2_factor": meta.area_to_m2_factor,
            "min_slab_area_m2": config.min_slab_area_m2,
            "project_id": config.project_id,
        },
        "detection_notes": detection_notes,
        "semantic_building_model": building_model.to_dict(),
        "benchmark": benchmark,
        "notes": {
            "default_thickness_mm": default_mm,
            "default_note_text": note_text,
            "local_thk_label_count": len(thk_labels),
        },
        "slabs": slabs,
        "beams": beams,
        "totals": totals,
    }

    stem = dxf_path.stem
    json_path = output_dir / f"{stem}_results.json"
    model_path = output_dir / f"{stem}_building_model.json"
    summary_path = output_dir / f"{stem}_summary.txt"

    review_path = None
    if config.use_v5_pipeline and config.use_v4_pipeline:
        review_path = write_review_queue(
            output_dir,
            classified,
            stem=stem,
            review_threshold=config.v5_review_threshold,
            force_queue_threshold=config.v5_force_queue_threshold,
        )
        detection_notes["review_queue"] = str(review_path)

    progress.stage("Writing outputs", 92)
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    model_path.write_text(
        json.dumps(building_model.to_dict(), indent=2), encoding="utf-8"
    )

    overlay_geoms = []
    if floor_bounds_y and config.apply_slab_exclusions:
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

    project_root = Path(__file__).resolve().parents[2]
    gt_context = None
    gt_xlsx = find_gt_xlsx_for_stem(stem, project_root)
    if gt_xlsx:
        gt_slabs = load_gt_xlsx(gt_xlsx)
        gt_context = annotate_slabs_with_gt(slabs, gt_slabs)

    overlay_files = write_overlay_outputs(
        stem,
        output_dir,
        slabs,
        meta.extents,
        title=(
            f"SDIE v5 — {dxf_path.name}"
            if config.use_v5_pipeline and config.use_v4_pipeline
            else (
                f"SDIE v4 — {dxf_path.name}"
                if config.use_v4_pipeline
                else f"SDIE v3.3 — {dxf_path.name}"
            )
        ),
        totals=totals,
        excluded_wkt=exclusion_union_wkt,
        classified=classified,
        gt_context=gt_context,
        component_type_counts=type_counts,
        beams=beams,
    )

    version_label = (
        "v5 Structural Reasoning"
        if config.use_v5_pipeline and config.use_v4_pipeline
        else ("v4 RAG" if config.use_v4_pipeline else "v3.3 Semantic")
    )
    summary_lines = [
        f"SDIE {version_label} Pipeline — {dxf_path.name}",
        f"Processed: {result['processed_at']}",
        f"Components classified: {len(classified)}",
        f"Graph: {graph.node_count} nodes, {graph.edge_count} edges",
    ]
    if config.use_v5_pipeline and config.use_v4_pipeline:
        summary_lines.append(
            f"Review queue: {review_count} entities "
            f"({detection_notes.get('low_confidence_pct', 0)}% below {config.v5_review_threshold}%)"
        )
    summary_lines.extend(
        [
            "",
            f"Slabs detected: {totals['slab_count']}",
            f"Slab area:       {totals['area_m2']:.3f} m²",
            f"Slab concrete:   {totals.get('slab_concrete_m3', totals['concrete_m3']):.3f} m³",
            f"Beams quantified: {totals.get('beam_count', 0)}",
            f"Beam length:     {totals.get('beam_total_length_m', 0):.3f} m",
            f"Beam concrete:   {totals.get('beam_concrete_m3', 0):.3f} m³",
            f"Total concrete:  {totals['concrete_m3']:.3f} m³ (slab + beam)",
            f"Total shuttering:{totals['shuttering_m2']:.3f} m²",
            "",
        ]
    )
    if beams:
        summary_lines.append("Beams (first 10):")
        for b in beams[:10]:
            summary_lines.append(
                f"  {b['beam_id']}: L={b['length_m']:.2f} m, "
                f"{b['width_mm']}x{b['depth_mm']} mm, {b['concrete_m3']:.3f} m³"
            )
        if len(beams) > 10:
            summary_lines.append(f"  ... +{len(beams) - 10} more beams")
        summary_lines.append("")
    if benchmark.get("status") == "computed":
        summary_lines.append(
            f"Benchmark overall accuracy: {benchmark.get('overall_accuracy_pct')}%"
        )
    for s in slabs:
        summary_lines.append(
            f"  {s['slab_id']}: {s['area_m2']:.3f} m², "
            f"{s['thickness_mm']} mm ({s['thickness_source']}), "
            f"{s['concrete_m3']:.3f} m³"
        )
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    excel_path = output_dir / f"{stem}_quantities.xlsx"
    try:
        export_results_to_excel(result, excel_path)
    except (RuntimeError, OSError, PermissionError):
        excel_path = None

    result["output_files"] = {
        "json": str(json_path),
        "building_model": str(model_path),
        "svg": overlay_files["svg"],
        "overlay_html": overlay_files["html"],
        "summary": str(summary_path),
    }
    if excel_path is not None:
        result["output_files"]["excel"] = str(excel_path)
    if review_path is not None:
        result["output_files"]["review_queue"] = str(review_path)
    progress.complete(
        f"{totals['slab_count']} slabs, {totals['area_m2']:.1f} m²"
    )
    set_active(None)
    return result
