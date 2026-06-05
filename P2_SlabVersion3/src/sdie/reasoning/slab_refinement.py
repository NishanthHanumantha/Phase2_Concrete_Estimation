from __future__ import annotations

import json
import logging
from typing import Any

from shapely import wkt
from shapely.ops import unary_union

from sdie.detection.region import SlabCandidate
from sdie.detection.slab_by_label import merge_grid_cells_by_label
from sdie.reasoning.context import (
    _labels_in_band,
    build_slab_reasoning_context,
    collect_void_annotations,
    summarize_layers,
)
from sdie.reasoning.deepseek_client import (
    DeepSeekError,
    chat_json,
    resolve_model,
)
from sdie.thickness.parser import ThicknessLabel, extract_thk_labels

logger = logging.getLogger(__name__)

MAX_CELL_EXCLUSION_RATIO = 0.20

SYSTEM_PROMPT = """You are a senior structural engineer validating automated slab detection on a consultant DXF (SDIE).

SEMANTIC decisions only — never compute areas, volumes, or totals.

Input:
- merged_slabs_preview: one candidate slab per A-FLOR-IDEN *THK tag (already beam-grid merged).
- void_annotations: STAIR/LIFT/RAMP/SHAFT text locations — slabs whose centroid is within ~5m of these are NOT slab.
- grid_cells: optional; only flag obvious non-slab cells (stairs/lifts/columns), NOT the whole grid.

Rules:
- DEFAULT: keep merged slabs — they represent cast-in-place slab between beams.
- EXCLUDE a merged slab only if: (a) area < 3 m² and clearly a label box/artifact, or (b) centroid beside void_annotations, or (c) duplicate THK tag on another floor band.
- exclude_cell_ids: maximum 40 ids, only cells clearly in stair/lift/column pockets — NEVER exclude more than 20% of grid_cells.
- merge_groups: optional list of slab_id groups that are one physical pour (rare).

Return JSON:
{
  "exclude_merged_slab_ids": [],
  "exclude_cell_ids": [],
  "merge_groups": [],
  "min_slab_area_m2": 2.0,
  "confidence": 0.85,
  "evidence": ["..."],
  "reasoning": "..."
}"""


def _parse_cell_id(cell_id: str) -> int | None:
    if not cell_id or not cell_id.startswith("G-"):
        return None
    try:
        return int(cell_id[2:]) - 1
    except ValueError:
        return None


def _filter_grid_cells(
    grid_cells: list[SlabCandidate],
    exclude_cell_ids: list[str],
    max_ratio: float = MAX_CELL_EXCLUSION_RATIO,
) -> tuple[list[SlabCandidate], bool]:
    exclude_idx = set()
    for cid in exclude_cell_ids:
        idx = _parse_cell_id(str(cid).strip())
        if idx is not None and 0 <= idx < len(grid_cells):
            exclude_idx.add(idx)
    if grid_cells and len(exclude_idx) / len(grid_cells) > max_ratio:
        return grid_cells, False
    return [c for i, c in enumerate(grid_cells) if i not in exclude_idx], True


def _apply_merge_groups(
    slabs: list[SlabCandidate],
    merge_groups: list[list[str]],
) -> list[SlabCandidate]:
    if not merge_groups:
        return slabs
    by_id = {s.slab_id: s for s in slabs}
    consumed: set[str] = set()
    merged: list[SlabCandidate] = []

    for group in merge_groups:
        ids = [gid for gid in group if gid in by_id]
        if len(ids) < 2:
            continue
        pieces = [wkt.loads(by_id[i].polygon_wkt) for i in ids]
        union = unary_union(pieces)
        if union.is_empty:
            continue
        if union.geom_type == "MultiPolygon":
            union = max(union.geoms, key=lambda g: g.area)
        if union.geom_type != "Polygon":
            continue
        area_m2 = sum(by_id[i].area_m2 for i in ids)
        thk = by_id[ids[0]].thickness_mm
        centroid = union.centroid
        merged.append(
            SlabCandidate(
                slab_id=ids[0],
                polygon_wkt=union.wkt,
                area_m2=round(area_m2, 6),
                centroid_cm=[round(centroid.x, 3), round(centroid.y, 3)],
                bounds_cm=[round(v, 1) for v in union.bounds],
                strategy="label_merged_bay_llm",
                thickness_mm=thk,
            )
        )
        consumed.update(ids)

    for s in slabs:
        if s.slab_id not in consumed:
            merged.append(s)

    for i, s in enumerate(merged, start=1):
        s.slab_id = f"SLAB-{i:03d}"
    return merged


