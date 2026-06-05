# SDIE v3.3 — Pipeline Flowcharts

Mermaid diagrams render in Cursor Markdown preview (`Ctrl+Shift+V`).

---

## 1. v3.3 semantic pipeline (default)

```mermaid
flowchart TB
    subgraph INPUT
        DXF[Consultant DXF]
        CFG[PipelineConfig]
        ATLAS[Component Atlas JSON]
    end

    subgraph INGEST
        LOAD[load_drawing]
        FZ[resolve_floor_zone]
        EXTRACT[extract_drawing_entities]
    end

    subgraph SEMANTIC
        CLASS[classify_entities]
        LLM_C{--component-llm?}
        DS_C[refine_ambiguous_components]
        GRAPH[build_structural_graph]
        MODEL[build_semantic_model]
    end

    subgraph SLAB
        SI[detect_slabs_after_classification]
        LLM_S{--llm?}
        DS_S[refine_slabs_with_deepseek]
    end

    subgraph QTY
        THK[nearest_thickness_mm]
        CALC[compute_slab_quantity]
        BENCH[compute_benchmark_report]
    end

    subgraph OUTPUT
        JSON[results.json]
        BM[building_model.json]
        OVL[overlay.html]
    end

    DXF --> LOAD
    CFG --> LOAD
    ATLAS --> CLASS
    LOAD --> FZ
    LOAD --> EXTRACT
    FZ --> EXTRACT
    EXTRACT --> CLASS
    CLASS --> LLM_C
    LLM_C -->|yes| DS_C
    LLM_C -->|no| GRAPH
    DS_C --> GRAPH
    GRAPH --> SI
    SI --> LLM_S
    LLM_S -->|yes| DS_S
    LLM_S -->|no| THK
    DS_S --> THK
    THK --> CALC
    CALC --> MODEL
    CALC --> BENCH
    MODEL --> JSON
    MODEL --> BM
    CALC --> OVL
```

---

## 2. Component classification flow

```mermaid
flowchart LR
    ENT[DrawingEntity] --> ANN[Annotation features]
    ENT --> GEO[Geometry features]
    ENT --> LAYER[Layer hints]
    ATLAS[Atlas lookup] --> VOTE[Atlas vote]
    ANN --> RULE[Rule classifier]
    GEO --> RULE
    LAYER --> RULE
    VOTE --> MERGE[Best type + confidence]
    RULE --> MERGE
    MERGE --> CONF[score_confidence]
```

---

## 3. Slab Intelligence (Epic 5)

```mermaid
flowchart TB
    NON[Classified non-slab components]
    GEO_EX[Geometric exclusion catalog]
    MERGE[Merge exclusion unions]
    GRID[Beam grid bays]
    THK[THK label merge]
    SLABS[Slab candidates]

    NON --> MERGE
    GEO_EX --> MERGE
    MERGE --> GRID
    GRID --> THK
    THK --> SLABS
```

---

## 4. Legacy geometry-first path

Use `--legacy-geometry` to skip semantic stages and run the v2 `pipeline.py` body directly.

```mermaid
flowchart LR
    DXF --> GRID[beam_grid]
    GRID --> MERGE[THK merge]
    MERGE --> QTY[quantity]
```

---

## 5. Atlas builder (Epic 1)

```mermaid
flowchart LR
    TAG_DXF[Tagged DXF] --> BUILD[build_atlas_samples_from_dxf]
    BUILD --> JSON[data/atlas/component_atlas.json]
    JSON --> CLASS[classify_entities lookup]
```

---

## Related

- [01_SIMPLE_OVERVIEW.md](./01_SIMPLE_OVERVIEW.md)  
- [02_ARCHITECTURE.md](./02_ARCHITECTURE.md)  
- [04_CODE_GUIDE.md](./04_CODE_GUIDE.md)
