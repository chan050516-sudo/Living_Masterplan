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

    # --- DSR from Huff (unit-corrected) ---
    # Huff returns effective_demand in persons. Convert to m² using per-capita
    # commercial demand coefficient, so DSR is dimensionless (m² / m²).
    huff_demand_persons = ctx.huff_effective_demand
    per_capita_m2 = assumptions.get("demand", {}).get(
        "commercial_per_capita_m2", {}
    )
    e_k = sum(per_capita_m2.values()) if per_capita_m2 else 0.48  # m²/person

    effective_demand_m2 = None
    if huff_demand_persons is not None:
        effective_demand_m2 = huff_demand_persons * e_k

    effective_supply = asset.get("lettable_area_m2")
    dsr = None
    if (effective_demand_m2 is not None
            and effective_supply is not None
            and float(effective_supply) > 0):
        dsr = effective_demand_m2 / float(effective_supply)

    # --- Footfall conversion (renamed: this is a rental income proxy, not a
    # true sales conversion rate). ---
    footfall = _get("footfall_daily")
    rental_income_per_visit = None
    if rental_income is not None and footfall and footfall > 0:
        rental_income_per_visit = rental_income / (footfall * 365.0)

    # --- Accessibility ---
    accessibility = ctx.accessibility_score

    shade = _shade_proxy_score(ctx)

    return {
        "asset_id": asset["asset_id"],
        "year": year,
        "occupancy_rate": occupancy,
        "vacancy_rate": vacancy_rate,
        "vacancy_duration_months": vacancy_duration,
        "footfall_daily": footfall,
        "rental_income_per_visit_proxy": rental_income_per_visit,   # renamed
        "rental_income_rm": rental_income,
        "noi_rm": noi,
        "noi_yield": noi_yield,
        "maintenance_surge_rm": maintenance_surge,
        "accessibility_score": accessibility,
        "effective_demand": huff_demand_persons,      # persons (raw Huff output)
        "effective_demand_m2": effective_demand_m2,   # NEW: m² (for DSR)
        "effective_supply": effective_supply,
        "dsr": dsr,   # dimensionless
        "shade_proxy_score": shade,     # replaces "thermal_exposure"
        "metric_source": "derived",
        "model_version": "0.3.0",
    }


def _shade_proxy_score(ctx: DerivationContext) -> float:
    """
    Proxy for shade availability. 0 = no shade, 100 = fully shaded.
    NOT a temperature model. Higher is better.
    """
    canopy = ctx.asset.get("canopy_ratio")
    try:
        canopy = float(canopy) if canopy is not None else 0.0
    except (TypeError, ValueError):
        canopy = 0.0
    return max(0.0, min(100.0, 100.0 * canopy))


def _isnan(v) -> bool:
    try:
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return False