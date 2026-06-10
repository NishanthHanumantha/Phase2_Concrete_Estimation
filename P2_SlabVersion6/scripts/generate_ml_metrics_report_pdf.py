"""Generate a PDF report of combined train + test ML metrics."""
from __future__ import annotations

import json
import statistics
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
TRAIN_PATH = ROOT / "Output/ml_eval/train_metrics.json"
TEST_PATH = ROOT / "Output/ml_eval/test_metrics.json"
TEST_GIT = "431aa01:P2_SlabVersion6/Output/ml_eval/test_metrics.json"
DEFAULT_OUT = ROOT / "Output/ml_eval/SDIE_V6_Combined_ML_Metrics_Report.pdf"

PAGE_W, _ = A4
CONTENT_W = PAGE_W - 36 * mm


def _load_test_metrics() -> tuple[dict[str, Any], str]:
    if TEST_PATH.is_file():
        return json.loads(TEST_PATH.read_text(encoding="utf-8")), str(TEST_PATH)
    raw = subprocess.check_output(["git", "show", TEST_GIT], cwd=ROOT.parent)
    return json.loads(raw.decode("utf-8")), f"git archive ({TEST_GIT})"


def _ref(f: dict, ctype: str, key: str) -> Any:
    return (
        f.get("reference_accuracy", {})
        .get("entity_count", {})
        .get(ctype, {})
        .get(key)
    )


def _aggregate_test(test: dict[str, Any]) -> dict[str, Any]:
    files = test.get("per_file", [])
    slab_pred = sum(
        f.get("classification_proxy", {}).get("by_type", {}).get("Slab", 0) for f in files
    )
    beam_pred = sum(
        f.get("classification_proxy", {}).get("by_type", {}).get("Beam", 0) for f in files
    )
    total_ent = sum(f.get("classification_proxy", {}).get("entities_total", 0) for f in files)
    slab_ref_actual = sum(_ref(f, "Slab", "actual") or 0 for f in files)
    beam_ref_actual = sum(_ref(f, "Beam", "actual") or 0 for f in files)
    slab_ref_expected = sum(_ref(f, "Slab", "expected") or 0 for f in files)
    beam_ref_expected = sum(_ref(f, "Beam", "expected") or 0 for f in files)
    slab_acc = [v for f in files if (v := _ref(f, "Slab", "accuracy_pct")) is not None]
    beam_acc = [v for f in files if (v := _ref(f, "Beam", "accuracy_pct")) is not None]
    return {
        "files": test.get("files_evaluated", 0),
        "paired": test.get("files_paired", 0),
        "quality_pass": test.get("files_quality_pass", 0),
        "total_entities": total_ent,
        "slab_pred": slab_pred,
        "beam_pred": beam_pred,
        "slab_ref_actual": slab_ref_actual,
        "beam_ref_actual": beam_ref_actual,
        "slab_ref_expected": slab_ref_expected,
        "beam_ref_expected": beam_ref_expected,
        "mean_ref_acc": test.get("mean_reference_accuracy_pct"),
        "mean_slab_ref": round(statistics.mean(slab_acc), 1) if slab_acc else None,
        "mean_beam_ref": round(statistics.mean(beam_acc), 1) if beam_acc else None,
    }


