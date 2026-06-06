from __future__ import annotations

from shapely import wkt
from shapely.geometry import Point
from shapely.ops import unary_union

from sdie.classification.types import (
    EXCLUSION_COMPONENT_TYPES,
    NON_SLAB_COMPONENTS,
    ClassifiedComponent,
    ComponentType,
)
from sdie.config import PipelineConfig
from sdie.detection.bay_merge import BayMergeParams
from sdie.detection.beam_grid import detect_beam_grid_slabs
from sdie.detection.exclusions import ExclusionCatalog, build_exclusion_catalog
from sdie.detection.floor_zone import FloorZone
from sdie.detection.region import SlabCandidate
from sdie.detection.slab_by_label import detect_label_merged_slabs
from sdie.graph.engine import StructuralGraph

CORE_BUFFER_MM = 4500.0
WALL_BUFFER_MM = 200.0
OPENING_BUFFER_MM = 1500.0
FRAME_SHEAR_WALL_EVIDENCE_PREFIXES = (
    "layer_profile:",
    "geometry:wall",
    "geometry:wall_line",
    "geometry:wall_polyline",
)


def _has_void_evidence(comp: ClassifiedComponent) -> bool:
    ann = comp.annotation_features or {}
    if ann.get("void_keyword") or ann.get("void_component_hint"):
        return True
    return any(e.startswith("void_keyword:") for e in comp.evidence)


def _has_frame_shear_wall_evidence(
    comp: ClassifiedComponent,
    frame_layers: tuple[str, ...],
) -> bool:
    return (
        comp.component_type in (ComponentType.SHEAR_WALL, ComponentType.STRUCTURAL_WALL)
        and (comp.layer or "") in frame_layers
        and any(e.startswith(FRAME_SHEAR_WALL_EVIDENCE_PREFIXES) for e in comp.evidence)
    )


def _effective_exclusion_confidence(
    comp: ClassifiedComponent,
    *,
    frame_layers: tuple[str, ...],
    frame_shear_min: float,
) -> float:
    """V5 blended scores understate high-confidence layer-profile shear walls."""
    if _has_frame_shear_wall_evidence(comp, frame_layers):
        if any(e.startswith("layer_profile:") for e in comp.evidence):
            return max(comp.confidence, 88.0)
        return max(comp.confidence, frame_shear_min)
    return comp.confidence


def _exclusion_confidence_floor(
    comp: ClassifiedComponent,
    *,
    frame_layers: tuple[str, ...],
    default_min: float,
    frame_shear_min: float,
) -> float:
    if _has_frame_shear_wall_evidence(comp, frame_layers):
        return frame_shear_min
    return default_min


def _layer_allows_semantic_exclusion(
    comp: ClassifiedComponent,
    *,
    column_layers: tuple[str, ...],
    wall_layers: tuple[str, ...],
    hatch_void_layers: tuple[str, ...],
    cutout_layers: tuple[str, ...],
    annotation_layers: tuple[str, ...],
    frame_layers: tuple[str, ...],
    min_confidence: float,
    frame_shear_min_confidence: float = 75.0,
) -> bool:
    """Conservative gate — S_FRAMES beam/column lines must not deduct slab bays."""
    layer = comp.layer or ""
    ctype = comp.component_type
    void_evidence = _has_void_evidence(comp)
    void_conf_floor = 60.0

    if ctype in (ComponentType.LIFT_CORE, ComponentType.STAIR_CORE, ComponentType.SHAFT):
        return void_evidence and comp.confidence >= void_conf_floor

    if ctype == ComponentType.OPENING:
        if layer in cutout_layers or layer in hatch_void_layers:
            return comp.confidence >= void_conf_floor
        if void_evidence:
            return comp.confidence >= void_conf_floor
        return False

    conf_floor = _exclusion_confidence_floor(
        comp,
        frame_layers=frame_layers,
        default_min=min_confidence,
        frame_shear_min=frame_shear_min_confidence,
    )
    effective_conf = _effective_exclusion_confidence(
        comp,
        frame_layers=frame_layers,
        frame_shear_min=frame_shear_min_confidence,
    )
    if effective_conf < conf_floor:
        return False

    if ctype == ComponentType.COLUMN:
        if layer in frame_layers:
            return False
        return layer in column_layers
    if ctype in (ComponentType.SHEAR_WALL, ComponentType.STRUCTURAL_WALL):
        if layer in wall_layers:
            return True
        # Inizio-style drawings: perimeter walls share S-BEAM with interior beams.
        if layer in frame_layers and any(
            e.startswith(FRAME_SHEAR_WALL_EVIDENCE_PREFIXES) for e in comp.evidence
        ):
            return True
        return False
    if layer in frame_layers:
        return False
    return False


