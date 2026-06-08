# Data Source — project inputs for SDIE v4

## Folder layout (your setup)

```
Data Source/
├── projects_manifest.json     ← links projects, DXFs, and Excel workbooks
├── Project1 - Inizio/         ← tagged + raw DXF drawings
├── Project2 - TrustOffice/
├── Project3 - Manohar/
└── Ground Truths/
    ├── Project1 - Inizio/
    │   └── Inizio - Slab beam.xlsx
    ├── Project2 - TrustOffice/
    │   └── Trust office - slab & Beam.xlsx
    └── Project3 - Manohar/
        └── Manohar Slab & Beam.xlsx
```

| Input | Location | Used for |
|-------|----------|----------|
| **Tagged DXF** | `ProjectN - …/*.dxf` | Atlas samples, pipeline runs, layer learning |
| **Estimator Excel** | `Ground Truths/ProjectN - …/*.xlsx` | Ground truth totals, slab IDs, KB estimator mappings |
| **Manifest** | `projects_manifest.json` | Which DXF belongs to which project and Excel floor |

Excel files stay here — do not move them to `data/`. The import script copies extracted totals into `data/ground_truth/*.json`.

## Import into knowledge base

```powershell
cd P2_SlabVersion4
$env:PYTHONPATH="src"
pip install openpyxl   # once

# Step 1: Excel → data/ground_truth/*.json
python scripts/ingest_estimator_workbooks.py

# Step 2 (optional): merge all project DXFs into atlas + rebuild KB
python scripts/ingest_estimator_workbooks.py --build-atlas --build-kb
```

Or separately:

```powershell
python scripts/build_atlas.py "Data Source/Project1 - Inizio/*.dxf" --project-id INIZIO --merge
python scripts/build_atlas.py "Data Source/Project2 - TrustOffice/*.dxf" --project-id TRUST_OFFICE --merge
python scripts/build_atlas.py "Data Source/Project3 - Manohar/*.dxf" --project-id MANOHAR --merge
python scripts/build_knowledge_base.py
```

## Run pipeline on a drawing

```powershell
python scripts/run_pipeline.py "Data Source/Project1 - Inizio/Inizio_B2_LayerTest1.dxf" `
  -o "Output/Project1" --project-id INIZIO --mode auto --layers S-BEAM --min-area 0.4
```

## Adding a new project

1. Create `Project4 - Name/` with DXFs.
2. Add Excel under `Ground Truths/Project4 - Name/`.
3. Add an entry to `projects_manifest.json`.
4. Run `ingest_estimator_workbooks.py --build-atlas --build-kb`.

## Note on duplicate folders

`TrustOffice/` and `Project2 - Manohar/` are legacy copies — the manifest uses `Project2 - TrustOffice` and `Project3 - Manohar` only.
