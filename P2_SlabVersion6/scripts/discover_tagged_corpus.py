"""Discover Tagged Files_2 DXFs and emit manifest drawing entries."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sdie.project_knowledge.paths import (
    REVISED_TAGGED_DIR_REL,
    REVISED_TAGGED_V2_ROOT_REL,
    tagged_v2_component_flag,
    tagged_v2_folder_for_flag,
)

FOLDER_TO_FLAG = {
    "Slab": "tagged_slab",
    "Beam": "tagged_beam",
    "Column": "tagged_column",
    "Wall": "tagged_shearwall",
}


def discover_tagged_files_v2(project_root: Path) -> list[dict]:
    root = project_root / REVISED_TAGGED_V2_ROOT_REL.replace("/", "\\")
    if not root.is_dir():
        root = project_root / REVISED_TAGGED_V2_ROOT_REL
    entries: list[dict] = []
    for folder_name, flag in FOLDER_TO_FLAG.items():
        folder = root / folder_name
        if not folder.is_dir():
            continue
        for dxf in sorted(folder.glob("*.dxf")):
            rel = dxf.relative_to(project_root).as_posix()
            entries.append(
                {
                    "drawing_id": dxf.stem,
                    "dxf": rel,
                    flag: True,
                    "corpus": "tagged_files_v2",
                    "floor_plan": True,
                    "component_folder": folder_name,
                }
            )
    return entries


def discover_legacy_tagged(project_root: Path) -> list[dict]:
    root = project_root / REVISED_TAGGED_DIR_REL.replace("/", "\\")
    if not root.is_dir():
        root = project_root / REVISED_TAGGED_DIR_REL
    entries: list[dict] = []
    mapping = {
        "Inizio Slab with tag_Revised1.dxf": "tagged_slab",
        "Inizio - Beam with tag_Revised1.dxf": "tagged_beam",
        "Inizio - Colum with tag_Revised1.dxf": "tagged_column",
        "Inizio - Shearwall with tag_Revised1.dxf": "tagged_shearwall",
    }
    for name, flag in mapping.items():
        path = root / name
        if not path.is_file():
            continue
        rel = path.relative_to(project_root).as_posix()
        entries.append(
            {
                "drawing_id": path.stem,
                "dxf": rel,
                flag: True,
                "corpus": "tagged_files_v1",
                "floor_plan": False,
            }
        )
    return entries


def summarize(entries: list[dict]) -> dict:
    by_flag: dict[str, int] = {}
    by_corpus: dict[str, int] = {}
    for e in entries:
        by_corpus[e.get("corpus", "?")] = by_corpus.get(e.get("corpus", "?"), 0) + 1
        for flag in FOLDER_TO_FLAG.values():
            if e.get(flag):
                by_flag[flag] = by_flag.get(flag, 0) + 1
    return {"total": len(entries), "by_corpus": by_corpus, "by_component_flag": by_flag}


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover INIZIO tagged teach corpus")
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument(
        "--include-legacy",
        action="store_true",
        help="Include Revised Project Knowledge/Tagged files (4 full sheets)",
    )
    parser.add_argument(
        "--write-manifest",
        type=Path,
        default=None,
        help="Merge discoveries into projects_manifest.json INIZIO drawings",
    )
    args = parser.parse_args()

    entries = discover_tagged_files_v2(args.project_root)
    if args.include_legacy:
        entries = discover_legacy_tagged(args.project_root) + entries

    print(json.dumps({"summary": summarize(entries), "drawings": entries}, indent=2))

    if args.write_manifest:
        manifest_path = args.write_manifest
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for project in manifest.get("projects", []):
            if project.get("project_id") != "INIZIO":
                continue
            project["tagged_corpus_v2"] = REVISED_TAGGED_V2_ROOT_REL
            project["drawings"] = entries
            project["dxf_folder"] = REVISED_TAGGED_V2_ROOT_REL
            break
        manifest["version"] = "4"
        manifest["description"] = (
            "INIZIO teach: Tagged Files_2 single-floor component plans (primary) "
            "+ legacy Tagged files full sheets. TRUST/MANOHAR unchanged."
        )
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote {len(entries)} INIZIO drawings to {manifest_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
