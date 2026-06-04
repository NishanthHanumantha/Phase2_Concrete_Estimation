# SDIE — Pipeline Flowcharts

Mermaid diagrams render in Cursor’s Markdown preview (open this file → preview).

**Related:** [01_SIMPLE_OVERVIEW.md](./01_SIMPLE_OVERVIEW.md) · [02_ARCHITECTURE.md](./02_ARCHITECTURE.md)

---

## 1. End-to-end pipeline

```mermaid
flowchart TB
    subgraph INPUT
        DXF[Consultant DXF file]
        CFG[PipelineConfig / CLI args]
    end

    subgraph INGESTION
        LOAD[load_drawing]
        META[DrawingMeta: units, m² factor, extents]
        THK0[extract_thk_labels + default note]
    end

    subgraph FLOOR
        FZ[resolve_floor_zone]
        FZOUT["bounds_y (grid)\nlabel_bounds_y (tags)"]
    end

    subgraph DETECT
        GRID[detect_beam_grid_slabs]
        EXCL[build_exclusion_catalog]
        MERGE[detect_label_merged_slabs]
        REG[detect_closed_regions]
        BF[detect_beam_frame_slab]
    end

    subgraph OPTIONAL
        LLM{--llm enabled?}
        DS[refine_slabs_with_deepseek]
    end

    subgraph QTY
        THK[nearest_thickness_mm per slab]
        CALC[compute_slab_quantity]
    end

    subgraph OUTPUT
        JSON[results.json]
        OVL[overlay.svg + .html]
        SUM[summary.txt]
    end

    DXF --> LOAD
    CFG --> LOAD
    LOAD --> META
    LOAD --> THK0
    THK0 --> FZ
    FZ --> FZOUT
    FZOUT --> EXCL
    EXCL --> GRID
    GRID --> MERGE
    MERGE --> LLM
    LLM -->|yes| DS
    LLM -->|no| THK
    DS --> THK
    MERGE -->|no merge| THK
    GRID -->|fallback| REG
    REG -->|fallback| BF
    BF --> THK
    THK --> CALC
    CALC --> JSON
    CALC --> OVL
    CALC --> SUM
```

---

## 2. Auto mode — strategy selection

```mermaid
flowchart TD
    START([run_pipeline auto]) --> COUNT[count orthogonal frame lines]
    COUNT --> GRIDOK{H ≥ 80 and V ≥ 60\nor mode = beam_grid?}

    GRIDOK -->|yes| ZONE[resolve_floor_zone cluster]
    ZONE --> EX[apply exclusions]
    EX --> CELLS[beam grid cells]
    CELLS --> LABELS{THK labels in floor\n≥ merge threshold?}

    LABELS -->|yes| LM[label_merged_bay]
    LABELS -->|no| RAW[beam_grid_bay cells as slabs]

    LM --> LLM2{--llm?}
    LLM2 -->|yes| REFINE[DeepSeek refine]
    LLM2 -->|no| DONE1([candidates ready])
    REFINE --> DONE1
    RAW --> DONE1

    GRIDOK -->|no| REGTRY[region polygonize]
    REGTRY --> REGOK{valid small regions?}
    REGOK -->|yes| DONE2([region_polygonize])
    REGOK -->|no| BFRAME[beam_frame_bbox]
    BFRAME --> DONE3([candidates ready])

    DONE1 --> QTY[thickness + quantities]
    DONE2 --> QTY
    DONE3 --> QTY
```

---

## 3. Floor zone (cluster mode)

```mermaid
flowchart LR
    subgraph LABELS
        THK[*THK positions on A-FLOR-IDEN]
    end

    subgraph CLUSTER
        C1[Y-cluster labels\nadaptive gap]
        C2[Score clusters\nlabels + beam lines]
        C3[Merge satellite\nsmall tag groups]
    end

    subgraph SUBPANEL
        S1[Split primary cluster\nlarge internal gaps]
        S2[Pick sub-panel\nmax beam density]
        S3[Stack cap on ymax\navoid duplicate plan tier]
    end

    subgraph BOUNDS
        LB[label_bounds_y\nwide — 73 tags]
        GB[bounds_y\ngrid — area takeoff]
    end

    THK --> C1 --> C2 --> C3
    C3 --> S1 --> S2 --> S3
    S3 --> GB
    C3 --> LB
```