def _filter_merged_slabs(
    slabs: list[SlabCandidate],
    exclude_ids: list[str],
    min_area_m2: float,
) -> list[SlabCandidate]:
    exclude_set = {str(s).strip() for s in exclude_ids}
    out = [
        s
        for s in slabs
        if s.slab_id not in exclude_set and s.area_m2 >= min_area_m2
    ]
    for i, s in enumerate(out, start=1):
        s.slab_id = f"SLAB-{i:03d}"
        s.strategy = "label_merged_bay_llm"
    return out


def _slabs_near_void(
    slabs: list[SlabCandidate],
    void_annotations: list[dict[str, Any]],
    radius_mm: float = 5000.0,
) -> list[str]:
    """Deterministic pre-filter: slabs whose centroid is near void text."""
    exclude: list[str] = []
    for s in slabs:
        cx, cy = s.centroid_cm
        for v in void_annotations:
            dx = cx - v["x_mm"]
            dy = cy - v["y_mm"]
            if dx * dx + dy * dy <= radius_mm * radius_mm:
                exclude.append(s.slab_id)
                break
    return exclude


_RETRYABLE = frozenset(
    {
        "rejected_too_many_slab_exclusions",
        "rejected_area_drop",
        "empty_after_filter",
        "error",
    }
)


def _apply_llm_result(
    base: list[SlabCandidate],
    grid_cells: list[SlabCandidate],
    labels_floor: list[ThicknessLabel],
    result: dict[str, Any],
    void_ann: list[dict[str, Any]],
    *,
    msp,
    frame_layers: tuple[str, ...],
    floor_bounds_y: tuple[float, float] | None,
    min_area_m2: float,
    area_to_m2_factor: float,
) -> tuple[list[SlabCandidate], dict[str, Any]]:
    notes: dict[str, Any] = {}
    geom_area = sum(c.area_m2 for c in base)
    min_llm_area = min(
        float(result.get("min_slab_area_m2") or min_area_m2),
        min_area_m2,
    )
    exclude_slabs = list(result.get("exclude_merged_slab_ids") or [])
    void_exclude = _slabs_near_void(base, void_ann)
    notes["void_proximity_excludes"] = void_exclude
    exclude_slabs = list(set(exclude_slabs + void_exclude))

    if len(exclude_slabs) > max(12, int(len(base) * 0.15)):
        notes["status"] = "rejected_too_many_slab_exclusions"
        notes["rejected_exclude_count"] = len(exclude_slabs)
        return base, notes

    candidates = _filter_merged_slabs(base, exclude_slabs, min_llm_area)
    out_area = sum(c.area_m2 for c in candidates)
    if out_area < geom_area * 0.97:
        notes["status"] = "rejected_area_drop"
        notes["geometric_area_m2"] = round(geom_area, 3)
        notes["llm_area_m2"] = round(out_area, 3)
        return base, notes

    merge_groups = result.get("merge_groups") or []
    if merge_groups:
        candidates = _apply_merge_groups(candidates, merge_groups)

    exclude_cells = result.get("exclude_cell_ids") or []
    filtered_cells, cells_ok = _filter_grid_cells(grid_cells, exclude_cells)
    notes["cell_filter_accepted"] = cells_ok

    if cells_ok and labels_floor and len(filtered_cells) >= len(labels_floor) * 0.5:
        regen = merge_grid_cells_by_label(
            filtered_cells,
            labels_floor,
            msp,
            frame_layers,
            bounds_y=floor_bounds_y,
            min_area_m2=min_llm_area,
            area_to_m2_factor=area_to_m2_factor,
            id_prefix="SLAB",
        )
        if regen:
            area_regen = sum(c.area_m2 for c in regen)
            area_base = sum(c.area_m2 for c in candidates)
            if area_regen >= area_base * 0.92:
                candidates = _filter_merged_slabs(
                    regen, exclude_slabs, min_llm_area
                )
                notes["regenerated_from_cells"] = True

    if not candidates:
        notes["status"] = "empty_after_filter"
        return base, notes

    notes["status"] = "ok"
    notes["output_slab_count"] = len(candidates)
    notes["output_area_m2"] = round(sum(c.area_m2 for c in candidates), 3)
    return candidates, notes


