from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from sdie.config import PipelineConfig
from sdie.pipeline import run_pipeline

app = FastAPI(
    title="SDIE v3.3 API",
    description="Structural Drawing Intelligence Engine — Enterprise API",
    version="3.3.0",
)


class ProcessDrawingRequest(BaseModel):
    dxf_path: str
    output_dir: str = "Output/Slab Test"
    project_id: str = "INIZIO"
    layers: list[str] = ["S-BEAM"]
    min_area: float = 0.4
    llm: bool = False
    legacy_geometry: bool = False


@app.get("/health")
def health():
    return {"status": "ok", "engine": "SDIE", "version": "3.3.0"}


@app.post("/drawings/process")
def process_drawing(req: ProcessDrawingRequest):
    dxf = Path(req.dxf_path)
    if not dxf.exists():
        raise HTTPException(status_code=404, detail=f"DXF not found: {dxf}")
    out = Path(req.output_dir)
    config = PipelineConfig(
        project_id=req.project_id,
        structural_layers=tuple(req.layers),
        min_slab_area_m2=req.min_area,
        enable_deepseek_refinement=req.llm,
        use_semantic_pipeline=not req.legacy_geometry,
    )
    result = run_pipeline(dxf.resolve(), out.resolve(), config)
    return {
        "totals": result["totals"],
        "benchmark": result.get("benchmark"),
        "outputs": result.get("output_files"),
        "detection_notes": {
            k: result["detection_notes"].get(k)
            for k in (
                "pipeline",
                "component_type_counts",
                "selected",
                "classified_non_slab_count",
            )
            if k in result.get("detection_notes", {})
        },
    }


@app.get("/buildings/{stem}")
def get_building_model(stem: str, output_dir: str = "Output/Slab Test"):
    path = Path(output_dir) / f"{stem}_building_model.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Building model not found")
    return json.loads(path.read_text(encoding="utf-8"))
