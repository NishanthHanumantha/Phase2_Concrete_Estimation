from __future__ import annotations

from dataclasses import dataclass

from sdie.detection.region import SlabCandidate


@dataclass
class BayMergeParams:
    """
    Generic estimator-bay merge tuning.

    Partial fragments (one axis short, other axis full bay width) are merged.
    Compact standalone bays (terraces, balconies, small landings) are preserved.
    """

    partial_span_mm: float = 2900.0
    full_bay_span_mm: float = 4500.0
    max_merged_span_mm: float = 5200.0
    partial_raw_area_m2: float = 8.5
    max_merged_raw_area_m2: float = 16.5
    small_bay_preserve_max_m2: float = 3.5
    min_area_ratio_for_merge: float = 0.35
    compact_bay_span_ratio: float = 0.38
    min_slab_area_m2: float = 0.4
    auto_inferred: bool = False

    @classmethod
    def infer_from_cells(
        cls,
        cells: list["_GridCell"],
        *,
        area_to_m2_factor: float,
        min_slab_area_m2: float = 0.4,
    ) -> BayMergeParams:
        """
        Derive span thresholds from the grid (drawing-agnostic).

        Uses an upper-percentile of cell spans so small terraces/balconies do not
        shrink the estimated full-bay size used for partial-fragment merging.
        """
        if not cells:
            return cls(min_slab_area_m2=min_slab_area_m2)

        widths = [c.width_mm() for c in cells]
        heights = [c.height_mm() for c in cells]
        areas = [c.raw_area_m2(area_to_m2_factor) for c in cells]
        large_spans = sorted(max(w, h) for w, h in zip(widths, heights))

        idx = max(0, int(len(large_spans) * 0.72) - 1)
        idx = min(idx, len(large_spans) - 1)
        ref_span = large_spans[idx]
        full_bay = max(4500.0, ref_span * 0.94)
        partial = max(2500.0, min(3100.0, full_bay * 0.50))

        return cls(
            partial_span_mm=partial,
            full_bay_span_mm=full_bay,
            min_slab_area_m2=min_slab_area_m2,
            auto_inferred=True,
        )


@dataclass
class _GridCell:
    i: int
    j: int
    xmin: float
    xmax: float
    ymin: float
    ymax: float

    def raw_area_m2(self, area_to_m2_factor: float) -> float:
        return (self.xmax - self.xmin) * (self.ymax - self.ymin) * area_to_m2_factor

    def width_mm(self) -> float:
        return self.xmax - self.xmin

    def height_mm(self) -> float:
        return self.ymax - self.ymin

    def merge(self, other: _GridCell) -> _GridCell:
        return _GridCell(
            i=min(self.i, other.i),
            j=min(self.j, other.j),
            xmin=min(self.xmin, other.xmin),
            xmax=max(self.xmax, other.xmax),
            ymin=min(self.ymin, other.ymin),
            ymax=max(self.ymax, other.ymax),
        )


def _span_overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return min(a1, b1) - max(a0, b0)


def _span_touch_or_overlap(
    a0: float,
    a1: float,
    b0: float,
    b1: float,
    *,
    min_overlap: float = 40.0,
    gap_tol: float = 80.0,
) -> bool:
    """Grid neighbours often share an edge (zero overlap) — count touching spans too."""
    if _span_overlap(a0, a1, b0, b1) >= min_overlap:
        return True
    return min(abs(a1 - b0), abs(b1 - a0)) <= gap_tol


def _same_row(a: _GridCell, b: _GridCell, tol: float = 80.0) -> bool:
    return (
        abs(a.ymin - b.ymin) <= tol
        and abs(a.ymax - b.ymax) <= tol
    ) or _span_overlap(a.ymin, a.ymax, b.ymin, b.ymax) > 0.5 * min(
        a.height_mm(), b.height_mm()
    )


def _same_col(a: _GridCell, b: _GridCell, tol: float = 80.0) -> bool:
    return (
        abs(a.xmin - b.xmin) <= tol
        and abs(a.xmax - b.xmax) <= tol
    ) or _span_overlap(a.xmin, a.xmax, b.xmin, b.xmax) > 0.5 * min(
        a.width_mm(), b.width_mm()
    )


