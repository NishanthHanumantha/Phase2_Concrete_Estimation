"""Generic bay-merge behaviour — partial fragments merge, terraces preserved."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdie.detection.bay_merge import BayMergeParams, _GridCell, merge_raw_grid_cells

FACTOR = 1e-6


def _cell(i, j, xmin, ymin, xmax, ymax) -> _GridCell:
    return _GridCell(i=i, j=j, xmin=xmin, xmax=xmax, ymin=ymin, ymax=ymax)


def test_compact_terrace_not_merged_into_full_bay():
    """1.5x0.8 m terrace beside 6 m bay — must stay separate."""
    terrace = _cell(0, 0, 0, 0, 1600, 900)
    full_bay = _cell(1, 0, 1500, 0, 7500, 6200)
    params = BayMergeParams(
        full_bay_span_mm=6000,
        partial_span_mm=2900,
        small_bay_preserve_max_m2=3.5,
        min_slab_area_m2=0.4,
        auto_inferred=True,
    )
    merged, notes = merge_raw_grid_cells(
        [terrace, full_bay],
        area_to_m2_factor=FACTOR,
        params=params,
    )
    assert len(merged) == 2
    assert notes["horizontal_merges"] == 0
    assert notes["vertical_merges"] == 0


def test_partial_width_fragments_merge():
    """Two narrow width fragments on same row form one estimator bay."""
    left = _cell(0, 0, 0, 0, 2400, 6500)
    right = _cell(1, 0, 2200, 0, 6500, 6500)
    params = BayMergeParams(
        full_bay_span_mm=6000,
        partial_span_mm=2900,
        max_merged_span_mm=7000.0,
        max_merged_raw_area_m2=45.0,
        auto_inferred=True,
    )
    merged, notes = merge_raw_grid_cells(
        [left, right],
        area_to_m2_factor=FACTOR,
        params=params,
    )
    assert len(merged) == 1
    assert notes["horizontal_merges"] == 1


def test_infer_spans_from_cell_population():
    cells = [
        _cell(0, 0, 0, 0, 6500, 6200),
        _cell(1, 0, 6500, 0, 12500, 6200),
        _cell(0, 1, 0, 6200, 1600, 7100),
    ]
    params = BayMergeParams.infer_from_cells(cells, area_to_m2_factor=FACTOR)
    assert params.full_bay_span_mm >= 3500
    assert params.auto_inferred is True


def test_full_width_vertical_stack_merge():
    """Full-width column cells stack into one large estimator bay (S43-style)."""
    top = _cell(8, 5, 10000, 14500, 15500, 17700)
    mid = _cell(8, 6, 10000, 17700, 15500, 18700)
    bot = _cell(8, 7, 10000, 18700, 15500, 20900)
    params = BayMergeParams(
        full_bay_span_mm=5475.0,
        partial_span_mm=2900.0,
        max_merged_span_mm=11000.0,
        max_merged_raw_area_m2=45.0,
        auto_inferred=True,
    )
    merged, notes = merge_raw_grid_cells(
        [top, mid, bot],
        area_to_m2_factor=FACTOR,
        params=params,
    )
    assert len(merged) == 1
    assert notes["vertical_merges"] >= 2
    area = merged[0].raw_area_m2(FACTOR)
    assert 25.0 <= area <= 40.0
