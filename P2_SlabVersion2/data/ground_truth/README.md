# Ground truth workflow

## Files

| File | Purpose |
|------|---------|
| `Slab-02_Layer_Try.json` | Engineer-validated expected quantities and slab definitions |
| `../audits/Slab-02_Layer_Try_audit.json` | Machine DXF entity/layer audit (auto-generated) |
| `../audits/Slab-02_LGF_candidates.json` | Debug polygon candidates (not final slabs) |

## Regenerate slab entries from DXF

```bash
python scripts/generate_ground_truth_slabs.py
python scripts/validate_ground_truth_totals.py
```

## Regenerate audit

```bash
python scripts/analyze_dxf.py "Data Source/Slab Test/Slab-02_Layer_Try.dxf"
```

## Approve ground truth

1. Edit `Slab-02_Layer_Try.json` → floor `LGF` → `expected_total`.
2. Add `slabs[]` entries (see example below).
3. Set `validation_status` to `"approved"`.

### Example slab entry

```json
{
  "slab_id": "LGF-S01",
  "name": "Main bay west",
  "is_structural_slab": true,
  "thickness_mm": 200,
  "area_m2": 450.0,
  "openings_deduct_m2": 12.5,
  "net_area_m2": 437.5,
  "expected_concrete_m3": 87.5,
  "expected_shuttering_m2": 437.5,
  "polygon_wkt": null,
  "validation_status": "approved"
}
```

Regression tests compare SDIE output to `expected_total` and per-slab values when `validation_status` is `approved`.
