"""Environmental model — operational carbon."""


def operational_carbon(energy_kwh: float, emission_factor: float) -> float:
    """tCO2e."""
    return (energy_kwh * emission_factor) / 1000.0  # kg → t


def energy_from_intensity(floor_area: float, intensity_kwh_m2: float) -> float:
    return floor_area * intensity_kwh_m2


def embodied_carbon(floor_area: float, material_intensity: float) -> float:
    """tCO2e for new construction."""
    return floor_area * material_intensity


def carbon_10y_total(operational_annual_tco2e: float,
                     embodied_oneshot_tco2e: float,
                     horizon_years: int = 10) -> float:
    """
    Unify operational carbon (annual) and embodied carbon (one-shot)
    into a comparable 10-year total.
    """
    return operational_annual_tco2e * horizon_years + embodied_oneshot_tco2e