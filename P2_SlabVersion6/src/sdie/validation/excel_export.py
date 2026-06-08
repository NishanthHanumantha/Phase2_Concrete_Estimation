"""Export SDIE pipeline results to Excel."""
from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import openpyxl
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter
except ImportError:  # pragma: no cover
    openpyxl = None  # type: ignore
    Font = None  # type: ignore
    get_column_letter = None  # type: ignore


def _require_openpyxl() -> None:
    if openpyxl is None:
        raise RuntimeError("openpyxl is required: pip install openpyxl")


def _bounds_to_dims_m(bounds_cm: list[float] | tuple[float, ...] | None) -> tuple[float | None, float | None]:
    if not bounds_cm or len(bounds_cm) < 4:
        return None, None
    length_m = abs(bounds_cm[2] - bounds_cm[0]) / 100.0
    breadth_m = abs(bounds_cm[3] - bounds_cm[1]) / 100.0
    return round(length_m, 3), round(breadth_m, 3)


def _autosize_columns(ws) -> None:
    for col_idx, column_cells in enumerate(ws.columns, start=1):
        max_len = 0
        for cell in column_cells:
            if cell.value is not None:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 2, 48)


def _write_summary_sheet(wb, result: dict[str, Any]) -> None:
    ws = wb.active
    ws.title = "Summary"
    bold = Font(bold=True)
    ws["A1"] = "SDIE Pipeline Results"
    ws["A1"].font = bold

    totals = result.get("totals") or {}
    notes = result.get("detection_notes") or {}
    cls = notes.get("classification") or {}
    benchmark = result.get("benchmark") or {}
    config = result.get("config") or {}

    rows: list[tuple[str, Any]] = [
        ("Source DXF", Path(str(result.get("source_dxf", ""))).name),
        ("Processed at", result.get("processed_at")),
        ("Engine version", result.get("version")),
        ("Project ID", config.get("project_id")),
        ("Detection mode", config.get("detection_mode")),
        ("", ""),
        ("Slab count", totals.get("slab_count")),
        ("Slab area (m2)", totals.get("area_m2")),
        ("Slab concrete (m3)", totals.get("slab_concrete_m3")),
        ("Beam count", totals.get("beam_count")),
        ("Beam total length (m)", totals.get("beam_total_length_m")),
        ("Beam concrete (m3)", totals.get("beam_concrete_m3")),
        ("Total concrete (m3)", totals.get("concrete_m3")),
        ("Total shuttering (m2)", totals.get("shuttering_m2")),
        ("", ""),
        ("Entities classified", notes.get("entity_count")),
        ("Review required", notes.get("review_required_count")),
        ("Low confidence %", notes.get("low_confidence_pct")),
        ("DeepSeek ambiguous", cls.get("ambiguous_count")),
        ("DeepSeek updated", (cls.get("deepseek") or {}).get("updated") if isinstance(cls.get("deepseek"), dict) else None),
        ("", ""),
        ("Benchmark status", benchmark.get("status")),
        ("Benchmark accuracy %", benchmark.get("overall_accuracy_pct")),
    ]

    for idx, (label, value) in enumerate(rows, start=3):
        ws.cell(row=idx, column=1, value=label)
        ws.cell(row=idx, column=2, value=value)
    ws["A3"].font = bold
    _autosize_columns(ws)


def _write_slabs_sheet(wb, slabs: list[dict[str, Any]]) -> None:
    ws = wb.create_sheet("Slabs")
    headers = [
        "S.No",
        "Slab ID",
        "Strategy",
        "Length (m)",
        "Breadth (m)",
        "Thickness (mm)",
        "Area (m2)",
        "Concrete (m3)",
        "Shuttering (m2)",
        "Thickness Source",
        "Centroid X (cm)",
        "Centroid Y (cm)",
    ]
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True)

    for row_idx, slab in enumerate(slabs, start=2):
        length_m, breadth_m = _bounds_to_dims_m(slab.get("bounds_cm"))
        centroid = slab.get("centroid_cm") or [None, None]
        ws.cell(row=row_idx, column=1, value=row_idx - 1)
        ws.cell(row=row_idx, column=2, value=slab.get("slab_id"))
        ws.cell(row=row_idx, column=3, value=slab.get("strategy"))
        ws.cell(row=row_idx, column=4, value=length_m)
        ws.cell(row=row_idx, column=5, value=breadth_m)
        ws.cell(row=row_idx, column=6, value=slab.get("thickness_mm"))
        ws.cell(row=row_idx, column=7, value=round(float(slab.get("area_m2") or 0), 3))
        ws.cell(row=row_idx, column=8, value=round(float(slab.get("concrete_m3") or 0), 3))
        ws.cell(row=row_idx, column=9, value=round(float(slab.get("shuttering_m2") or 0), 3))
        ws.cell(row=row_idx, column=10, value=slab.get("thickness_source"))
        ws.cell(row=row_idx, column=11, value=centroid[0] if len(centroid) > 0 else None)
        ws.cell(row=row_idx, column=12, value=centroid[1] if len(centroid) > 1 else None)

    total_row = len(slabs) + 2
    ws.cell(row=total_row, column=1, value="TOTAL").font = Font(bold=True)
    ws.cell(row=total_row, column=7, value=round(sum(float(s.get("area_m2") or 0) for s in slabs), 3)).font = Font(bold=True)
    ws.cell(row=total_row, column=8, value=round(sum(float(s.get("concrete_m3") or 0) for s in slabs), 3)).font = Font(bold=True)
    ws.cell(row=total_row, column=9, value=round(sum(float(s.get("shuttering_m2") or 0) for s in slabs), 3)).font = Font(bold=True)
    _autosize_columns(ws)


