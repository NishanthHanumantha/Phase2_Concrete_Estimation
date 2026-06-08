"""Revised Project Knowledge paths (INIZIO authoritative teach corpus)."""
from __future__ import annotations

from pathlib import Path

REVISED_KNOWLEDGE_ROOT = "Revised Project Knowledge"
REVISED_TAGGED_DIR_REL = f"{REVISED_KNOWLEDGE_ROOT}/Tagged files"
REVISED_RAW_DIR_REL = f"{REVISED_KNOWLEDGE_ROOT}/Raw File"

INIZIO_TAGGED_DXFS: dict[str, str] = {
    "slab": f"{REVISED_TAGGED_DIR_REL}/Inizio Slab with tag_Revised1.dxf",
    "beam": f"{REVISED_TAGGED_DIR_REL}/Inizio - Beam with tag_Revised1.dxf",
    "column": f"{REVISED_TAGGED_DIR_REL}/Inizio - Colum with tag_Revised1.dxf",
    "shearwall": f"{REVISED_TAGGED_DIR_REL}/Inizio - Shearwall with tag_Revised1.dxf",
}

INIZIO_RAW_DXF_REL = f"{REVISED_RAW_DIR_REL}/Inizio - Slab beam_Raw_Revised1.dxf"


def default_project_root() -> Path:
    """P2_SlabVersion6 package root (parent of src/)."""
    return Path(__file__).resolve().parents[2]


def resolve_manifest_dxf_path(project_root: Path, rel_path: str) -> Path:
    """Resolve a manifest-relative DXF path against project root."""
    rel = rel_path.replace("\\", "/")
    candidates = [
        project_root / rel,
        project_root / "Data Source" / rel,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return (project_root / rel).resolve()


def inizio_raw_dxf_path(project_root: Path | None = None) -> Path:
    root = project_root or default_project_root()
    return resolve_manifest_dxf_path(root, INIZIO_RAW_DXF_REL)
