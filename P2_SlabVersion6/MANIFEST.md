# P2_SlabVersion6 file manifest

Copied from `P2_Slabversion5` — lean runtime only (~65 MB atlas + KB + code + test DXFs).

## V6-only additions

```
src/sdie/ingestion/layer_discovery.py   # drawing scan + project profile boost
docs/Prompt_extracted_V5_docx.txt       # verbatim extract from V5 docx
docs/Prompt_extracted_V6.txt            # revised prompt (docx + V5/V6 implementation)
docs/Prompt_extracted_V4.txt            # V4 archive (from V5 copy)
```

## Runtime-critical

```
src/sdie/
data/atlas/component_atlas.json
data/knowledge_base/structural_kb.json
data/layer_profiles.json
requirements.txt
scripts/run_pipeline.py
```

## Bundled inputs

```
Data Source/TestInput/TrustOffice_FF_LayerTest_RAG.dxf
Data Source/TestInput/Inizio_B2_LayerTest_V5.dxf
Data Source/Ground Truths/TestGT/TrustOffice_FF_ExpectedOutput.xlsx
Data Source/projects_manifest.json
data/ground_truth/*.json
```

## INIZIO Revised Project Knowledge (authoritative teach corpus)

```
Revised Project Knowledge/Tagged files/Inizio Slab with tag_Revised1.dxf
Revised Project Knowledge/Tagged files/Inizio - Beam with tag_Revised1.dxf
Revised Project Knowledge/Tagged files/Inizio - Colum with tag_Revised1.dxf
Revised Project Knowledge/Tagged files/Inizio - Shearwall with tag_Revised1.dxf
Revised Project Knowledge/Raw File/Inizio - Slab beam_Raw_Revised1.dxf
```

## Omitted (regenerate or copy from V5/V4)

```
Output/**           (all prior test runs)
SDIE Version 5 PDF/docx
Data Source/Ground Truths/Inizio_B2_GT/  (large tagged DXFs)
Data Source/Project1-3/                 (teach corpus)
```
