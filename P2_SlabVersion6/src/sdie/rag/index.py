from __future__ import annotations

from collections import defaultdict

from sdie.atlas.schema import AtlasSample
from sdie.inference.generic import is_generic_project
from sdie.rag.schema import StructuralKnowledgeBase


class RagIndex:
    """Layer- and project-scoped indexes so retrieval avoids full-corpus scans."""

    def __init__(
        self,
        kb: StructuralKnowledgeBase,
        atlas: list[AtlasSample],
        project_id: str,
    ) -> None:
        self.project_id = project_id
        self._generic = is_generic_project(project_id)
        self.layer_knowledge_by_layer: dict[str, list] = defaultdict(list)
        for lk in kb.layer_knowledge:
            if not self._generic and lk.project_id not in (project_id, "GLOBAL"):
                continue
            self.layer_knowledge_by_layer[lk.layer].append(lk)

        self.patterns_by_type: dict[str, list[dict]] = defaultdict(list)
        for p in kb.pattern_knowledge:
            if not self._generic and p.get("project_id") not in (project_id, "GLOBAL"):
                continue
            ctype = p.get("component_type") or ""
            self.patterns_by_type[ctype].append(p)

        self.atlas_by_layer: dict[str, list[AtlasSample]] = defaultdict(list)
        for sample in atlas:
            if not self._generic and sample.project_id not in (project_id, "GLOBAL"):
                continue
            if sample.layer:
                self.atlas_by_layer[sample.layer].append(sample)

        if self._generic:
            self.estimator_mappings = list(kb.estimator_mappings)
        else:
            self.estimator_mappings = [
                m
                for m in kb.estimator_mappings
                if m.project_id in (project_id, "GLOBAL")
            ]
