from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DXF = ROOT / "Data Source" / "Slab Test" / "Inizio_B2_LayerTest1.dxf"


@pytest.mark.skipif(not DXF.is_file(), reason="benchmark DXF missing")
def test_inizio_cluster_floor_includes_most_thk_labels():
    from sdie.ingestion.dxf_reader import load_drawing
    from sdie.detection.floor_zone import resolve_floor_zone

    doc, _ = load_drawing(DXF)
    zone = resolve_floor_zone(
        doc.modelspace(),
        label_layers=("A-FLOR-IDEN",),
        frame_layers=("S-BEAM",),
        mode="cluster",
    )
    assert zone.bounds_y is not None
    assert zone.label_count >= 73
    assert zone.method == "thk_cluster"
    assert zone.label_bounds_y is not None
    assert zone.bounds_y[1] < zone.label_bounds_y[1]


@pytest.mark.skipif(not DXF.is_file(), reason="benchmark DXF missing")
def test_legacy_band_fewer_labels_than_cluster():
    from sdie.ingestion.dxf_reader import load_drawing
    from sdie.detection.floor_zone import resolve_floor_zone

    doc, _ = load_drawing(DXF)
    legacy = resolve_floor_zone(
        doc.modelspace(),
        label_layers=("A-FLOR-IDEN",),
        mode="legacy",
    )
    cluster = resolve_floor_zone(
        doc.modelspace(),
        label_layers=("A-FLOR-IDEN",),
        frame_layers=("S-BEAM",),
        mode="cluster",
    )
    assert cluster.label_count > legacy.label_count
