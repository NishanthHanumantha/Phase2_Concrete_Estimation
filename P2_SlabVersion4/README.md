# P2_SlabVersion4 — SDIE v4 Knowledge-Driven Structural Intelligence

**Active development.** Spec: `doc/Prompt_V4.docx` · `doc/Prompt_extracted.txt`  
**Frozen baselines:** `../P2_SlabVersion1/`, `../P2_SlabVersion2/`, `../P2_SlabVersion3/`

## v4 change vs v3

| v3.3 | v4 |
|------|-----|
| Rule + optional DeepSeek | **RAG Knowledge Base + DeepSeek-V3** (default) |
| Atlas lookup only | Atlas + layer/annotation/estimator mappings |
| Geometry-first fallback | Knowledge-driven; teach estimator patterns |

**Principle:** Structural understanding before quantities. DeepSeek classifies; code calculates.

## Setup

```powershell
cd P2_SlabVersion4
pip install -r requirements.txt
$env:PYTHONPATH="src"
```

**DeepSeek:** `DEEPSEEK_API_KEY` in `../.env` (repo root `Phase2_Concrete_Estimation/.env`).

## Build knowledge base (first time)

```powershell
python scripts/build_knowledge_base.py
python scripts/build_atlas.py "Data Source/Slab Test/Inizio_B2_LayerTest1.dxf" --merge
```

## Run

```powershell
python scripts/run_pipeline.py "Data Source/Slab Test/Inizio_B2_LayerTest1.dxf" `
  -o "Output/Slab Test" --mode auto --layers S-BEAM --min-area 0.4
```

Flags: `--no-deepseek` (rules only), `--v3-semantic` (v3 classifier), `--legacy-geometry` (pre-v3).

## Documentation

Start at [docs/README.md](docs/README.md). V4 authority: [doc/Prompt_extracted.txt](doc/Prompt_extracted.txt).
