"""In-memory job store for async pipeline runs."""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class PipelineJob:
    job_id: str
    status: str  # queued | running | completed | failed
    dxf_name: str
    output_dir: Path
    created_at: str
    message: str = ""
    totals: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    error: str | None = None


_lock = threading.Lock()
_jobs: dict[str, PipelineJob] = {}


def create_job(dxf_name: str, output_dir: Path) -> PipelineJob:
    job = PipelineJob(
        job_id=str(uuid.uuid4()),
        status="queued",
        dxf_name=dxf_name,
        output_dir=output_dir,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    with _lock:
        _jobs[job.job_id] = job
    return job


def get_job(job_id: str) -> PipelineJob | None:
    with _lock:
        return _jobs.get(job_id)


def update_job(job_id: str, **kwargs: Any) -> PipelineJob | None:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        for key, value in kwargs.items():
            if hasattr(job, key):
                setattr(job, key, value)
        return job


def job_to_dict(job: PipelineJob) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "status": job.status,
        "dxf_name": job.dxf_name,
        "created_at": job.created_at,
        "message": job.message,
        "totals": job.totals,
        "outputs": job.outputs,
        "assumptions": job.assumptions,
        "error": job.error,
    }
