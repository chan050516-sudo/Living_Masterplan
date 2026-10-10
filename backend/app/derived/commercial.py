"""Commercial asset derived metrics — B-03 core."""

import math
from .context import DerivationContext


def derive_commercial(ctx: DerivationContext) -> dict:
    asset = ctx.asset
    year = ctx.year
    assumptions = ctx.assumptions

    # --- Load raw observed metric for this year ---
    metrics = ctx.business["asset_metrics"]
    row = metrics[
        (metrics["asset_id"] == asset["asset_id"]) &
        (metrics["year"] == year)
    ]
    if row.empty:
        raise ValueError(f"No asset_metrics row for {asset['asset_id']} year {year}")
    raw = row.iloc[0]

    def _get(col):
        v = raw.get(col)
        if v is None:
            return None
        try:
            if math.isnan(float(v)):
                return None
        except (TypeError, ValueError):
            return None
        return float(v)

    # --- Occupancy ---
    occupancy = _get("occupancy_rate")
    vacancy_rate = (1.0 - occupancy) if occupancy is not None else None
    vacancy_duration = _get("vacancy_duration_months")

    # --- Maintenance with aging surge ---
    completion_year = asset.get("completion_year")
    maintenance_base = asset.get("maintenance_annual_rm")
    maintenance_surge = None
    if maintenance_base is not None and completion_year is not None and not _isnan(maintenance_base):
        alpha = assumptions.get("asset_aging", {}).get("alpha", 0.03)
        years_old = max(0, year - int(completion_year))
        maintenance_surge = float(maintenance_base) * (1.0 + alpha) ** years_old
    ctx_maintenance = maintenance_surge or maintenance_base

    # --- NOI ---
    rental_income = _get("rental_income_rm")
    opex = asset.get("opex_annual_rm")
    noi = None
    if rental_income is not None and opex is not None and ctx_maintenance is not None:
        try:
            noi = rental_income - float(opex) - float(ctx_maintenance)
        except (TypeError, ValueError):
            noi = None

    # --- NOI yield ---
    capex = asset.get("capex_initial_rm")
    noi_yield = None
    if noi is not None and capex is not None and float(capex) > 0:
        noi_yield = noi / float(capex)

    # --- DSR from Huff ---
    effective_demand = ctx.huff_effective_demand
    effective_supply = asset.get("lettable_area_m2")
    dsr = None
    if effective_demand is not None and effective_supply is not None and float(effective_supply) > 0:
        dsr = effective_demand / float(effective_supply)

    # --- Footfall conversion ---
    footfall = _get("footfall_daily")
    footfall_conversion = None
    if rental_income is not None and footfall and footfall > 0:
        # Approximate: rental income / (footfall * 30 days)
        footfall_conversion = rental_income / (footfall * 365.0)

    # --- Accessibility ---
    accessibility = ctx.accessibility_score

    # --- Thermal exposure (0-100, higher = worse) ---
    # Placeholder: 70 base, minus canopy coverage bonus
    thermal = _thermal_exposure(ctx)

    return {
        "asset_id": asset["asset_id"],
        "year": year,
        "occupancy_rate": occupancy,
        "vacancy_rate": vacancy_rate,
        "vacancy_duration_months": vacancy_duration,
        "footfall_daily": footfall,
        "footfall_conversion_rm_per_person": footfall_conversion,
        "rental_income_rm": rental_income,
        "noi_rm": noi,
        "noi_yield": noi_yield,
        "maintenance_surge_rm": maintenance_surge,
        "accessibility_score": accessibility,
        "effective_demand": effective_demand,
        "effective_supply": effective_supply,
        "dsr": dsr,
        "thermal_exposure": thermal,
        "metric_source": "derived",
        "model_version": "0.3.0",
    }


def _thermal_exposure(ctx: DerivationContext) -> float:
    """
    Simple thermal proxy: high when canopy is low.
    0 = cool, 100 = hot.
    """
    canopy = ctx.asset.get("canopy_ratio")
    try:
        canopy = float(canopy) if canopy is not None else 0.0
    except (TypeError, ValueError):
        canopy = 0.0
    # Placeholder formula: 80 - 100 * canopy, clipped 0-100
    return max(0.0, min(100.0, 80.0 - 100.0 * canopy))


def _isnan(v) -> bool:
    try:
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return False