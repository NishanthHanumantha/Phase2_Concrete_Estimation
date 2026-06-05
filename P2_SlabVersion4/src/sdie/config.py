from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PipelineConfig:
    """Runtime configuration for a single drawing run (SDIE v4.0)."""

    project_id: str = "INIZIO"
    use_v4_pipeline: bool = True
    use_semantic_pipeline: bool = True
    knowledge_base_path: Path | None = None
    enable_rag_classification: bool = True
    atlas_path: Path | None = None
    ground_truth_path: Path | None = None
    component_confidence_threshold: float = 65.0
    enable_deepseek_component_classification: bool = True
    deepseek_classification_batch_size: int = 30
    structural_layers: tuple[str, ...] = ("STR-BEAM",)
    polygonize_layers: tuple[str, ...] | None = None
    annotation_layers: tuple[str, ...] = (
        "G-ANNO-TEXT",
        "S-BEAM-IDEN",
        "A-FLOR-IDEN",
    )
    detection_mode: str = "auto"  # auto | semantic | region | beam_frame | beam_grid
    min_slab_area_m2: float = 0.4
    merge_beam_grid_to_estimator_bays: bool = True
    default_thickness_mm: int = 200
    thickness_label_radius_m: float = 15.0
    slab_edge_expand_mm: float | None = None
    shuttering_equals_soffit: bool = True
    # Beam-grid (Strategy B) — used on S_FRAMES-style framing plans
    grid_min_horizontal_span_mm: float = 3000.0
    grid_min_vertical_span_mm: float = 2000.0
    grid_axis_cluster_tol_mm: float = 300.0
    grid_void_label_radius_mm: float = 2200.0
    grid_slab_face_expand_mm: float | None = 55.0
    apply_slab_exclusions: bool = True
    exclude_beam_footprints_from_quantity: bool = True
    include_void_label_buffers: bool = False
    beam_layers_for_exclusion: tuple[str, ...] | None = None
    column_exclusion_layers: tuple[str, ...] = ("S-COLS", "S-COL HATCH")
    wall_exclusion_layers: tuple[str, ...] = ()
    hatch_void_layers: tuple[str, ...] = ("SUNK SLAB", "S-COL HATCH")
    label_box_exclusion_layers: tuple[str, ...] = ()
    wall_half_width_mm: float = 100.0
    # Floor zone (multi-panel DXF) — None = auto from A-FLOR-IDEN *THK labels
    floor_bounds_y: tuple[float, float] | None = None
    floor_label_layers: tuple[str, ...] = ("A-FLOR-IDEN",)
    auto_floor_zone: bool = True
    floor_zone_mode: str = "cluster"  # cluster | legacy | manual
    floor_cluster_gap_mm: float = 6000.0
    floor_cluster_margin_mm: float = 5000.0
    thk_label_max_distance_mm: float = 3300.0
    merge_slabs_by_thk_labels: bool = True
    min_thk_labels_for_merge: int = 25
    # DeepSeek reasoning (Prompt §6 — semantic only, no quantity math)
    enable_deepseek_refinement: bool = False
    deepseek_model: str = "deepseek-chat"  # DeepSeek-V3 via API; auto | deepseek-reasoner
    deepseek_base_url: str = "https://api.deepseek.com"
