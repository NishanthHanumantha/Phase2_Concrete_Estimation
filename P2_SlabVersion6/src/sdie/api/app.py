"""SDIE V6 web API — DXF upload → slab + beam Excel quantities."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from sdie.api.jobs import create_job, get_job, job_to_dict
from sdie.api.runner import run_job_task

ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIR = ROOT / "frontend"
UPLOAD_ROOT = ROOT / "Output" / "web_jobs"
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="SDIE V6 Estimation API",
    description="Upload structural DXF → download slab & beam concrete quantities (Excel)",
    version="6.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if FRONTEND_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.is_file():
        return HTMLResponse("<h1>SDIE V6</h1><p>frontend/index.html not found.</p>")
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.get("/health")
def health():
    return {"status": "ok", "engine": "SDIE", "version": "6.0.0"}


@app.post("/api/estimate")
async def estimate_drawing(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    if not file.filename or not file.filename.lower().endswith(".dxf"):
        raise HTTPException(status_code=400, detail="Upload a .dxf file.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file.")

    job = create_job(file.filename, UPLOAD_ROOT / "placeholder")
    job_dir = UPLOAD_ROOT / job.job_id
    out_dir = job_dir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    job.output_dir = out_dir

    dxf_path = job_dir / Path(file.filename).name
    dxf_path.write_bytes(content)

    background_tasks.add_task(run_job_task, job, dxf_path)
    return {
        "job_id": job.job_id,
        "status": "queued",
        "dxf_name": file.filename,
        "poll_url": f"/api/jobs/{job.job_id}",
        "excel_url": f"/api/jobs/{job.job_id}/excel",
    }


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job_to_dict(job)


@app.get("/api/jobs/{job_id}/excel")
def download_excel(job_id: str):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status != "completed":
        raise HTTPException(status_code=409, detail=f"Job status: {job.status}")

    excel = job.outputs.get("excel_beamquantities") or job.outputs.get("excel")
    if not excel or not Path(excel).is_file():
        raise HTTPException(status_code=404, detail="Excel output not found.")
    return FileResponse(
        path=excel,
        filename=Path(excel).name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/api/jobs/{job_id}/overlay")
def download_overlay(job_id: str):
    job = get_job(job_id)
    if job is None or job.status != "completed":
        raise HTTPException(status_code=404, detail="Overlay not available.")
    html = job.outputs.get("overlay_html")
    if not html or not Path(html).is_file():
        raise HTTPException(status_code=404, detail="Overlay not found.")
    return FileResponse(path=html, filename=Path(html).name, media_type="text/html")


@app.get("/api/jobs/{job_id}/results")
def download_results_json(job_id: str):
    job = get_job(job_id)
    if job is None or job.status != "completed":
        raise HTTPException(status_code=404, detail="Results not available.")
    json_path = job.outputs.get("json")
    if not json_path or not Path(json_path).is_file():
        raise HTTPException(status_code=404, detail="JSON not found.")
    return json.loads(Path(json_path).read_text(encoding="utf-8"))
