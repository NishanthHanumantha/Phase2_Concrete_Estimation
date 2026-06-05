from __future__ import annotations

WEIGHTS = {
    "geometry": 0.35,
    "topology": 0.25,
    "graph": 0.20,
    "deepseek": 0.20,
}


def score_confidence(
    *,
    geometry_score: float,
    topology_score: float,
    graph_score: float,
    deepseek_score: float,
) -> dict[str, float]:
    """PART 11 confidence framework — weighted 0–100%."""
    g = max(0.0, min(1.0, geometry_score))
    t = max(0.0, min(1.0, topology_score))
    gr = max(0.0, min(1.0, graph_score))
    d = max(0.0, min(1.0, deepseek_score))
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
