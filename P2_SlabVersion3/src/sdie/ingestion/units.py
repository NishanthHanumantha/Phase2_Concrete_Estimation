from __future__ import annotations

from dataclasses import dataclass

import ezdxf


@dataclass
class DrawingUnits:
    """Resolved drawing unit system for geometry calculations."""

    insunits: int
    insunits_name: str
    coordinate_unit: str  # mm | cm | m
    area_to_m2_factor: float  # multiply raw polygon.area by this


INSUNITS_NAMES = {
    0: "unitless",
    1: "inches",
    2: "feet",
    3: "mm",
    4: "cm",
    5: "m",
}


def _extent_scale(doc) -> float:
    try:
        from ezdxf import bbox

        ext = bbox.extents(doc.modelspace(), fast=True)
        return max(ext.size.x, ext.size.y)
    except Exception:
        return 0.0


def resolve_units(doc) -> DrawingUnits:
    """
    Resolve how to convert raw coordinate areas to m².

    Many structural DXFs store geometry in mm even when $INSUNITS is missing
    or set to cm. Heuristic: large coordinates (>5000) → treat as mm.
    """
    insunits = int(doc.header.get("$INSUNITS", 0))
    extent = _extent_scale(doc)

    if insunits == 4 and extent > 5000:
        # Geometry spans thousands — mm coordinates, not cm
        return DrawingUnits(
            insunits=insunits,
            insunits_name=INSUNITS_NAMES.get(insunits, "cm"),
            coordinate_unit="mm",
            area_to_m2_factor=1.0 / 1_000_000.0,
        )
    if insunits == 4:
        return DrawingUnits(
            insunits=insunits,
            insunits_name="cm",
            coordinate_unit="cm",
            area_to_m2_factor=1.0 / 10_000.0,
        )
    if insunits == 3:
        return DrawingUnits(
            insunits=insunits,
            insunits_name="mm",
            coordinate_unit="mm",
            area_to_m2_factor=1.0 / 1_000_000.0,
        )
    if insunits == 5:
        return DrawingUnits(
            insunits=insunits,
            insunits_name="m",
            coordinate_unit="m",
            area_to_m2_factor=1.0,
        )

    # Default heuristic for unitless / missing INSUNITS
    if extent > 5000:
        return DrawingUnits(
            insunits=insunits,
            insunits_name=INSUNITS_NAMES.get(insunits, "unitless"),
            coordinate_unit="mm",
            area_to_m2_factor=1.0 / 1_000_000.0,
        )
    return DrawingUnits(
        insunits=insunits,
        insunits_name=INSUNITS_NAMES.get(insunits, "unitless"),
        coordinate_unit="cm",
        area_to_m2_factor=1.0 / 10_000.0,
    )
