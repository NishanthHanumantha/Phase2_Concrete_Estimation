from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PipelineConfig:
    """Runtime configuration for a single drawing run (SDIE v6.0)."""

    project_id: str = "GENERIC"
    use_v5_pipeline: bool = True
    use_v4_pipeline: bool = True
    use_semantic_pipeline: bool = True
    knowledge_base_path: Path | None = None
    enable_rag_classification: bool = True
    atlas_path: Path | None = None
    ground_truth_path: Path | None = None
    component_confidence_threshold: float = 75.0
    v5_auto_accept_threshold: float = 90.0
    v5_review_threshold: float = 75.0
    v5_force_queue_threshold: float = 60.0
    enable_deepseek_component_classification: bool = True
    deepseek_classification_batch_size: int = 30
    auto_discover_layers: bool = True
    structural_layers: tuple[str, ...] = ()
    polygonize_layers: tuple[str, ...] | None = None
    annotation_layers: tuple[str, ...] = ()
    frame_layers: tuple[str, ...] = ()
    layer_discovery_notes: dict = field(default_factory=dict)
    detection_mode: str = "auto"  # auto | semantic | region | beam_frame | beam_grid
    min_slab_area_m2: float = 0.4
    tower_min_slab_area_m2: float = 5.0
    podium_min_slab_area_m2: float = 3.0
    dedupe_plan_copies_x: bool = True
    merge_beam_grid_to_estimator_bays: bool = True
    bay_merge_small_preserve_max_m2: float = 3.5
    bay_merge_auto_infer_spans: bool = True
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
    # Slab exclusions: gate semantic (classified) deductions by layer + confidence
    use_layer_gated_semantic_exclusions: bool = True
    semantic_exclusion_min_confidence: float = 82.0
    frame_layer_shear_wall_exclusion_min_confidence: float = 55.0
    enable_podium_beam_grid_slabs: bool = True
    podium_band_gap_mm: float = 500.0
    podium_beam_margin_mm: float = 1500.0
    podium_grid_min_horizontal_span_mm: float = 500.0
    podium_grid_min_vertical_span_mm: float = 1500.0
    exclude_beam_footprints_from_quantity: bool = True
    enable_beam_quantities: bool = True
    min_beam_length_mm: float = 500.0
    min_beam_confidence: float = 70.0
    default_beam_width_mm: int = 300
    default_beam_depth_mm: int = 600
    include_void_label_buffers: bool = False
    beam_layers_for_exclusion: tuple[str, ...] | None = None
    column_exclusion_layers: tuple[str, ...] = ("S-COLS", "S-COL HATCH")
    wall_exclusion_layers: tuple[str, ...] = ()
    hatch_void_layers: tuple[str, ...] = ("SUNK SLAB", "S-COL HATCH")
    cutout_exclusion_layers: tuple[str, ...] = ("STR-CUTOUT",)
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
    show_progress: bool = True
