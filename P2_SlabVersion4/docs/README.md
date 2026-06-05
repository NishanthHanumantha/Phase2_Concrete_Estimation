# SDIE v3.3 Documentation Index

**Architecture:** Structural Component Intelligence (semantics before geometry)  
**Authority:** [Prompt_extracted.txt](./Prompt_extracted.txt) (from SDIE v3.3 Enterprise Implementation Package)

| # | Document | What you get |
|---|----------|--------------|
| **1** | [01_SIMPLE_OVERVIEW.md](./01_SIMPLE_OVERVIEW.md) | Plain-language v3.3 explanation |
| **2** | [02_ARCHITECTURE.md](./02_ARCHITECTURE.md) | Modules, epics, component types |
| **3** | [03_PIPELINE_FLOW.md](./03_PIPELINE_FLOW.md) | Mermaid flowcharts (Markdown preview) |
| **4** | [04_CODE_GUIDE.md](./04_CODE_GUIDE.md) | Files, functions, where to edit |

### Also useful

| Document | Purpose |
|----------|---------|
| [MODEL_DESIGN.md](./MODEL_DESIGN.md) | v3.3 design spec + benchmark targets |
| [Prompt_extracted.txt](./Prompt_extracted.txt) | Full v3.3 implementation prompt |
| [SESSION_PROGRESS.md](./SESSION_PROGRESS.md) | Changelog and metrics |
| [NEW_DRAWING_GUIDE.md](./NEW_DRAWING_GUIDE.md) | New DXF workflow (atlas + semantic run) |

### Source package

| File | Purpose |
|------|---------|
| `SDIE v3.3 Enterprise Implementation Package.pdf` | Original PDF |
| `SDIE v3.3 Enterprise Implementation Package.docx` | Original Word |

### Quick commands

```powershell
cd P2_SlabVersion3
pip install -r requirements.txt
$env:PYTHONPATH="src"

# Build atlas (Epic 1)
python scripts/build_atlas.py "Data Source/Slab Test/Inizio_B2_LayerTest1.dxf" --merge

# Run semantic pipeline (default)
python scripts/run_pipeline.py "Data Source/Slab Test/Inizio_B2_LayerTest1.dxf" `
  -o "Output/Slab Test" --mode auto --layers S-BEAM --min-area 0.4
```
