"""Convert a plain-text document to PDF using reportlab."""
from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IN = ROOT / "docs" / "Prompt_extracted_V6.txt"
DEFAULT_OUT = ROOT / "docs" / "Prompt_extracted_V6.pdf"

PAGE_W, PAGE_H = A4
MARGIN_L = 18 * mm
MARGIN_R = 18 * mm
MARGIN_T = 20 * mm
MARGIN_B = 18 * mm
FONT = "Courier"
FONT_SIZE = 8.5
LINE_HEIGHT = FONT_SIZE * 1.35
MAX_CHARS = 105  # wrap width for Courier at this size on A4


def _wrap_line(line: str, max_chars: int) -> list[str]:
    if len(line) <= max_chars:
        return [line]
    parts: list[str] = []
    while len(line) > max_chars:
        break_at = line.rfind(" ", 0, max_chars)
        if break_at <= 0:
            break_at = max_chars
        parts.append(line[:break_at].rstrip())
        line = line[break_at:].lstrip()
    if line:
        parts.append(line)
    return parts


def txt_to_pdf(src: Path, dst: Path) -> Path:
    text = src.read_text(encoding="utf-8")
    lines = text.splitlines()

    c = canvas.Canvas(str(dst), pagesize=A4)
    c.setTitle(src.stem)
    c.setAuthor("SDIE V6")

    y = PAGE_H - MARGIN_T
    usable_w = PAGE_W - MARGIN_L - MARGIN_R

    def new_page() -> None:
        nonlocal y
        c.showPage()
        y = PAGE_H - MARGIN_T

    c.setFont(FONT, FONT_SIZE)
    for raw in lines:
        wrapped = _wrap_line(raw.replace("\t", "    "), MAX_CHARS) or [""]
        for segment in wrapped:
            if y < MARGIN_B + LINE_HEIGHT:
                new_page()
                c.setFont(FONT, FONT_SIZE)
            c.drawString(MARGIN_L, y, segment)
            y -= LINE_HEIGHT

    c.save()
    return dst


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_IN
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUT
    if not src.is_file():
        print(f"Not found: {src}", file=sys.stderr)
        return 1
    dst.parent.mkdir(parents=True, exist_ok=True)
    out = txt_to_pdf(src, dst)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
