"""Generic inference — teach per project, classify from merged knowledge + drawing."""
from __future__ import annotations

GENERIC_PROJECT_IDS: frozenset[str] = frozenset({"GENERIC", "AUTO", "*", ""})


def is_generic_project(project_id: str | None) -> bool:
    """True when inference should use all teach corpora, not one project_id."""
    return (project_id or "GENERIC").strip().upper() in GENERIC_PROJECT_IDS


def atlas_project_filter(project_id: str | None) -> str | None:
    """Return project_id for atlas filter, or None to load all teach samples."""
    return None if is_generic_project(project_id) else project_id