def _table_style(header_rows: int = 1) -> TableStyle:
    style = TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, header_rows - 1), colors.HexColor("#1e3a5f")),
            ("TEXTCOLOR", (0, 0), (-1, header_rows - 1), colors.white),
            ("FONTNAME", (0, 0), (-1, header_rows - 1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("FONTNAME", (0, header_rows), (-1, -1), "Helvetica"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("ROWBACKGROUNDS", (0, header_rows), (-1, -1), [colors.white, colors.HexColor("#f5f7fa")]),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]
    )
    return style


def _cell_style() -> ParagraphStyle:
    return ParagraphStyle(
        "TableCell",
        fontName="Helvetica",
        fontSize=8.5,
        leading=10,
        alignment=1,
    )


def _header_cell_style() -> ParagraphStyle:
    return ParagraphStyle(
        "TableHeader",
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=10,
        alignment=1,
        textColor=colors.white,
    )


def _make_table(
    data: list[list[str]],
    col_widths: list[float] | None = None,
    *,
    header_rows: int = 1,
) -> Table:
    cell = _cell_style()
    header = _header_cell_style()
    rows: list[list[Any]] = []
    for r_idx, row in enumerate(data):
        style = header if r_idx < header_rows else cell
        rows.append([Paragraph(str(cell_text), style) for cell_text in row])
    tbl = Table(rows, colWidths=col_widths, repeatRows=header_rows)
    tbl.setStyle(_table_style(header_rows=header_rows))
    return tbl


def _fmt_int(n: int | float | None) -> str:
    if n is None:
        return "—"
    return f"{int(n):,}"


def _fmt_pct(n: float | None) -> str:
    if n is None:
        return "—"
    return f"{n:.1f}%"


def build_pdf(dst: Path) -> Path:
    train = json.loads(TRAIN_PATH.read_text(encoding="utf-8"))
    test, test_source = _load_test_metrics()
    tx = _aggregate_test(test)

    gt_total = train["gt_corpus"]["total_entities"]
    gt_slab = train["gt_corpus"]["by_type"]["Slab"]
    gt_beam = train["gt_corpus"]["by_type"]["Beam"]
    classified = train["summary"]["entities_evaluated"]
    missing = train["summary"]["missing_predictions"]
    correct = train["summary"]["correct"]
    slab_tp = train["per_class"]["Slab"]["tp"]
    beam_tp = train["per_class"]["Beam"]["tp"]
    slab_fp = train["per_class"]["Slab"]["fp"]
    beam_fp = train["per_class"]["Beam"]["fp"]
    acc = train["summary"]["accuracy_pct"]
    slab_f1 = train["per_class"]["Slab"]["f1_pct"]
    beam_f1 = train["per_class"]["Beam"]["f1_pct"]
    mean_f1 = train["summary"]["slab_beam_mean_f1_pct"]
    train_pass = "No" if not train.get("quality_pass") else "Yes"

    pred_slab_train = slab_tp + slab_fp
    pred_beam_train = beam_tp + beam_fp

    grand_classified = classified + tx["total_entities"]
    target = 85.0

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=6,
        textColor=colors.HexColor("#1e3a5f"),
    )
    h2_style = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontSize=11,
        spaceBefore=10,
        spaceAfter=6,
        textColor=colors.HexColor("#1e3a5f"),
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        spaceAfter=4,
    )
    note_style = ParagraphStyle(
        "Note",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#555555"),
        spaceAfter=6,
    )

    dst.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(dst),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="SDIE V6 Combined ML Metrics Report",
        author="SDIE V6",
    )

    story: list[Any] = []
    story.append(Paragraph("SDIE V6 — Combined ML Metrics Report", title_style))
    story.append(
        Paragraph(
            f"Train corpus (X): <b>Tagged Files_2</b> &nbsp;|&nbsp; "
            f"Test corpus (Y): <b>Raw files_2</b> &nbsp;|&nbsp; "
            f"Generated: {date.today().isoformat()}",
            body_style,
        )
    )
    story.append(
        Paragraph(
            f"Phase target: classification F1 and reference accuracy ≥ <b>{target:.0f}%</b>",
            body_style,
        )
    )
    story.append(Spacer(1, 6))

    # Overview
    story.append(Paragraph("Combined ML Metrics — Overview", h2_style))
    cw = [CONTENT_W * 0.28, CONTENT_W * 0.24, CONTENT_W * 0.24, CONTENT_W * 0.24]
    story.append(
        _make_table(
            [
                ["", "Train (X)", "Test (Y)", "Target"],
                ["Corpus", "Tagged Files_2", "Raw files_2", "—"],
                ["Drawings", "47", f"{tx['files']} ({tx['paired']} paired)", "—"],
                [
                    "Metric type",
                    "Entity-level GT (manifest flags)",
                    "Paired teach-reference proxy",
                    "—",
                ],
            ],
            cw,
        )
    )
    story.append(Spacer(1, 10))

    # Sample counts
    story.append(Paragraph("Sample Counts", h2_style))
    story.append(
        _make_table(
            [
                ["", "Train (X)", "Test (Y)"],
                [
                    "Ground truth / reference",
                    f"{_fmt_int(gt_total)} slab+beam entities",
                    f"Teach ref: {_fmt_int(tx['slab_ref_expected'])} slab + "
                    f"{_fmt_int(tx['beam_ref_expected'])} beam",
                ],
                [
                    "Total classified (with prediction)",
                    f"<b>{_fmt_int(classified)}</b>",
                    f"<b>{_fmt_int(tx['total_entities'])}</b>",
                ],
                ["Missing predictions", _fmt_int(missing), "—"],
                [
                    "Predicted as Slab",
                    f"{_fmt_int(pred_slab_train)} ({_fmt_int(slab_tp)} correct TP)",
                    f"{_fmt_int(tx['slab_pred'])} labeled / "
                    f"{_fmt_int(tx['slab_ref_actual'])} ref-count",
                ],
                [
                    "Predicted as Beam",
                    f"{_fmt_int(pred_beam_train)} ({_fmt_int(beam_tp)} correct TP)",
                    f"{_fmt_int(tx['beam_pred'])} labeled / "
                    f"{_fmt_int(tx['beam_ref_actual'])} ref-count",
                ],
            ],
            [CONTENT_W * 0.34, CONTENT_W * 0.33, CONTENT_W * 0.33],
        )
    )
    story.append(Spacer(1, 10))

    # Correctness
    story.append(Paragraph("Correctness", h2_style))
    story.append(
        _make_table(
            [
                ["", "Train (X)", "Test (Y)"],
                [
                    "Correct (any class)",
                    f"<b>{_fmt_int(correct)}</b>",
                    "N/A (no entity-level GT on raw)",
                ],
                [
                    "Correct Slab",
                    f"<b>{_fmt_int(slab_tp)}</b> / {_fmt_int(gt_slab)} GT",
                    f"Mean ref entity-count acc <b>{_fmt_pct(tx['mean_slab_ref'])}</b>",
                ],
                [
                    "Correct Beam",
                    f"<b>{_fmt_int(beam_tp)}</b> / {_fmt_int(gt_beam)} GT",
                    f"Mean ref entity-count acc <b>{_fmt_pct(tx['mean_beam_ref'])}</b>",
                ],
            ],
            [CONTENT_W * 0.34, CONTENT_W * 0.33, CONTENT_W * 0.33],
        )
    )
    story.append(Spacer(1, 10))

    # Accuracy & F1
    story.append(Paragraph("Accuracy &amp; F1", h2_style))
    story.append(
        _make_table(
            [
                ["Metric", "Train (X)", "Test (Y)", "Target"],
                ["Overall accuracy", _fmt_pct(acc), _fmt_pct(tx["mean_ref_acc"]), f"≥ {target:.0f}%"],
                ["Slab F1 / ref acc", _fmt_pct(slab_f1), _fmt_pct(tx["mean_slab_ref"]), f"≥ {target:.0f}%"],
                ["Beam F1 / ref acc", _fmt_pct(beam_f1), _fmt_pct(tx["mean_beam_ref"]), f"≥ {target:.0f}%"],
                ["Slab+Beam mean", _fmt_pct(mean_f1), "—", f"≥ {target:.0f}%"],
                ["Pass", train_pass, f"{tx['quality_pass']}/{tx['files']} files", "—"],
            ],
            cw,
        )
    )
    story.append(Spacer(1, 10))

    # Train detail
    story.append(Paragraph("Train (X) — Detail", h2_style))
    train_bullets = [
        f"<b>47</b> teach drawings ({_fmt_int(gt_total)} slab+beam GT entities)",
        f"<b>{_fmt_int(classified)}</b> entities received a prediction; "
        f"<b>{_fmt_int(missing)}</b> had none",
        f"<b>{_fmt_int(correct)}</b> correct overall "
        f"({_fmt_int(slab_tp)} slab TP + {_fmt_int(beam_tp)} beam TP)",
        "Primary error mode: slab↔beam confusion "
        f"({train['confusion']['Slab']['Beam']:,} slab GT → predicted beam; "
        f"{train['confusion']['Beam']['Slab']:,} beam GT → predicted slab)",
        "Drawings 1–10: cached DeepSeek run; drawings 11–47: --no-deepseek (API timeouts)",
        f"Quality gate: <b>FAIL</b> (accuracy {_fmt_pct(acc)}, mean F1 {_fmt_pct(mean_f1)})",
    ]
    for line in train_bullets:
        story.append(Paragraph(f"• {line}", body_style))

    story.append(Spacer(1, 8))

    # Test detail
    story.append(Paragraph("Test (Y) — Detail", h2_style))
    test_bullets = [
        f"<b>{tx['paired']}/{tx['files']}</b> raw DXFs paired to teach references",
        f"<b>{_fmt_int(tx['total_entities'])}</b> entities classified total",
        f"<b>{_fmt_int(tx['slab_pred'])}</b> predicted Slab, "
        f"<b>{_fmt_int(tx['beam_pred'])}</b> predicted Beam (classification proxy)",
        f"vs teach reference counts: slab {_fmt_int(tx['slab_ref_actual'])} actual vs "
        f"{_fmt_int(tx['slab_ref_expected'])} expected; beam "
        f"{_fmt_int(tx['beam_ref_actual'])} vs {_fmt_int(tx['beam_ref_expected'])}",
        f"Beam count tracking relatively strong (~{_fmt_pct(tx['mean_beam_ref'])}); "
        f"slab under-detected (~{_fmt_pct(tx['mean_slab_ref'])} mean ref acc)",
        f"<b>{tx['quality_pass']}/{tx['files']}</b> files passed the {target:.0f}% quality gate",
    ]
    for line in test_bullets:
        story.append(Paragraph(f"• {line}", body_style))

    story.append(Spacer(1, 8))

    # Grand totals
    story.append(Paragraph("Grand Totals (Both Splits)", h2_style))
    story.append(
        _make_table(
            [
                ["", "Count"],
                ["Entities classified (train + test)", f"<b>{_fmt_int(grand_classified)}</b>"],
                ["Correct Slab (train TP only)", f"<b>{_fmt_int(slab_tp)}</b>"],
                ["Correct Beam (train TP only)", f"<b>{_fmt_int(beam_tp)}</b>"],
                ["Correct Slab+Beam (train only)", f"<b>{_fmt_int(correct)}</b>"],
            ],
            [CONTENT_W * 0.65, CONTENT_W * 0.35],
        )
    )
    story.append(Spacer(1, 10))

    story.append(
        Paragraph(
            "<b>Notes:</b> Test metrics use paired teach-reference count accuracy, not per-entity "
            "TP/FN like train. Test data source: "
            f"<i>{test_source}</i>. "
            "Re-run <font face='Courier'>python scripts/evaluate_ml_project.py --test-only</font> "
            "to refresh test metrics on disk.",
            note_style,
        )
    )
    story.append(
        Paragraph(
            f"Source files: {TRAIN_PATH.relative_to(ROOT)} | "
            f"{TEST_PATH.relative_to(ROOT) if TEST_PATH.is_file() else 'test_metrics (archived)'}",
            note_style,
        )
    )

    doc.build(story)
    return dst


def main() -> int:
    dst = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    if not TRAIN_PATH.is_file():
        print(f"Missing train metrics: {TRAIN_PATH}", file=sys.stderr)
        return 1
    out = build_pdf(dst)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
