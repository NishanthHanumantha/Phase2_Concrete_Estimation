from __future__ import annotations

from pathlib import Path

# Legacy regression sample — not part of estimator project corpus.
EXCLUDED_DXF_STEMS = frozenset({"Inizio_B2_LayerTest1"})


def is_tagged_atlas_dxf(path: Path) -> bool:
    """Tagged teaching DXFs only: *with tag*, no RAW, no excluded stems."""
    stem = path.stem
    if stem in EXCLUDED_DXF_STEMS:
        return False
    lower = path.name.lower()
    if "_raw" in lower or lower.endswith(" raw.dxf"):
        return False
    return "with tag" in lower


def select_atlas_dxfs(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.glob("*.dxf") if is_tagged_atlas_dxf(p))
