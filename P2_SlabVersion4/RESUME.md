# Resume here — P2_SlabVersion4 (SDIE v4)

**Active project:** `P2_SlabVersion4/`  
**Spec:** [doc/Prompt_extracted.txt](doc/Prompt_extracted.txt)  
**Frozen:** V1, V2, V3 — do not edit for new work

---

## Quick start

```powershell
cd C:\Users\nishanth.h\Phase2_Concrete_Estimation\P2_SlabVersion4
pip install -r requirements.txt
$env:PYTHONPATH="src"

python scripts/build_knowledge_base.py
python scripts/run_pipeline.py "Data Source/Slab Test/Inizio_B2_LayerTest1.dxf" `
  -o "Output/Slab Test" --mode auto --layers S-BEAM --min-area 0.4
```

DeepSeek: `DEEPSEEK_API_KEY` in `C:\Users\nishanth.h\Phase2_Concrete_Estimation\.env`

---

## v4 architecture

```
Raw DXF → entities → RAG retrieve → DeepSeek classify → graph → slab intelligence → quantities
```

**Do not** compare drawings to BOQ unless you provide `data/ground_truth/<stem>.json` for that drawing.

---

## Imported from V3

- Source, scripts, docs, atlas (1986 samples), ground truth, test DXFs
- Verification outputs **not** copied — regenerate in `Output/`

---

## v4 epics (from Prompt_V4)

| Epic | Status |
|------|--------|
| 1 Knowledge Base (RAG) | Implemented — `rag/`, `build_knowledge_base.py` |
| 2 Atlas Builder | From V3 — `build_atlas.py` |
| 3 DeepSeek Classification | Implemented — `rag_classifier.py` (default on) |
| 4–7 Graph, model, slab, quantity | From V3 pipeline |
| 8 Validation UI | Planned |

---

## Estimator project inputs (configured)

| Project | DXFs | Excel ground truth |
|---------|------|-------------------|
| Inizio | `Data Source/Project1 - Inizio/` | `Data Source/Ground Truths/Project1 - Inizio/` |
| Trust Office | `Data Source/Project2 - TrustOffice/` | `Data Source/Ground Truths/Project2 - TrustOffice/` |
| Manohar | `Data Source/Project3 - Manohar/` | `Data Source/Ground Truths/Project3 - Manohar/` |

Import: `python scripts/ingest_estimator_workbooks.py --build-atlas --build-kb`  
Details: [Data Source/README.md](Data%20Source/README.md)

## Next steps

1. Run ingest + rebuild KB (command above)
2. Run v4 on each project drawing; verify overlays
3. Tune RAG retrieval + DeepSeek prompts for misclassified non-slab regions
