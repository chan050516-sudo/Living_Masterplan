"""Commercial asset derived metrics.

Phase 11 additions:
  - Energy sub-system split.
  - Productive vs stranded carbon.
  - Life-cycle carbon (embodied amortised + maintenance).
  - UHI surface temperature proxy.
"""

import math
from .. import __version__
from .context import DerivationContext
from ..taxonomy import get_subtype_or_default, default_subtype_for
from .demand_mismatch import demographic_mismatch
from .environmental import (
    energy_from_subtype,
    operational_carbon,
    shade_proxy_score_from_canopy,
    breakdown_energy,
    apply_canopy_hvac_relief,
    productive_stranded_carbon,
    embodied_amortised,
    maintenance_carbon_annual,
    calculate_surface_temp_delta,
    MATERIAL_INTENSITY_NEW_BUILD,
    MATERIAL_INTENSITY_REPURPOSE,
)


def derive_commercial(ctx: DerivationContext) -> dict:
    asset = ctx.asset
    year = ctx.year
    assumptions = ctx.assumptions

    subtype = asset.get("subtype") or default_subtype_for(asset.get("asset_type"))
    subtype_cfg = get_subtype_or_default(subtype)

    raw = _get_metric_row(ctx, asset["asset_id"], year)

    def _get(col):
        v = raw.get(col) if raw is not None else None
        if v is None:
            return None
        try:
            if math.isnan(float(v)):
                return None
        except (TypeError, ValueError):
            return None
        return float(v)

    # --- Occupancy / vacancy ---
    occupancy = _get("occupancy_rate")
    vacancy_rate = (1.0 - occupancy) if occupancy is not None else None
    vacancy_duration = _get("vacancy_duration_months")

    # --- Maintenance surge ---
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

    capex = asset.get("capex_initial_rm")
    noi_yield = None
    if noi is not None and capex is not None and float(capex) > 0:
        noi_yield = noi / float(capex)

    # --- DSR ---
    demand_m2 = ctx.huff_effective_demand_m2
    effective_supply = asset.get("lettable_area_m2")
    dsr = None
    if (demand_m2 is not None
            and effective_supply is not None
            and float(effective_supply) > 0):
        dsr = demand_m2 / float(effective_supply)

    # --- Rental income per visit (proxy) ---
    footfall = _get("footfall_daily")
    rental_income_per_visit = None
    if rental_income is not None and footfall and footfall > 0:
        rental_income_per_visit = rental_income / (footfall * 365.0)

    # --- Accessibility ---
    walking = ctx.walking_profile or {}
    driving = ctx.driving_profile or {}

    # --- Shade proxy ---
    shade = shade_proxy_score_from_canopy(ctx.canopy_coverage)

    # --- Energy / carbon ---
    floor_area = float(asset.get("floor_area_m2") or 0.0)
    energy_kwh = energy_from_subtype(subtype, floor_area)

    # Phase 11 — sub-system split with canopy HVAC relief
    breakdown = breakdown_energy(energy_kwh, "commercial", assumptions)
    hvac_adj = apply_canopy_hvac_relief(
        breakdown["hvac_kwh"], ctx.canopy_coverage,
    )
    # Recombine with the canopy-adjusted HVAC
    energy_kwh_adjusted = (
        hvac_adj
        + breakdown["lighting_equipment_kwh"]
        + breakdown["base_load_kwh"]
    )

    emission_factor = assumptions.get("environmental", {}).get(
        "emission_factor_energy", 0.58,
    )
    carbon = operational_carbon(energy_kwh_adjusted, emission_factor)

    # Phase 11 — productive vs stranded
    split = productive_stranded_carbon(carbon, occupancy)

    # Phase 11 — life-cycle
    amortised = embodied_amortised(floor_area, MATERIAL_INTENSITY_REPURPOSE)
    maint_carbon = maintenance_carbon_annual(amortised["embodied_carbon_total_tco2e"])

    # Phase 11 — UHI proxy
    uhi = calculate_surface_temp_delta(
        canopy_coverage_ratio=ctx.canopy_coverage,
        is_hard_surface=True,
    )

    # --- Demographic mismatch ---
    mismatch = None
    if ctx.catchment_population_profile:
        target_demographics = subtype_cfg.get("target_demographics", []) or []
        mismatch = demographic_mismatch(ctx.catchment_population_profile, target_demographics)

    diversity = ctx.neighborhood_diversity

    return {
        "asset_id": asset["asset_id"],
        "year": year,
        "subtype": subtype,
        "occupancy_rate": occupancy,
        "vacancy_rate": vacancy_rate,
        "vacancy_duration_months": vacancy_duration,
        "footfall_daily": footfall,
        "rental_income_per_visit_proxy": rental_income_per_visit,
        "rental_income_rm": rental_income,
        "noi_rm": noi,
        "noi_yield": noi_yield,
        "maintenance_surge_rm": maintenance_surge,
        "effective_demand": ctx.huff_effective_demand,
        "effective_demand_m2": demand_m2,
        "effective_supply": effective_supply,
        "dsr": dsr,
        "shade_proxy_score": shade,
        "energy_kwh": energy_kwh_adjusted,
        "energy_kwh_hvac": hvac_adj,
        "energy_kwh_lighting_equipment": breakdown["lighting_equipment_kwh"],
        "energy_kwh_base_load": breakdown["base_load_kwh"],
        "carbon_operational_tco2e": carbon,
        "carbon_productive_tco2e": split["carbon_productive_tco2e"],
        "carbon_stranded_tco2e": split["carbon_stranded_tco2e"],
        "stranded_carbon_ratio": split["stranded_carbon_ratio"],
        "embodied_carbon_total_tco2e": amortised["embodied_carbon_total_tco2e"],
        "embodied_carbon_amortised_tco2e": amortised["embodied_carbon_amortised_tco2e"],
        "maintenance_carbon_tco2e": maint_carbon,
        "surface_temp_delta_c": uhi,
        "demographic_mismatch": mismatch,
        "neighborhood_diversity": diversity,
        "accessibility_score": ctx.accessibility_score,
        "metric_source": "derived",
        "model_version": __version__,
    }


def _get_metric_row(ctx: DerivationContext, asset_id: str, year: int):
    metrics = ctx.business["asset_metrics"]
    row = metrics[
        (metrics["asset_id"] == asset_id) & (metrics["year"] == year)
    ]
    if row.empty:
        return None
    return row.iloc[0]


def _isnan(v) -> bool:
    try:
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return False