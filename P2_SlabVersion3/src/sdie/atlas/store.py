from __future__ import annotations

import json
from pathlib import Path

from sdie.atlas.schema import AtlasSample


def default_atlas_path() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "atlas" / "component_atlas.json"


def load_atlas(path: Path | None = None) -> list[AtlasSample]:
    atlas_path = path or default_atlas_path()
    if not atlas_path.exists():
        return []
    data = json.loads(atlas_path.read_text(encoding="utf-8"))
    samples = data.get("samples", data if isinstance(data, list) else [])
    return [AtlasSample.from_dict(s) for s in samples]


def save_atlas(samples: list[AtlasSample], path: Path | None = None) -> Path:
    atlas_path = path or default_atlas_path()
    atlas_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "project_id": "INIZIO",
        "version": "3.3",
        "sample_count": len(samples),
        "samples": [s.to_dict() for s in samples],
    }
    atlas_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return atlas_path