def _is_compact_standalone(
    cell: _GridCell,
    params: BayMergeParams,
    factor: float,
) -> bool:
    """
    Small complete bay (terrace, balcony, landing) — both footprints are modest
    relative to typical structural bays on the same drawing.
    """
    area = cell.raw_area_m2(factor)
    if area < params.min_slab_area_m2 or area > params.small_bay_preserve_max_m2:
        return False
    max_dim = max(cell.width_mm(), cell.height_mm())
    return max_dim < params.full_bay_span_mm * params.compact_bay_span_ratio


def _is_row_sliver(cell: _GridCell, *, max_height_mm: float = 1200.0) -> bool:
    return cell.height_mm() < max_height_mm


def _area_merge_allowed(
    a: _GridCell,
    b: _GridCell,
    params: BayMergeParams,
    factor: float,
) -> bool:
    """Block merging a small standalone bay into a much larger neighbour."""
    a_area = a.raw_area_m2(factor)
    b_area = b.raw_area_m2(factor)
    small, large = (a_area, b_area) if a_area <= b_area else (b_area, a_area)
    if small > params.small_bay_preserve_max_m2:
        return True
    if large <= 0:
        return False
    return (small / large) >= params.min_area_ratio_for_merge


def _has_partial_extent_horizontal(cell: _GridCell, params: BayMergeParams, factor: float) -> bool:
    """One axis still looks like a split fragment of a larger estimator bay."""
    return (
        cell.width_mm() < params.partial_span_mm
        or cell.raw_area_m2(factor) < params.partial_raw_area_m2
    )


def _has_partial_extent_vertical(cell: _GridCell, params: BayMergeParams, factor: float) -> bool:
    return (
        cell.height_mm() < params.partial_span_mm
        or cell.raw_area_m2(factor) < params.partial_raw_area_m2
    )


def _column_stack_pair(
    a: _GridCell,
    b: _GridCell,
    params: BayMergeParams,
    factor: float,
) -> bool:
    """
    Decide whether two same-column cells are row fragments of one estimator bay.

    Avoid bridging two adjacent full-height bays (e.g. j=4 + j=5) while still
    allowing sliver bands and modest lower extensions (S43: j=5 + j=6 + j=7).
    """
    if _is_row_sliver(a) or _is_row_sliver(b):
        return True
    a_area = a.raw_area_m2(factor)
    b_area = b.raw_area_m2(factor)
    small, large = (a_area, b_area) if a_area <= b_area else (b_area, a_area)
    if (
        a_area > params.partial_raw_area_m2
        and b_area > params.partial_raw_area_m2
        and min(a.height_mm(), b.height_mm()) > 2100.0
        and max(a_area, b_area) < 18.0
    ):
        return False
    if small < 10.0 and large >= small * 1.5:
        return True
    if 10.0 <= small <= 15.5 and large >= small * 1.55:
        return True
    return False


def _column_stack_merge(
    a: _GridCell,
    b: _GridCell,
    factor: float,
    params: BayMergeParams,
) -> bool:
    """Same-column row fragments stacking into a multi-row estimator bay (e.g. 5x5 m)."""
    if not _same_col(a, b):
        return False
    if not _column_stack_pair(a, b, params, factor):
        return False
    combined = a.merge(b)
    span_cap = max(params.max_merged_span_mm, params.full_bay_span_mm * 1.45)
    area_cap = max(params.max_merged_raw_area_m2, 42.0)
    return (
        combined.height_mm() <= span_cap
        and combined.raw_area_m2(factor) <= area_cap
    )


def _can_merge_horizontal(
    a: _GridCell,
    b: _GridCell,
    factor: float,
    params: BayMergeParams,
) -> bool:
    if not _same_row(a, b):
        return False
    if _span_overlap(a.xmin, a.xmax, b.xmin, b.xmax) < 40.0:
        return False
    if _is_compact_standalone(a, params, factor) or _is_compact_standalone(b, params, factor):
        return False
    if not _area_merge_allowed(a, b, params, factor):
        return False

    combined = a.merge(b)
    if combined.width_mm() > params.max_merged_span_mm:
        return False
    if combined.raw_area_m2(factor) > params.max_merged_raw_area_m2:
        return False
    return _has_partial_extent_horizontal(a, params, factor) or _has_partial_extent_horizontal(
        b, params, factor
    )