def _classified_exclusion_geoms(
    classified: list[ClassifiedComponent],
    area_to_m2_factor: float,
    *,
    config: PipelineConfig | None = None,
    frame_layers: tuple[str, ...] = (),
) -> tuple[object | None, list[tuple[str, object]], float]:
    """Build exclusion union from semantically classified non-slab components."""
    parts: list[tuple[str, object]] = []
    gated = config is not None and config.use_layer_gated_semantic_exclusions
    for comp in classified:
        if comp.component_type not in EXCLUSION_COMPONENT_TYPES:
            continue
        if gated and config is not None:
            if not _layer_allows_semantic_exclusion(
                comp,
                column_layers=config.column_exclusion_layers,
                wall_layers=config.wall_exclusion_layers,
                hatch_void_layers=config.hatch_void_layers,
                cutout_layers=config.cutout_exclusion_layers,
                annotation_layers=config.annotation_layers,
                frame_layers=frame_layers,
                min_confidence=config.semantic_exclusion_min_confidence,
                frame_shear_min_confidence=config.frame_layer_shear_wall_exclusion_min_confidence,
            ):
                continue
        if not comp.geometry_wkt:
            if comp.centroid_mm and comp.component_type in (
                ComponentType.LIFT_CORE,
                ComponentType.STAIR_CORE,
                ComponentType.SHAFT,
            ):
                buf = CORE_BUFFER_MM
                if comp.component_type == ComponentType.OPENING:
                    buf = OPENING_BUFFER_MM
                poly = Point(comp.centroid_mm).buffer(buf)
                parts.append((comp.component_type.value, poly))
            continue
        try:
            geom = wkt.loads(comp.geometry_wkt)
        except Exception:
            continue
        if geom.is_empty:
            continue
        buf = WALL_BUFFER_MM
        if comp.component_type in (
            ComponentType.LIFT_CORE,
            ComponentType.STAIR_CORE,
            ComponentType.SHAFT,
        ):
            buf = CORE_BUFFER_MM
        elif comp.component_type == ComponentType.OPENING:
            buf = OPENING_BUFFER_MM
        elif comp.component_type == ComponentType.COLUMN:
            buf = 50.0
        buffered = geom.buffer(buf)
        parts.append((comp.component_type.value, buffered))

    if not parts:
        return None, [], 0.0
    union = unary_union([p[1] for p in parts])
    area_m2 = union.area * area_to_m2_factor if union and not union.is_empty else 0.0
    return union, parts, area_m2


def _merge_exclusions(
    geometric: ExclusionCatalog | None,
    semantic_union: object | None,
    semantic_parts: list[tuple[str, object]],
    area_to_m2_factor: float,
) -> ExclusionCatalog | None:
    geoms = []
    parts: list[tuple[str, object]] = []
    if geometric is not None:
        if geometric.union is not None and not geometric.union.is_empty:
            geoms.append(geometric.union)
        parts.extend(geometric.parts)
    if semantic_union is not None and not semantic_union.is_empty:
        geoms.append(semantic_union)
        parts.extend(semantic_parts)
    if not geoms:
        return geometric
    union = unary_union(geoms)
    return ExclusionCatalog(
        union=union,
        parts=parts,
        area_m2=union.area * area_to_m2_factor,
    )


def _infer_podium_bounds_y(
    floor_bounds_y: tuple[float, float] | None,
    thk_bounds_y: tuple[float, float] | None,
    msp,
    frame_layers: tuple[str, ...],
    *,
    gap_mm: float = 500.0,
    beam_margin_mm: float = 1500.0,
    min_horizontal_span_mm: float = 400.0,
) -> tuple[float, float] | None:
    """
    Band below *THK labels where podium beam framing lives (Inizio-style sheets).
    """
    if floor_bounds_y is None or thk_bounds_y is None:
        return None
    ymin_floor, _ = floor_bounds_y
    ymax_candidate = thk_bounds_y[0] - gap_mm
    if ymax_candidate - ymin_floor < 2500.0:
        return None

    horizontal_ys: list[float] = []
    for entity in msp:
        if entity.dxf.layer not in frame_layers:
            continue
        if entity.dxftype() != "LINE":
            continue
        x1, y1 = entity.dxf.start.x, entity.dxf.start.y
        x2, y2 = entity.dxf.end.x, entity.dxf.end.y
        if abs(y2 - y1) >= 50:
            continue
        if abs(x2 - x1) < min_horizontal_span_mm:
            continue
        if not (ymin_floor <= (y1 + y2) / 2.0 <= ymax_candidate):
            continue
        horizontal_ys.append((y1 + y2) / 2.0)

    if horizontal_ys:
        horiz_span = max(horizontal_ys) - min(horizontal_ys)
        band_height = ymax_candidate - ymin_floor
        # Sparse corner details (Inizio podium) sit far below the THK band — do not
        # collapse ymax to a tight horizontal-beam cap when framing is incomplete.
        if horiz_span >= max(2500.0, band_height * 0.12):
            ymax = min(ymax_candidate, max(horizontal_ys) + beam_margin_mm)
        else:
            ymax = ymax_candidate
    else:
        ymax = ymax_candidate
    if ymax - ymin_floor < 1200.0:
        return None
    return (ymin_floor, ymax)