def refine_slabs_with_deepseek(
    msp,
    *,
    drawing_name: str,
    structural_layers: tuple[str, ...],
    annotation_layers: tuple[str, ...],
    label_layers: tuple[str, ...],
    frame_layers: tuple[str, ...],
    grid_cells: list[SlabCandidate],
    merged_slabs: list[SlabCandidate] | None,
    floor_bounds_y: tuple[float, float] | None,
    frame_line_count: dict[str, int],
    exclusion_area_m2: float | None,
    geometric_notes: dict[str, Any],
    area_to_m2_factor: float,
    min_area_m2: float,
    deepseek_model: str,
    deepseek_base_url: str,
    thk_labels_total: int = 0,
) -> tuple[list[SlabCandidate], dict[str, Any]]:
    """
    DeepSeek validates merged slabs; geometry recomputes quantities.
    Falls back to geometric merge if LLM over-excludes or fails.
    """
    base = merged_slabs or []
    if not base:
        return [], {"status": "no_merged_slabs"}

    thk_all = extract_thk_labels(msp, label_layers)
    labels_floor = _labels_in_band(thk_all, floor_bounds_y)
    void_ann = collect_void_annotations(
        msp, annotation_layers, floor_bounds_y
    )
    layers = summarize_layers(msp)

    ctx = build_slab_reasoning_context(
        drawing_name=drawing_name,
        structural_layers=structural_layers,
        frame_line_count=frame_line_count,
        floor_bounds_y=floor_bounds_y,
        thk_labels=thk_all,
        grid_cells=grid_cells[:120],
        merged_slabs=base,
        void_annotations=void_ann,
        layer_summary=layers,
        exclusion_area_m2=exclusion_area_m2,
        geometric_notes=geometric_notes,
    )
    ctx["note"] = (
        "grid_cells truncated to 120 in prompt; full merge uses all cells server-side."
    )

    user_msg = (
        "Validate merged slab list. Keep almost all slabs. "
        "Only exclude clear non-slab (void-adjacent, <3m² artifacts). "
        "Return JSON only.\n\n"
        f"{json.dumps(ctx, separators=(',', ':'))}"
    )

    llm_notes: dict[str, Any] = {
        "model_requested": deepseek_model,
        "merged_slabs_sent": len(base),
        "grid_cells_total": len(grid_cells),
        "status": "pending",
    }

    if deepseek_model == "auto":
        models_to_try = [
            resolve_model("auto", prefer_reasoner=False),
            resolve_model("auto", prefer_reasoner=True),
        ]
    else:
        models_to_try = [resolve_model(deepseek_model, prefer_reasoner=False)]

    last_notes: dict[str, Any] = llm_notes
    for attempt, model_used in enumerate(models_to_try):
        llm_notes["model"] = model_used
        llm_notes["attempt"] = attempt + 1
        try:
            result = chat_json(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                model=model_used,
                base_url=deepseek_base_url,
            )
        except DeepSeekError as exc:
            logger.warning("DeepSeek attempt %s failed: %s", attempt + 1, exc)
            llm_notes["status"] = "error"
            llm_notes["error"] = str(exc)
            last_notes = llm_notes
            if attempt == 0 and deepseek_model == "auto":
                continue
            return base, llm_notes

        llm_notes["raw"] = result
        llm_notes["confidence"] = result.get("confidence")
        llm_notes["evidence"] = result.get("evidence", [])
        llm_notes["reasoning"] = result.get("reasoning", "")

        candidates, apply_notes = _apply_llm_result(
            base,
            grid_cells,
            labels_floor,
            result,
            void_ann,
            msp=msp,
            frame_layers=frame_layers,
            floor_bounds_y=floor_bounds_y,
            min_area_m2=min_area_m2,
            area_to_m2_factor=area_to_m2_factor,
        )
        llm_notes.update(apply_notes)
        last_notes = llm_notes

        if llm_notes.get("status") == "ok":
            return candidates, llm_notes

        if (
            llm_notes.get("status") in _RETRYABLE
            and attempt < len(models_to_try) - 1
        ):
            llm_notes["retry_with"] = models_to_try[attempt + 1]
            continue
        break

    return base, last_notes
