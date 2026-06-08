"""Background pipeline runner for web jobs."""
from __future__ import annotations

import shutil
from pathlib import Path

from sdie.api.jobs import PipelineJob, update_job
from sdie.config import PipelineConfig
from sdie.pipeline import run_pipeline
from sdie.reasoning.env import get_deepseek_api_key
from sdie.validation.excel_export import export_results_to_excel


def _excel_path(output_dir: Path, stem: str) -> Path:
    return output_dir / f"{stem}_Beamquantities.xlsx"


def run_job_task(job: PipelineJob, dxf_path: Path) -> None:
    update_job(job.job_id, status="running", message="Running SDIE V6 pipeline…")
    deepseek_on = bool(get_deepseek_api_key())
    try:
        config = PipelineConfig(
            project_id="GENERIC",
            auto_discover_layers=True,
            use_semantic_pipeline=True,
            use_v4_pipeline=True,
            use_v5_pipeline=True,
            enable_rag_classification=True,
            enable_beam_quantities=True,
            enable_deepseek_component_classification=deepseek_on,
            show_progress=False,
        )
        result = run_pipeline(dxf_path, job.output_dir, config)

        stem = dxf_path.stem
        excel_dst = _excel_path(job.output_dir, stem)
        excel_src = result.get("output_files", {}).get("excel")
        if excel_src and Path(excel_src).exists():
            shutil.copy2(excel_src, excel_dst)
        else:
            export_results_to_excel(result, excel_dst)

        outputs = dict(result.get("output_files") or {})
        outputs["excel_beamquantities"] = str(excel_dst)

        update_job(
            job.job_id,
            status="completed",
            message="Estimation complete.",
            totals=result.get("totals") or {},
            outputs=outputs,
        )
    except Exception as exc:
        update_job(
            job.job_id,
            status="failed",
            message="Pipeline failed.",
            error=str(exc),
        )
