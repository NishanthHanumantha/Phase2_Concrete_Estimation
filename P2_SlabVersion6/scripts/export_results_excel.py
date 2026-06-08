"""Export SDIE *_results.json to Excel quantities workbook."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sdie.validation.excel_export import export_results_json_to_excel


def main() -> int:
    parser = argparse.ArgumentParser(description="Export pipeline JSON results to Excel")
    parser.add_argument("results_json", type=Path, help="Path to *_results.json")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output .xlsx path (default: <stem>_quantities.xlsx beside JSON)",
    )
    args = parser.parse_args()
    out = export_results_json_to_excel(args.results_json.resolve(), args.output)
    print(f"Excel saved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
