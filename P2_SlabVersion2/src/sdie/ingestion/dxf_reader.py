from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import ezdxf
from ezdxf import bbox

from sdie.ingestion.units import DrawingUnits, resolve_units


@dataclass
class DrawingMeta:
    path: str
    dxf_version: str
    insunits: int
    insunits_name: str
    coordinate_unit: str
    area_to_m2_factor: float
    extents: dict | None


def load_drawing(path: Path) -> tuple[ezdxf.document.Drawing, DrawingMeta]:
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    units = resolve_units(doc)
    try:
        ext = bbox.extents(msp, fast=True)
        extents = {
            "min": [round(ext.extmin.x, 3), round(ext.extmin.y, 3)],
            "max": [round(ext.extmax.x, 3), round(ext.extmax.y, 3)],
        }
    except Exception:
        extents = None

    meta = DrawingMeta(
        path=str(path),
        dxf_version=doc.dxfversion,
        insunits=units.insunits,
        insunits_name=units.insunits_name,
        coordinate_unit=units.coordinate_unit,
        area_to_m2_factor=units.area_to_m2_factor,
        extents=extents,
    )
    return doc, meta
