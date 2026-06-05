# P2_SlabVersion4 — Import manifest

Copied from `P2_SlabVersion3` on 2026-06-05.

## From V3 (included)

- `src/sdie/` — full package including v3 modules
- `scripts/` — pipeline, atlas, compare, analyze
- `docs/` — guides (update for v4 as work proceeds)
- `data/ground_truth/`, `data/atlas/`, `data/audits/`
- `data/knowledge_base/` — **v4 RAG corpus** (generated)
- `tests/`
- `requirements.txt`
- `Data Source/` — Slab Test DXFs + Terrace/TrustOffice root DXFs

## v4 additions

| Module | Purpose |
|--------|---------|
| `src/sdie/rag/` | Knowledge base builder, store, retriever |
| `src/sdie/classification/rag_classifier.py` | RAG + DeepSeek-V3 classification |
| `src/sdie/semantic_model/` | Semantic building model alias |
| `scripts/build_knowledge_base.py` | Epic 1 CLI |
| `doc/Prompt_V4.docx` | V4 design authority |

## Not copied

- `Output/SlabTest_V3/` and other generated outputs (regenerate in V4)
- `.pytest_cache/`, `*.dwl`, `*.dwl2`

## DeepSeek

API key: `C:\Users\nishanth.h\Phase2_Concrete_Estimation\.env`
