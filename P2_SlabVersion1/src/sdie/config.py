from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PipelineConfig:
    """Runtime configuration for a single drawing run."""

    structural_layers: tuple[str, ...] = ("STR-BEAM",)
    polygonize_layers: tuple[str, ...] | None = None
    annotation_layers: tuple[str, ...] = ("G-ANNO-TEXT", "S-BEAM-IDEN")
    detection_mode: str = "auto"  # auto | region | beam_frame | beam_grid
    min_slab_area_m2: float = 10.0
    default_thickness_mm: int = 200
    thickness_label_radius_m: float = 15.0
    slab_edge_expand_mm: float | None = None
    shuttering_equals_soffit: bool = True
    # Beam-grid (Strategy B) — used on S_FRAMES-style framing plans
    grid_min_horizontal_span_mm: float = 3000.0
    grid_min_vertical_span_mm: float = 2000.0
    grid_axis_cluster_tol_mm: float = 300.0
    grid_slab_face_expand_mm: float | None = None
    grid_void_label_radius_mm: float = 2000.0
