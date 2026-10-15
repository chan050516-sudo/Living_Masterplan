"""Environmental model — asset-level energy and carbon.

This module holds the fundamental energy / carbon calculations
used by B3 (derived metrics per asset). The simulation layer
imports these and adds scenario-level helpers on top.

Phase 11 additions:
  - Energy sub-system breakdown (HVAC / lighting / base load).
  - Productive vs stranded carbon split.
  - Simplified Urban Heat Island (UHI) surface temperature proxy.
  - Interim solar farm generation model.
  - Life-cycle (embodied + maintenance) carbon helpers.
"""

from ..taxonomy import get_energy_intensity


# ----------------------------------------------------------------
# Constants
# ----------------------------------------------------------------

# Life-cycle carbon (tCO2e per m2 of floor area)
MATERIAL_INTENSITY_NEW_BUILD   = 0.45   # full rebuild
MATERIAL_INTENSITY_REPURPOSE   = 0.08   # adaptive reuse (retains structure)
DEMOLITION_CARBON_INTENSITY    = 0.05   # rubble clearing on rebuild
STRUCTURAL_LIFESPAN_YEARS      = 50     # amortisation horizon
MAINTENANCE_CARBON_RATE        = 0.015  # annual maintenance carbon as
                                        # fraction of embodied

# Solar (interim farm on undeveloped parcel)
SOLAR_YIELD_KWH_PER_KWP        = 1350.0
SOLAR_CAPACITY_DENSITY_KWP     = 0.15
SOLAR_USABLE_LAND_FRACTION     = 0.60
SOLAR_INSTALL_CARBON_PER_KWP   = 0.05   # tCO2e per kWp (panel embodied)

# Microclimate
UHI_HARD_SURFACE_PENALTY_C     = 8.0
UHI_CANOPY_COOLING_C           = 4.5

# HVAC canopy relief
HVAC_CANOPY_RELIEF_PER_UNIT    = 0.10


# ----------------------------------------------------------------
# Core energy / carbon
# ----------------------------------------------------------------

def operational_carbon(energy_kwh: float, emission_factor: float) -> float:
    """Operational carbon in tCO2e."""
    return (energy_kwh * emission_factor) / 1000.0


def energy_from_intensity(floor_area: float, intensity_kwh_m2: float) -> float:
    """Annual energy (kWh) from a fixed intensity value."""
    return floor_area * intensity_kwh_m2


def embodied_carbon(floor_area: float, material_intensity: float) -> float:
    """tCO2e for a given material intensity."""
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


def shade_proxy_score_from_canopy(canopy_coverage) -> float:
    """
    Convert canopy coverage ratio [0, 1] to a 0-100 shade proxy score.
    Returns 0.0 when the input is None or invalid.
    """
    if canopy_coverage is None:
        return 0.0
    try:
        c = float(canopy_coverage)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(100.0, 100.0 * c))


# ----------------------------------------------------------------
# Phase 11 — Energy breakdown
# ----------------------------------------------------------------

def breakdown_energy(
    total_kwh: float,
    asset_type: str,
    assumptions: dict,
) -> dict:
    """
    Split annual energy into HVAC / lighting+equipment / base load.

    The split comes from `assumptions.environmental.energy_breakdown`
    keyed by asset type. Falls back to a 50/30/20 tropical default if
    the asset type is missing.
    """
    if total_kwh is None or total_kwh <= 0:
        return {
            "hvac_kwh": 0.0,
            "lighting_equipment_kwh": 0.0,
            "base_load_kwh": 0.0,
        }

    split = (
        assumptions
        .get("energy_breakdown", {})
        .get(asset_type, {})
    ) or {}
    hvac_share = float(split.get("hvac", 0.50))
    light_share = float(split.get("lighting_equipment", 0.30))
    base_share = float(split.get("base_load", 0.20))

    total_share = hvac_share + light_share + base_share
    if total_share <= 0:
        hvac_share, light_share, base_share = 0.50, 0.30, 0.20
    else:
        hvac_share /= total_share
        light_share /= total_share
        base_share /= total_share

    return {
        "hvac_kwh": total_kwh * hvac_share,
        "lighting_equipment_kwh": total_kwh * light_share,
        "base_load_kwh": total_kwh * base_share,
    }


def apply_canopy_hvac_relief(
    hvac_kwh: float,
    canopy_coverage: float,
) -> float:
    """
    Reduce HVAC load in proportion to canopy coverage.

    `HVAC_CANOPY_RELIEF_PER_UNIT = 0.10` means a fully shaded asset
    (canopy = 1.0) sees a 10% reduction in HVAC energy. This is
    consistent with tropical microclimate studies (LBNL, BCA Green
    Mark); it is a first-order approximation, not a physical model.
    """
    if hvac_kwh is None or hvac_kwh <= 0:
        return 0.0
    if canopy_coverage is None:
        return hvac_kwh
    try:
        c = max(0.0, min(1.0, float(canopy_coverage)))
    except (TypeError, ValueError):
        return hvac_kwh
    return hvac_kwh * (1.0 - HVAC_CANOPY_RELIEF_PER_UNIT * c)


