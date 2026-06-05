from __future__ import annotations

from dataclasses import dataclass

from sdie.detection.region import SlabCandidate

PARTIAL_SPAN_MM = 2900.0
MAX_MERGED_SPAN_MM = 5200.0
PARTIAL_RAW_AREA_M2 = 8.5
MAX_MERGED_RAW_AREA_M2 = 16.5


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


def _can_merge_horizontal(a: _GridCell, b: _GridCell, factor: float) -> bool:
    if not _same_row(a, b):
        return False
    # Beam-grid cells overlap at axis lines (slab_face_expand on both sides).
    if _span_overlap(a.xmin, a.xmax, b.xmin, b.xmax) < 40.0:
        return False
    combined = a.merge(b)
    if combined.width_mm() > MAX_MERGED_SPAN_MM:
        return False
    if combined.raw_area_m2(factor) > MAX_MERGED_RAW_AREA_M2:
        return False
    return (
        a.width_mm() < PARTIAL_SPAN_MM
        or b.width_mm() < PARTIAL_SPAN_MM
        or a.raw_area_m2(factor) < PARTIAL_RAW_AREA_M2
        or b.raw_area_m2(factor) < PARTIAL_RAW_AREA_M2
    )


def _can_merge_vertical(a: _GridCell, b: _GridCell, factor: float) -> bool:
    if not _same_col(a, b):
        return False
    if _span_overlap(a.ymin, a.ymax, b.ymin, b.ymax) < 40.0:
        return False
    combined = a.merge(b)
    if combined.height_mm() > MAX_MERGED_SPAN_MM:
        return False
    if combined.raw_area_m2(factor) > MAX_MERGED_RAW_AREA_M2:
        return False
    return (
        a.height_mm() < PARTIAL_SPAN_MM
        or b.height_mm() < PARTIAL_SPAN_MM
        or a.raw_area_m2(factor) < PARTIAL_RAW_AREA_M2
        or b.raw_area_m2(factor) < PARTIAL_RAW_AREA_M2
    )


def merge_raw_grid_cells(
    cells: list[_GridCell],
    *,
    area_to_m2_factor: float,
) -> tuple[list[_GridCell], dict]:
    """Merge partial beam-grid bays on axis indices before exclusion clipping."""
    notes = {"input_count": len(cells), "horizontal_merges": 0, "vertical_merges": 0}
    if len(cells) < 2:
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
                        _can_merge_horizontal(a, b, area_to_m2_factor)
                        if axis == "horizontal"
                        else _can_merge_vertical(a, b, area_to_m2_factor)
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
