"""Environmental model — asset-level energy and carbon.

This module holds the fundamental energy / carbon calculations used by
B3 (derived metrics per asset). The simulation layer imports these and
adds scenario-level helpers on top.
"""

from ..taxonomy import get_energy_intensity


def operational_carbon(energy_kwh: float, emission_factor: float) -> float:
    """Operational carbon in tCO2e."""
    return (energy_kwh * emission_factor) / 1000.0


def energy_from_intensity(floor_area: float, intensity_kwh_m2: float) -> float:
    """Annual energy (kWh) from a fixed intensity value."""
    return floor_area * intensity_kwh_m2


def embodied_carbon(floor_area: float, material_intensity: float) -> float:
    """tCO2e for new construction."""
    return floor_area * material_intensity


def energy_from_subtype(
    subtype: str,
    floor_area_m2: float,
    floor_count: int = None,
    default_intensity: float = 120.0,
) -> float:
    """
    Annual energy consumption (kWh) estimated from subtype benchmarks.

    Applies a floor-count correction for high-rise offices because
    vertical circulation and envelope losses scale with height. Falls
    back to `default_intensity` when the subtype has no taxonomy entry.
    """
    intensity = get_energy_intensity(subtype)
    if intensity is None:
        intensity = default_intensity

    if subtype == "office" and floor_count and floor_count > 10:
        intensity *= 1.15

    return floor_area_m2 * intensity