---

## 4. Beam grid → one slab per THK tag

```mermaid
flowchart TD
    BEAMS[Beam centerlines S-BEAM / S_FRAMES] --> AXES[Cluster H and V axes]
    AXES --> CELLS[Rectangular bay per cell]
    CELLS --> EXP[Expand face ~55mm\nclear span]
    EXP --> SUB[Subtract exclusion union]
    SUB --> VOID{Centroid near\nSTAIR/LIFT text?}
    VOID -->|yes| DROP[Skip cell]
    VOID -->|no| KEEP[Grid cell with area_m2]

    KEEP --> ASSIGN[Assign cell to nearest *THK label]
    ASSIGN --> GROUP[Group cells per label]
    GROUP --> UNION[Union polygons for display]
    GROUP --> SUM[Sum cell areas for BOQ]
    SUM --> SLAB[One SlabCandidate per label]
```

---

## 5. Exclusions vs slab area

```mermaid
flowchart LR
    subgraph SUBTRACT_FROM_AREA
        COL[Column layers]
        SUNK[Sunk slab hatch]
    end

    subgraph SKIP_CELL
        VOID[Void keywords\nSTAIR LIFT RAMP...]
    end

    subgraph VISUAL_ONLY
        BEAM[Beam footprint\noverlay red]
    end

    RAW[Raw grid cell] --> COL
    RAW --> SUNK
    COL --> NET[Net slab polygon]
    SUNK --> NET
    RAW --> VOID
    VOID --> NET
    BEAM -.->|not subtracted| NET
```

---

## 6. Quantity and export

```mermaid
flowchart LR
    SLAB[SlabCandidate list] --> T{thickness_mm\non candidate?}
    T -->|yes| USE[Use label thickness]
    T -->|no| NEAR[Nearest *THK or default note]
    USE --> Q[area × thk → m³]
    NEAR --> Q
    Q --> JSON[Slab JSON + totals]
    Q --> SVG[Overlay blue/red]
```

---

## 7. Optional DeepSeek path

```mermaid
flowchart TD
    GEO[Geometric label_merged slabs] --> CTX[Build context:\nmerged slabs, voids, floor_zone]
    CTX --> CHAT[deepseek-chat JSON]
    CHAT --> OK{status ok?}
    OK -->|no| RETRY[deepseek-reasoner retry]
    RETRY --> APPLY
    OK -->|yes| APPLY[Apply exclude list\n+ area guard ±3%]
    APPLY --> OUT[label_merged_bay_llm]
    APPLY -->|rejected| GEO
```

---

## 8. CLI entry point

```mermaid
flowchart LR
    USER[Engineer] --> CLI[scripts/run_pipeline.py]
    CLI --> PIPE[src/sdie/pipeline.py run_pipeline]
    PIPE --> OUTDIR[Output/Slab Test/]
    USER2[Engineer] --> CMP[compare_to_ground_truth.py]
    CMP --> OUTDIR
```

**Example:**

```text
python scripts/run_pipeline.py  "Data Source/.../Drawing.dxf"  -o "Output/Slab Test"  --mode auto  --layers S-BEAM  --min-area 0.4
```

---

## 9. Reading order

| # | Document | Best for |
|---|----------|----------|
| 1 | [01_SIMPLE_OVERVIEW.md](./01_SIMPLE_OVERVIEW.md) | First read — concepts |
| 2 | [02_ARCHITECTURE.md](./02_ARCHITECTURE.md) | Modules and design rules |
| 3 | **This file** | Visual flow |
| 4 | [NEW_DRAWING_GUIDE.md](./NEW_DRAWING_GUIDE.md) | Next drawing test |