def _write_beams_sheet(wb, beams: list[dict[str, Any]]) -> None:
    if not beams:
        return
    ws = wb.create_sheet("Beams")
    headers = [
        "S.No",
        "Beam ID",
        "Component ID",
        "Layer",
        "Length (m)",
        "Width (mm)",
        "Depth (mm)",
        "Section Source",
        "Concrete (m3)",
        "Shuttering (m2)",
        "Confidence",
        "Centroid X (mm)",
        "Centroid Y (mm)",
    ]
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True)

    for row_idx, beam in enumerate(beams, start=2):
        centroid = beam.get("centroid_mm") or [None, None]
        ws.cell(row=row_idx, column=1, value=row_idx - 1)
        ws.cell(row=row_idx, column=2, value=beam.get("beam_id"))
        ws.cell(row=row_idx, column=3, value=beam.get("component_id"))
        ws.cell(row=row_idx, column=4, value=beam.get("layer"))
        ws.cell(row=row_idx, column=5, value=beam.get("length_m"))
        ws.cell(row=row_idx, column=6, value=beam.get("width_mm"))
        ws.cell(row=row_idx, column=7, value=beam.get("depth_mm"))
        ws.cell(row=row_idx, column=8, value=beam.get("section_source"))
        ws.cell(row=row_idx, column=9, value=round(float(beam.get("concrete_m3") or 0), 3))
        ws.cell(row=row_idx, column=10, value=round(float(beam.get("shuttering_m2") or 0), 3))
        ws.cell(row=row_idx, column=11, value=beam.get("confidence"))
        ws.cell(row=row_idx, column=12, value=centroid[0] if len(centroid) > 0 else None)
        ws.cell(row=row_idx, column=13, value=centroid[1] if len(centroid) > 1 else None)

    total_row = len(beams) + 2
    ws.cell(row=total_row, column=1, value="TOTAL").font = Font(bold=True)
    ws.cell(row=total_row, column=5, value=round(sum(float(b.get("length_m") or 0) for b in beams), 3)).font = Font(bold=True)
    ws.cell(row=total_row, column=9, value=round(sum(float(b.get("concrete_m3") or 0) for b in beams), 3)).font = Font(bold=True)
    ws.cell(row=total_row, column=10, value=round(sum(float(b.get("shuttering_m2") or 0) for b in beams), 3)).font = Font(bold=True)
    _autosize_columns(ws)


def _write_classification_sheet(wb, result: dict[str, Any]) -> None:
    notes = result.get("detection_notes") or {}
    counts = notes.get("component_type_counts") or {}
    if not counts:
        return
    ws = wb.create_sheet("Classification")
    ws.cell(row=1, column=1, value="Component Type").font = Font(bold=True)
    ws.cell(row=1, column=2, value="Count").font = Font(bold=True)
    for row_idx, (ctype, count) in enumerate(sorted(counts.items()), start=2):
        ws.cell(row=row_idx, column=1, value=ctype)
        ws.cell(row=row_idx, column=2, value=count)
    _autosize_columns(ws)


def export_results_to_excel(
    result: dict[str, Any],
    output_path: Path,
) -> Path:
    """Write pipeline result dict to an Excel workbook."""
    _require_openpyxl()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.Workbook()
    _write_summary_sheet(wb, result)
    _write_slabs_sheet(wb, result.get("slabs") or [])
    _write_beams_sheet(wb, result.get("beams") or [])
    _write_classification_sheet(wb, result)
    wb.save(output_path)
    return output_path


def export_results_json_to_excel(json_path: Path, output_path: Path | None = None) -> Path:
    """Load a *_results.json file and export to Excel."""
    import json

    result = json.loads(json_path.read_text(encoding="utf-8"))
    out = output_path or json_path.with_name(json_path.stem.replace("_results", "") + "_quantities.xlsx")
    if out.suffix.lower() != ".xlsx":
        out = out.with_suffix(".xlsx")
    return export_results_to_excel(result, out)
