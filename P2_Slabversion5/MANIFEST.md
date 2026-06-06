# P2_SlabVersion5 file manifest

Copied from `P2_SlabVersion4` on session handoff. **~65 MB** runtime (atlas + KB + code + one test DXF).

## Runtime-critical

```
src/sdie/                          # entire package
data/atlas/component_atlas.json
data/knowledge_base/structural_kb.json
data/layer_profiles.json
requirements.txt
scripts/run_pipeline.py
```

## Validation & teach scripts

```
scripts/build_knowledge_base.py
scripts/build_layer_profiles.py
scripts/ingest_estimator_workbooks.py
scripts/evaluate_component_classification.py
scripts/verify_test_gt.py
scripts/teach_all_projects.py
scripts/build_atlas.py
scripts/analyze_dxf.py
scripts/compare_to_ground_truth.py
```

## Input data (bundled)

```
Data Source/TestInput/TrustOffice_FF_LayerTest_RAG.dxf
Data Source/Ground Truths/TestGT/TrustOffice_FF_ExpectedOutput.xlsx
Data Source/projects_manifest.json
data/ground_truth/*.json
```

## Not bundled — copy from V4 when needed

```
Data Source/Project1 - Inizio/
Data Source/Project2 - TrustOffice/
Data Source/Project3 - Manohar/
Data Source/Ground Truths/Project1 - Inizio/
Data Source/Ground Truths/Project2 - TrustOffice/
Data Source/Ground Truths/Project3 - Manohar/
```

## Environment

```
C:\Users\nishanth.h\Phase2_Concrete_Estimation\.env   # DEEPSEEK_API_KEY
```

`env.py` walks up to repo root (`Phase2_Concrete_Estimation`) — no `.env` inside V5.
