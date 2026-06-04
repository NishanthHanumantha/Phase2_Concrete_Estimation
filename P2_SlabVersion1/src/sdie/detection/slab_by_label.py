from __future__ import annotations

import math

from shapely import wkt
from shapely.ops import unary_union

from sdie.detection.beam_grid import detect_beam_grid_slabs
from sdie.detection.exclusions import ExclusionCatalog
from sdie.detection.region import SlabCandidate
from sdie.thickness.parser import ThicknessLabel, extract_thk_labels


def _labels_in_band(
    labels: list[ThicknessLabel],
    bounds_y: tuple[float, float] | None,
) -> list[ThicknessLabel]:
    if bounds_y is None:
        return labels
    ymin, ymax = bounds_y
    return [lb for lb in labels if ymin <= lb.xy_cm[1] <= ymax]


def _assign_orphan_labels(
    labels: list[ThicknessLabel],
    groups: list[list[SlabCandidate]],
    cells: list[SlabCandidate],
) -> None:
    for i, grp in enumerate(groups):
        if grp:
            continue
        lx, ly = labels[i].xy_cm[0], labels[i].xy_cm[1]
        best_cell: SlabCandidate | None = None
        best_dist = float("inf")
        best_donor = -1
        for cell in cells:
            cx, cy = cell.centroid_cm
            d = math.hypot(cx - lx, cy - ly)
            if d >= best_dist:
                continue
            owner = -1
            for gi, g in enumerate(groups):
                if cell in g:
                    owner = gi
                    break
            if owner >= 0 and len(groups[owner]) > 1:
                best_dist = d
                best_cell = cell
                best_donor = owner
        if best_cell is not None and best_donor >= 0:
            groups[best_donor].remove(best_cell)
            groups[i].append(best_cell)


def merge_grid_cells_by_label(
    grid_cells: list[SlabCandidate],
    labels: list[ThicknessLabel],
    msp,
    frame_layers: tuple[str, ...],
    *,
    bounds_y: tuple[float, float] | None,
    min_area_m2: float,
    area_to_m2_factor: float,
    slab_face_expand_mm: float = 55.0,
    id_prefix: str = "SLAB",
) -> list[SlabCandidate]:
    """
    Merge net beam-grid cells into one slab polygon per THK label.
    Cell areas are already exclusion-filtered; sum cell areas for BOQ.
    """
    if not grid_cells or not labels:
        return []

    groups: list[list[SlabCandidate]] = [[] for _ in labels]
    for cell in grid_cells:
        cx, cy = cell.centroid_cm
        best = min(
            range(len(labels)),
            key=lambda i: math.hypot(
                cx - labels[i].xy_cm[0], cy - labels[i].xy_cm[1]
            ),
        )
        groups[best].append(cell)

    _assign_orphan_labels(labels, groups, grid_cells)

    candidates: list[SlabCandidate] = []
    idx = 0
    for label, cell_group in zip(labels, groups):
        if not cell_group:
            continue
        area_m2 = sum(c.area_m2 for c in cell_group)
        if area_m2 < min_area_m2:
            continue
        piece = unary_union(
            [wkt.loads(c.polygon_wkt) for c in cell_group]
        )
        if piece.is_empty:
            continue
        if piece.geom_type == "MultiPolygon":
            piece = max(piece.geoms, key=lambda g: g.area)
        if piece.geom_type != "Polygon":
            continue
        idx += 1
        centroid = piece.centroid
        candidates.append(
            SlabCandidate(
                slab_id=f"{id_prefix}-{idx:03d}",
                polygon_wkt=piece.wkt,
                area_m2=round(area_m2, 6),
                centroid_cm=[round(centroid.x, 3), round(centroid.y, 3)],
                bounds_cm=[round(v, 1) for v in piece.bounds],
                strategy="label_merged_bay",
                thickness_mm=label.value_mm,
            )
        )

    return candidates


def detect_label_merged_slabs(
    msp,
    *,
    frame_layers: tuple[str, ...],
    label_layers: tuple[str, ...],
    annotation_layers: tuple[str, ...],
    area_to_m2_factor: float,
    min_area_m2: float,
    bounds_y: tuple[float, float] | None,
    exclusions: ExclusionCatalog | None,
    slab_face_expand_mm: float = 55.0,
    min_labels_for_strategy: int = 25,
    id_prefix: str = "SLAB",
    grid_cells: list[SlabCandidate] | None = None,
) -> list[SlabCandidate]:
    """
    One physical slab per *THK tag on the floor (Prompt §8 semantic model).
    """
    labels = _labels_in_band(
        extract_thk_labels(msp, label_layers), bounds_y
    )
    if len(labels) < min_labels_for_strategy:
        return []

    if grid_cells is None:
        grid_cells = detect_beam_grid_slabs(
            msp,
            frame_layers=frame_layers,
            annotation_layers=annotation_layers,
            area_to_m2_factor=area_to_m2_factor,
            min_area_m2=0.05,
            bounds_y=bounds_y,
            slab_face_expand_mm=slab_face_expand_mm,
            exclusions=exclusions,
            apply_exclusions=exclusions is not None,
            void_label_radius_mm=2200.0,
        )

    return merge_grid_cells_by_label(
        grid_cells,
        labels,
        msp,
        frame_layers,
        bounds_y=bounds_y,
        min_area_m2=min_area_m2,
        area_to_m2_factor=area_to_m2_factor,
        slab_face_expand_mm=slab_face_expand_mm,
        id_prefix=id_prefix,
    )
