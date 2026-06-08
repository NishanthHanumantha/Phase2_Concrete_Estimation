from __future__ import annotations

import json
from pathlib import Path

from sdie.rag.schema import StructuralKnowledgeBase


def default_kb_path() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "knowledge_base" / "structural_kb.json"


def load_knowledge_base(path: Path | None = None) -> StructuralKnowledgeBase:
    kb_path = path or default_kb_path()
    if not kb_path.exists():
        return StructuralKnowledgeBase()
    data = json.loads(kb_path.read_text(encoding="utf-8"))
    return StructuralKnowledgeBase.from_dict(data)


def save_knowledge_base(kb: StructuralKnowledgeBase, path: Path | None = None) -> Path:
    kb_path = path or default_kb_path()
    kb_path.parent.mkdir(parents=True, exist_ok=True)
    kb_path.write_text(json.dumps(kb.to_dict(), indent=2), encoding="utf-8")
    return kb_path