# ----------------------------------------------------------------
# Phase 11 — Productive vs stranded carbon
# ----------------------------------------------------------------

def productive_stranded_carbon(
    total_carbon_tco2e: float,
    utilisation_rate: float,
) -> dict:
    """
    Split operational carbon into a productive and a stranded share.

    `utilisation_rate` is a 0-1 signal of how much the asset is
    actually serving its intended population. It is the occupancy
    rate for commercial / residential, and the utilisation rate for
    community facilities.

    Returns
    -------
    {
      "carbon_productive_tco2e":  float,
      "carbon_stranded_tco2e":    float,
      "stranded_carbon_ratio":    float,   # in [0, 1]
    }
    """
    if total_carbon_tco2e is None or total_carbon_tco2e <= 0:
        return {
            "carbon_productive_tco2e": 0.0,
            "carbon_stranded_tco2e": 0.0,
            "stranded_carbon_ratio": 0.0,
        }

    if utilisation_rate is None:
        utilisation_rate = 0.0
    try:
        u = max(0.0, min(1.0, float(utilisation_rate)))
    except (TypeError, ValueError):
        u = 0.0

    productive = total_carbon_tco2e * u
    stranded = total_carbon_tco2e * (1.0 - u)
    ratio = stranded / total_carbon_tco2e if total_carbon_tco2e > 0 else 0.0

    return {
        "carbon_productive_tco2e": productive,
        "carbon_stranded_tco2e": stranded,
        "stranded_carbon_ratio": ratio,
    }


# ----------------------------------------------------------------
# Phase 11 — Life-cycle carbon helpers
# ----------------------------------------------------------------

def embodied_amortised(
    floor_area_m2: float,
    material_intensity: float,
    lifespan_years: int = None,
) -> dict:
    """
    Return both the one-off embodied carbon and its annual amortised
    share. Lifespan defaults to the module constant when None.
    """
    total = embodied_carbon(floor_area_m2 or 0.0, material_intensity)
    life = lifespan_years or STRUCTURAL_LIFESPAN_YEARS
    if life <= 0:
        life = STRUCTURAL_LIFESPAN_YEARS
    return {
        "embodied_carbon_total_tco2e": total,
        "embodied_carbon_amortised_tco2e": total / life,
    }


def maintenance_carbon_annual(
    embodied_total_tco2e: float,
    rate: float = None,
) -> float:
    """Annual carbon attributable to maintenance activities."""
    if embodied_total_tco2e is None or embodied_total_tco2e <= 0:
        return 0.0
    r = rate if rate is not None else MAINTENANCE_CARBON_RATE
    return embodied_total_tco2e * r


# ----------------------------------------------------------------
# Phase 11 — Solar
# ----------------------------------------------------------------

def interim_solar_generation(land_area_m2: float) -> dict:
    """
    Potential output of an interim solar farm on an undeveloped parcel.

    Assumes SOLAR_USABLE_LAND_FRACTION of land becomes panel area,
    SOLAR_CAPACITY_DENSITY_KWP kWp per m2, and SOLAR_YIELD_KWH_PER_KWP
    kWh per kWp per year.

    Returns
    -------
    {
      "capacity_kwp":   float,
      "annual_kwh":     float,
    }
    """
    if not land_area_m2 or land_area_m2 <= 0:
        return {"capacity_kwp": 0.0, "annual_kwh": 0.0}

    usable_area = land_area_m2 * SOLAR_USABLE_LAND_FRACTION
    capacity = usable_area * SOLAR_CAPACITY_DENSITY_KWP
    annual_energy = capacity * SOLAR_YIELD_KWH_PER_KWP
    return {"capacity_kwp": capacity, "annual_kwh": annual_energy}


# ----------------------------------------------------------------
# Phase 11 — Urban Heat Island proxy
# ----------------------------------------------------------------

def calculate_surface_temp_delta(
    canopy_coverage_ratio: float,
    is_hard_surface: bool = True,
) -> float:
    """
    Simplified surface temperature proxy. Returns a delta in Celsius
    relative to an open-field baseline.

    Positive delta = warmer than baseline (heat island contribution).
    Negative delta = cooler than baseline (shade / evapotranspiration).

    Formula:
        ΔT = k_hard * (1 - canopy)  if hard surface
           - k_green * canopy
    """
    if canopy_coverage_ratio is None:
        canopy_coverage_ratio = 0.0
    try:
        c = max(0.0, min(1.0, float(canopy_coverage_ratio)))
    except (TypeError, ValueError):
        c = 0.0

    delta_t = 0.0
    if is_hard_surface:
        delta_t += UHI_HARD_SURFACE_PENALTY_C * (1.0 - c)
    delta_t -= UHI_CANOPY_COOLING_C * c
    return round(delta_t, 1)