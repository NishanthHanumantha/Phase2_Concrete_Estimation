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
from sdie.detection.beam_grid import detect_beam_grid_slabs
from sdie.detection.exclusions import ExclusionCatalog, build_exclusion_catalog
from sdie.detection.floor_zone import FloorZone
from sdie.detection.region import SlabCandidate
from sdie.detection.slab_by_label import detect_label_merged_slabs
from sdie.graph.engine import StructuralGraph

CORE_BUFFER_MM = 4500.0
WALL_BUFFER_MM = 200.0
OPENING_BUFFER_MM = 1500.0


def _classified_exclusion_geoms(
    classified: list[ClassifiedComponent],
    area_to_m2_factor: float,
) -> tuple[object | None, list[tuple[str, object]], float]:
    """Build exclusion union from semantically classified non-slab components."""
    parts: list[tuple[str, object]] = []
    for comp in classified:
        if comp.component_type not in EXCLUSION_COMPONENT_TYPES:
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
        classified, area_to_m2_factor
    )
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
        bounds_y=floor_bounds_y,
        exclusions=exclusions,
        apply_exclusions=config.apply_slab_exclusions,
        id_prefix="SLAB",
    )
    notes["beam_grid_cell_count"] = len(grid_candidates)

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

    if label_merged:
        candidates = label_merged
        notes["selected"] = "semantic_label_merged_bay"
    elif grid_candidates:
        candidates = grid_candidates
        notes["selected"] = "semantic_beam_grid_bay"
    else:
        candidates = []
        notes["selected"] = "none"

    for cand in candidates:
        cand.strategy = notes["selected"]

    return candidates, notes
