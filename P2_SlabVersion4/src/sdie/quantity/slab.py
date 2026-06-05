from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SlabQuantity:
    area_m2: float
    thickness_mm: int
    concrete_m3: float
    shuttering_m2: float
    trace: str


def compute_slab_quantity(
    area_m2: float,
    thickness_mm: int,
    *,
    shuttering_equals_soffit: bool = True,
) -> SlabQuantity:
    thickness_m = thickness_mm / 1000.0
    concrete_m3 = round(area_m2 * thickness_m, 6)
    shuttering_m2 = round(area_m2, 6) if shuttering_equals_soffit else round(
        area_m2 * 1.071339, 6
    )
    trace = f"area_m2={area_m2}; thickness_mm={thickness_mm}; volume={concrete_m3}"
    return SlabQuantity(
        area_m2=area_m2,
        thickness_mm=thickness_mm,
        concrete_m3=concrete_m3,
        shuttering_m2=shuttering_m2,
        trace=trace,
    )
