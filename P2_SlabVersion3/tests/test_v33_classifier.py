from sdie.classification.classifier import classify_entity
from sdie.classification.types import ComponentType
from sdie.ingestion.entity_extractor import DrawingEntity


def test_thk_text_classified_as_slab():
    entity = DrawingEntity(
        entity_id="ENT-00001",
        handle="1",
        layer="A-FLOR-IDEN",
        entity_type="TEXT",
        geometry_wkt=None,
        centroid_mm=(1000.0, 2000.0),
        bounds_mm=(1000.0, 2000.0, 1000.0, 2000.0),
        text="275 THK",
    )
    comp = classify_entity(entity)
    assert comp.component_type == ComponentType.SLAB
    assert comp.confidence >= 50
    assert "thk_annotation" in comp.evidence


def test_stair_keyword_classified_as_stair_core():
    entity = DrawingEntity(
        entity_id="ENT-00002",
        handle="2",
        layer="G-ANNO-TEXT",
        entity_type="TEXT",
        geometry_wkt=None,
        centroid_mm=(500.0, 500.0),
        bounds_mm=(500.0, 500.0, 500.0, 500.0),
        text="STAIRCASE",
    )
    comp = classify_entity(entity)
    assert comp.component_type == ComponentType.STAIR_CORE


def test_confidence_breakdown_weights():
    entity = DrawingEntity(
        entity_id="ENT-00003",
        handle="3",
        layer="S_FRAMES",
        entity_type="LINE",
        geometry_wkt="LINESTRING (0 0, 5000 0)",
        centroid_mm=(2500.0, 0.0),
        bounds_mm=(0.0, 0.0, 5000.0, 0.0),
        length_mm=5000.0,
        aspect_ratio=50.0,
    )
    comp = classify_entity(entity)
    assert comp.component_type == ComponentType.BEAM
    assert "geometry" in comp.confidence_breakdown
    assert comp.confidence_breakdown["final"] > 0