def _can_merge_vertical(
    a: _GridCell,
    b: _GridCell,
    factor: float,
    params: BayMergeParams,
) -> bool:
    if not _same_col(a, b):
        return False
    if not _span_touch_or_overlap(a.ymin, a.ymax, b.ymin, b.ymax):
        return False
    if _is_compact_standalone(a, params, factor) or _is_compact_standalone(b, params, factor):
        return False
    if not (
        _has_partial_extent_vertical(a, params, factor)
        or _has_partial_extent_vertical(b, params, factor)
        or _is_row_sliver(a)
        or _is_row_sliver(b)
    ):
        return False
    if not _column_stack_merge(a, b, factor, params):
        return False
    if not _area_merge_allowed(a, b, params, factor):
        if not (_is_row_sliver(a) or _is_row_sliver(b) or _column_stack_pair(a, b, params, factor)):
            return False
    return True


def merge_raw_grid_cells(
    cells: list[_GridCell],
    *,
    area_to_m2_factor: float,
    params: BayMergeParams | None = None,
) -> tuple[list[_GridCell], dict]:
    """Merge partial beam-grid bays; preserve compact terraces and small landings."""
    merge_params = params or BayMergeParams.infer_from_cells(
        cells,
        area_to_m2_factor=area_to_m2_factor,
    )
    notes: dict = {
        "input_count": len(cells),
        "horizontal_merges": 0,
        "vertical_merges": 0,
        "merge_params": {
            "partial_span_mm": round(merge_params.partial_span_mm, 1),
            "full_bay_span_mm": round(merge_params.full_bay_span_mm, 1),
            "max_merged_span_mm": round(merge_params.max_merged_span_mm, 1),
            "max_merged_raw_area_m2": round(merge_params.max_merged_raw_area_m2, 2),
            "small_bay_preserve_max_m2": merge_params.small_bay_preserve_max_m2,
            "auto_inferred": merge_params.auto_inferred,
        },
        "compact_cells_preserved": sum(
            1
            for c in cells
            if _is_compact_standalone(c, merge_params, area_to_m2_factor)
        ),
    }
    if len(cells) < 2:
        notes["output_count"] = len(cells)
        return cells, notes

    merged = list(cells)
    changed = True
    while changed:
        changed = False
        for axis in ("horizontal", "vertical"):
            best_score = -1.0
            best_pair: tuple[int, int] | None = None
            for ai, a in enumerate(merged):
                for bi, b in enumerate(merged):
                    if bi <= ai:
                        continue
                    ok = (
                        _can_merge_horizontal(a, b, area_to_m2_factor, merge_params)
                        if axis == "horizontal"
                        else _can_merge_vertical(a, b, area_to_m2_factor, merge_params)
                    )
                    if not ok:
                        continue
                    combined = a.merge(b)
                    score = combined.raw_area_m2(area_to_m2_factor)
                    if score > best_score:
                        best_score = score
                        best_pair = (ai, bi)
            if best_pair is not None:
                ai, bi = best_pair
                lo, hi = (ai, bi) if ai > bi else (bi, ai)
                merged[lo] = merged[ai].merge(merged[bi])
                merged.pop(hi)
                notes[f"{axis}_merges"] += 1
                changed = True
                break

    notes["output_count"] = len(merged)
    return merged, notes


def merge_estimator_bays(
    candidates: list[SlabCandidate],
    *,
    area_to_m2_factor: float,
    id_prefix: str = "SLAB",
    strategy: str = "semantic_beam_grid_bay_merged",
    **_,
) -> tuple[list[SlabCandidate], dict]:
    """Legacy post-exclusion merge (kept for compatibility; grid merge preferred)."""
    return candidates, {"input_count": len(candidates), "output_count": len(candidates)}