def _renumber_slab_candidates(
    candidates: list[SlabCandidate],
    *,
    id_prefix: str = "SLAB",
) -> list[SlabCandidate]:
    for idx, cand in enumerate(candidates, start=1):
        cand.slab_id = f"{id_prefix}-{idx:03d}"
    return candidates


def detect_slabs_after_classification(
    msp,
    *,
    config: PipelineConfig,
    classified: list[ClassifiedComponent],
    graph: StructuralGraph,
    floor_zone: FloorZone | None,
    thk_labels: list,
    area_to_m2_factor: float,
    frame_layers: tuple[str, ...],
) -> tuple[list[SlabCandidate], dict]:
    """
    PART 9 — Slab Intelligence Engine.
    Classify Beam/Column/Wall/Core first; then derive slab bays from framed regions.
    """
    notes: dict = {"engine": "slab_intelligence_v3.3"}
    floor_bounds_y = floor_zone.bounds_y if floor_zone else config.floor_bounds_y
    label_bounds_y = (
        floor_zone.thk_filter_bounds_y if floor_zone else floor_bounds_y
    )

    geometric_excl = None
    if config.apply_slab_exclusions:
        beam_ex_layers = ()
        if not config.exclude_beam_footprints_from_quantity:
            beam_ex_layers = config.beam_layers_for_exclusion or frame_layers
        geometric_excl = build_exclusion_catalog(
            msp,
            bounds_y=floor_bounds_y,
            beam_layers=beam_ex_layers,
            column_layers=config.column_exclusion_layers,
            wall_layers=config.wall_exclusion_layers,
            hatch_void_layers=config.hatch_void_layers,
            label_box_layers=config.label_box_exclusion_layers,
            annotation_layers=config.annotation_layers,
            wall_half_width_mm=config.wall_half_width_mm,
            area_to_m2_factor=area_to_m2_factor,
            include_void_label_buffers=config.include_void_label_buffers,
        )

    sem_union, sem_parts, sem_area = _classified_exclusion_geoms(
        classified,
        area_to_m2_factor,
        config=config,
        frame_layers=frame_layers,
    )
    notes["semantic_exclusion_gated"] = config.use_layer_gated_semantic_exclusions
    exclusions = _merge_exclusions(
        geometric_excl, sem_union, sem_parts, area_to_m2_factor
    )
    notes["semantic_exclusion_area_m2"] = round(sem_area, 3)
    notes["semantic_exclusion_parts"] = len(sem_parts)
    if exclusions:
        notes["total_exclusion_area_m2"] = round(exclusions.area_m2, 3)
        notes["total_exclusion_parts"] = len(exclusions.parts)

    non_slab_count = sum(
        1 for c in classified if c.component_type in NON_SLAB_COMPONENTS
    )
    notes["classified_non_slab_count"] = non_slab_count
    notes["graph_nodes"] = graph.node_count
    notes["graph_edges"] = graph.edge_count

    expand = config.grid_slab_face_expand_mm
    if expand is None:
        expand = 55.0

    merge_flag = bool(config.merge_beam_grid_to_estimator_bays)
    notes["merge_beam_grid_to_estimator_bays"] = merge_flag
    bay_merge = BayMergeParams(
        small_bay_preserve_max_m2=config.bay_merge_small_preserve_max_m2,
        min_slab_area_m2=config.min_slab_area_m2,
    )
    grid_notes: dict = {}
    tower_bounds_y = label_bounds_y or floor_bounds_y
    grid_candidates = detect_beam_grid_slabs(
        msp,
        frame_layers=frame_layers,
        annotation_layers=config.annotation_layers,
        area_to_m2_factor=area_to_m2_factor,
        min_area_m2=config.min_slab_area_m2,
        min_horizontal_span_mm=config.grid_min_horizontal_span_mm,
        min_vertical_span_mm=config.grid_min_vertical_span_mm,
        axis_cluster_tol_mm=config.grid_axis_cluster_tol_mm,
        slab_face_expand_mm=expand,
        void_label_radius_mm=config.grid_void_label_radius_mm,
        bounds_y=tower_bounds_y,
        exclusions=exclusions,
        apply_exclusions=config.apply_slab_exclusions,
        merge_to_estimator_bays=merge_flag,
        bay_merge_params=bay_merge if merge_flag else None,
        out_notes=grid_notes,
        id_prefix="SLAB",
    )
    notes.update(grid_notes)
    notes["beam_grid_cell_count"] = len(grid_candidates)
    notes["tower_bounds_y_mm"] = (
        [round(v, 1) for v in tower_bounds_y] if tower_bounds_y else None
    )

    thk_in_floor = [
        lb
        for lb in thk_labels
        if label_bounds_y is None
        or (label_bounds_y[0] <= lb.xy_cm[1] <= label_bounds_y[1])
    ]
    merge_min = config.min_thk_labels_for_merge
    if thk_in_floor and len(thk_in_floor) < merge_min:
        merge_min = max(10, int(len(thk_in_floor) * 0.5))

    label_merged: list[SlabCandidate] = []
    if config.merge_slabs_by_thk_labels and len(thk_in_floor) >= merge_min:
        label_merged = detect_label_merged_slabs(
            msp,
            frame_layers=frame_layers,
            label_layers=config.floor_label_layers,
            annotation_layers=config.annotation_layers,
            area_to_m2_factor=area_to_m2_factor,
            min_area_m2=config.min_slab_area_m2,
            bounds_y=label_bounds_y,
            exclusions=exclusions,
            slab_face_expand_mm=expand,
            min_labels_for_strategy=config.min_thk_labels_for_merge,
            id_prefix="SLAB",
            grid_cells=grid_candidates,
        )
        notes["label_merged_count"] = len(label_merged)

    podium_candidates: list[SlabCandidate] = []
    podium_bounds_y = None
    if config.enable_podium_beam_grid_slabs:
        podium_bounds_y = _infer_podium_bounds_y(
            floor_bounds_y,
            label_bounds_y,
            msp,
            frame_layers,
            gap_mm=config.podium_band_gap_mm,
            beam_margin_mm=config.podium_beam_margin_mm,
            min_horizontal_span_mm=config.podium_grid_min_horizontal_span_mm * 0.8,
        )
        if podium_bounds_y is not None:
            podium_notes: dict = {}
            podium_candidates = detect_beam_grid_slabs(
                msp,
                frame_layers=frame_layers,
                annotation_layers=config.annotation_layers,
                area_to_m2_factor=area_to_m2_factor,
                min_area_m2=config.min_slab_area_m2,
                min_horizontal_span_mm=config.podium_grid_min_horizontal_span_mm,
                min_vertical_span_mm=config.podium_grid_min_vertical_span_mm,
                axis_cluster_tol_mm=config.grid_axis_cluster_tol_mm,
                slab_face_expand_mm=expand,
                void_label_radius_mm=config.grid_void_label_radius_mm,
                bounds_y=podium_bounds_y,
                augment_sparse_grid_axes=True,
                exclusions=exclusions,
                apply_exclusions=config.apply_slab_exclusions,
                merge_to_estimator_bays=merge_flag,
                bay_merge_params=bay_merge if merge_flag else None,
                out_notes=podium_notes,
                id_prefix="POD",
            )
            for cand in podium_candidates:
                cand.strategy = "semantic_podium_beam_grid_bay_merged"
            notes["podium_bounds_y_mm"] = [round(v, 1) for v in podium_bounds_y]
            notes["podium_beam_grid_cell_count"] = len(podium_candidates)
            notes["podium_beam_grid_area_m2"] = round(
                sum(c.area_m2 for c in podium_candidates), 3
            )
            if podium_notes.get("estimator_bay_merge"):
                notes["podium_bay_merge"] = podium_notes["estimator_bay_merge"]

    if label_merged:
        candidates = label_merged
        notes["selected"] = "semantic_label_merged_bay"
    elif grid_candidates:
        candidates = grid_candidates
        if grid_notes.get("estimator_bay_merge"):
            notes["selected"] = "semantic_beam_grid_bay_merged"
        else:
            notes["selected"] = "semantic_beam_grid_bay"
    else:
        candidates = []
        notes["selected"] = "none"

    if podium_candidates:
        candidates = _renumber_slab_candidates(
            candidates + podium_candidates,
            id_prefix="SLAB",
        )
        notes["selected"] = f"{notes['selected']}+podium_grid"
        notes["slab_count_with_podium"] = len(candidates)

    for cand in candidates:
        if cand.strategy.startswith("semantic_podium"):
            continue
        cand.strategy = notes["selected"].split("+")[0]

    return candidates, notes
