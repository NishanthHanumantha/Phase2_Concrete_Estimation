from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_ENV_LOADED = False


def _candidate_env_files() -> list[Path]:
    here = Path(__file__).resolve()
    # .../P2_SlabVersion1/src/sdie/reasoning/env.py
    pkg_root = here.parents[3]
    repo_root = here.parents[4]
    return [
        pkg_root / ".env",
        repo_root / ".env",
        Path.cwd() / ".env",
        Path.cwd().parent / ".env",
    ]


def load_project_env() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    for path in _candidate_env_files():
        if path.is_file():
            load_dotenv(path, override=False)
    _ENV_LOADED = True


def get_deepseek_api_key() -> str | None:
    load_project_env()
    key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_KEY")
    if key:
        return key.strip()
    return None
