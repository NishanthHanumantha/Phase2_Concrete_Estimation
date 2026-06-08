from __future__ import annotations

# V4 legacy weights (geometry + topology + graph + deepseek)
WEIGHTS = {
    "geometry": 0.35,
    "topology": 0.25,
    "graph": 0.20,
    "deepseek": 0.20,
}

# V5 multi-evidence weights (Prompt § multi-evidence engine)
V5_WEIGHTS = {
    "layer": 0.25,
    "geometry": 0.25,
    "topology": 0.20,
    "annotation": 0.15,
    "atlas": 0.10,
    "knowledge_base": 0.05,
}

V5_THRESHOLDS = {
    "auto_accept": 90.0,
    "warning": 75.0,
    "review": 75.0,
    "force_queue": 60.0,
}


def _clamp(score: float) -> float:
    return max(0.0, min(1.0, score))


def score_confidence(
    *,
    geometry_score: float,
    topology_score: float,
    graph_score: float,
    deepseek_score: float,
) -> dict[str, float]:
    """V4 confidence framework — weighted 0–100%."""
    g = _clamp(geometry_score)
    t = _clamp(topology_score)
    gr = _clamp(graph_score)
    d = _clamp(deepseek_score)
    final = (
        WEIGHTS["geometry"] * g
        + WEIGHTS["topology"] * t
        + WEIGHTS["graph"] * gr
        + WEIGHTS["deepseek"] * d
    )
    return {
        "geometry": round(g * 100, 2),
        "topology": round(t * 100, 2),
        "graph": round(gr * 100, 2),
        "deepseek": round(d * 100, 2),
        "final": round(final * 100, 2),
        "weights": WEIGHTS,
    }


def score_v5_confidence(
    *,
    layer_score: float,
    geometry_score: float,
    topology_score: float,
    annotation_score: float,
    atlas_score: float,
    kb_score: float,
) -> dict[str, float | dict | str | bool]:
    """V5 estimator-style multi-evidence confidence (0–100%)."""
    scores = {
        "layer_match": round(_clamp(layer_score) * 100, 2),
        "geometry_match": round(_clamp(geometry_score) * 100, 2),
        "topology_match": round(_clamp(topology_score) * 100, 2),
        "annotation_match": round(_clamp(annotation_score) * 100, 2),
        "atlas_match": round(_clamp(atlas_score) * 100, 2),
        "kb_match": round(_clamp(kb_score) * 100, 2),
    }
    final = (
        V5_WEIGHTS["layer"] * _clamp(layer_score)
        + V5_WEIGHTS["geometry"] * _clamp(geometry_score)
        + V5_WEIGHTS["topology"] * _clamp(topology_score)
        + V5_WEIGHTS["annotation"] * _clamp(annotation_score)
        + V5_WEIGHTS["atlas"] * _clamp(atlas_score)
        + V5_WEIGHTS["knowledge_base"] * _clamp(kb_score)
    )
    final_pct = round(final * 100, 2)
    if final_pct >= V5_THRESHOLDS["auto_accept"]:
        status = "auto_accept"
        review_required = False
    elif final_pct >= V5_THRESHOLDS["warning"]:
        status = "warning"
        review_required = False
    elif final_pct >= V5_THRESHOLDS["force_queue"]:
        status = "review"
        review_required = True
    else:
        status = "force_queue"
        review_required = True

    return {
        "evidence": scores,
        "final": final_pct,
        "weights": V5_WEIGHTS,
        "status": status,
        "review_required": review_required,
    }


def infer_v5_evidence_from_baseline(comp) -> dict[str, float]:
    """Derive 0–1 evidence scores from rule baseline before DeepSeek."""
    layer_s = 0.5
    if any(e.startswith(("hard_layer:", "layer_profile:", "layer_hint:")) for e in comp.evidence):
        layer_s = 0.9
    elif comp.layer:
        layer_s = 0.6

    geo = comp.geometry_features or {}
    geometry_s = 0.5
    if any(e.startswith("geometry:") for e in comp.evidence):
        geometry_s = 0.85
    elif geo.get("aspect_ratio"):
        ar = geo["aspect_ratio"]
        if ar >= 4:
            geometry_s = 0.75
        elif ar >= 2:
            geometry_s = 0.65

    topo = comp.graph_features or {}
    topology_s = 0.5
    if topo.get("connected_columns", 0) > 0 or topo.get("connected_beams", 0) > 0:
        topology_s = 0.75
    if topo.get("neighbor_count", 0) >= 3:
        topology_s = max(topology_s, 0.7)

    ann = comp.annotation_features or {}
    annotation_s = 0.4
    if ann.get("has_thk") or ann.get("has_beam_tag") or ann.get("void_keyword"):
        annotation_s = 0.9
    elif comp.annotation_text:
        annotation_s = 0.6

    atlas_s = 0.5 if any(e.startswith("atlas_match:") for e in comp.evidence) else 0.35
    kb_s = 0.4

    return {
        "layer": layer_s,
        "geometry": geometry_s,
        "topology": topology_s,
        "annotation": annotation_s,
        "atlas": atlas_s,
        "knowledge_base": kb_s,
    }
