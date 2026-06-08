# SDIE V6 — Model Flow

Structural Drawing Intelligence Engine: **teach from reference projects → infer on any drawing → quantify slabs and beams.**

---

## 1. End-to-end flow (single view)

```mermaid
flowchart TD
    classDef teach fill:#E8F4FD,stroke:#1A73E8,stroke-width:2px
    classDef infer fill:#E6F4EA,stroke:#34A853,stroke-width:2px
    classDef out fill:#FEF7E0,stroke:#FBBC04,stroke-width:2px

    subgraph TEACH["A · TEACH — offline, reference projects only"]
        T0[Tagged DXFs<br/>INIZIO · TRUST_OFFICE · MANOHAR]:::teach
        T1[Component Atlas]:::teach
        T2[Layer Profiles]:::teach
        T3[Structural Knowledge Base]:::teach
        T0 --> T1 & T2 & T3
    end

    subgraph INFER["B · INFER — runtime, any raw DXF · project-id GENERIC"]
        I0[Input DXF]:::infer
        I1[Prepare drawing<br/>layers · floor zone · entities]:::infer
        I2[Classify components<br/>rules · graph · DeepSeek]:::infer
        I3[Quantify<br/>beams · slabs · concrete]:::infer
        I4[Export results]:::infer
        I0 --> I1 --> I2 --> I3 --> I4
    end

    T1 & T2 & T3 --> I1
    T1 & T2 & T3 --> I2

    I4 --> O1[JSON + building model]:::out
    I4 --> O2[Overlay HTML / SVG]:::out
    I4 --> O3[Excel + review queue]:::out
```

---

## 2. Teach pipeline (Phase A)

```mermaid
flowchart LR
    M[projects_manifest.json] --> D[Tagged DXF per project]
    D --> S1[build_atlas.py]
    D --> S2[build_layer_profiles.py]
    D --> S3[RAG / KB builder]
    S1 --> A[(component_atlas.json)]
    S2 --> P[(layer_profiles.json)]
    S3 --> K[(structural_kb.json)]
```

| Artifact | What it stores |
|----------|----------------|
| **Atlas** | Labelled geometry samples per layer and entity type |
| **Layer profiles** | Hard globals, soft layers, per-project rules + confidence |
| **Knowledge base** | Layer rules, annotation patterns, estimator mappings |

---

## 3. Inference pipeline (Phase B) — step by step

```mermaid
flowchart TD
    START([run_pipeline.py]) --> S1

    S1["① Load DXF<br/>units · scale · extents"]
    S2["② Auto-discover layers<br/>frame · annotation · void · column"]
    S3["③ Resolve floor zone<br/>THK label clusters"]
    S4["④ Load teach artifacts<br/>Atlas + KB · GENERIC = all projects"]
    S5["⑤ Extract entities<br/>structural · cutout · hatch void · columns"]
    S6["⑥ Classify — V5 engine"]
    S7["⑦ Beam quantities<br/>length × section → concrete m³"]
    S8["⑧ Build structural graph<br/>nodes + topology edges"]
    S9["⑨ Slab detection<br/>exclusions → beam grid → bays"]
    S10["⑩ Slab quantities<br/>area × THK → concrete m³"]
    S11["⑪ Export<br/>JSON · overlay · Excel · review queue"]

    START --> S1 --> S2 --> S3 --> S4 --> S5 --> S6
    S6 --> S7 --> S8 --> S9 --> S10 --> S11
```

---

## 4. Classification engine (V5)

```mermaid
flowchart TD
    E[Entity] --> R{Rule baseline}
    R -->|Hard layer| L1[Locked type<br/>Opening · Column · Beam]
    R -->|Soft layer| L2[Geometry heuristics<br/>beam line · column · wall]
    R -->|Teach rule| L3[Best layer profile<br/>cross-project if GENERIC]
    L1 & L2 & L3 --> G[Structural graph topology]
    G --> C[V5 confidence score]
    C --> D{Below 75%?}
    D -->|Yes| DS[DeepSeek + RAG<br/>atlas · KB · neighbours]
    D -->|No| F[Final type]
    DS --> F
```

**Excluded from slab area:** Shear Wall, Structural Wall, Lift Core, Stair Core, Shaft, Opening.

---

## 5. Quantity engines

```mermaid
flowchart LR
    subgraph BEAM["Beam takeoff"]
        B1[Classified Beam lines] --> B2[Centerline length]
        B2 --> B3[Section WxD<br/>tags or drawing default]
        B3 --> B4[Concrete + shuttering m³/m²]
    end

    subgraph SLAB["Slab takeoff"]
        S1[Classified framing] --> S2[Exclusions applied]
        S2 --> S3[Closed bays via beam grid]
        S3 --> S4[Nearest THK label]
        S4 --> S5[Area × thickness → m³]
    end

    BEAM --> T[Combined totals<br/>slab + beam concrete]
    SLAB --> T
```

**Slab fallback order:** beam-grid intelligence → region polygonize → beam-frame bbox.

---

## 6. Inference mode

| `project-id` | Knowledge used | When |
|--------------|----------------|------|
| **GENERIC** *(default)* | All teach projects merged | New / unknown drawings |
| INIZIO | Inizio + GLOBAL | Teach evaluation |
| TRUST_OFFICE | Trust + GLOBAL | Teach evaluation |

---

## 7. Key CLI flags

| Flag | Default | Purpose |
|------|---------|---------|
| `--project-id` | GENERIC | Teach knowledge scope |
| `--auto-layers` | on | Discover layers from DXF |
| `--no-deepseek` | off | Skip DeepSeek reasoning pass |
| `--no-beam-quantities` | off | Skip beam takeoff |
| `--llm` | off | Optional slab bay DeepSeek refinement |

API key: `DEEPSEEK_API_KEY` in `Phase2_Concrete_Estimation/.env`

---

## 8. Output files

| File | Contents |
|------|----------|
| `{drawing}_results.json` | Full run: classification, slabs, beams, totals |
| `{drawing}_building_model.json` | Semantic model + graph + quantities |
| `{drawing}_overlay.html` | Interactive component overlay |
| `{drawing}_quantities.xlsx` | Summary · Slabs · **Beams** · Classification |
| `{drawing}_review_queue.json` | Low-confidence entities |
| `{drawing}_summary.txt` | Human-readable summary |

---

## 9. Progress bar stages

| % | Stage |
|---|--------|
| 2–8 | Load DXF |
| 10–12 | Discover layers · floor zone |
| 15–25 | Load atlas · extract entities |
| 28–55 | Classify (rules → DeepSeek batches) |
| 56–57 | **Beam quantities** |
| 58–60 | Structural graph |
| 62–82 | Slab detection |
| 85–92 | Slab quantities · write outputs |
| 100 | Complete |

---

*SDIE V6 · P2_SlabVersion6 · Teach-then-infer structural estimation*
