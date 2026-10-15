"""Residential asset derived metrics — subtype-aware.

Phase 11 additions:
  - Energy sub-system split.
  - Productive vs stranded carbon.
  - Life-cycle carbon.
  - UHI surface temperature proxy (uses explicit canopy field).
"""

import math
from .. import __version__
from .context import DerivationContext
from ..taxonomy import get_subtype_or_default, get_energy_intensity
from .environmental import (
    operational_carbon,
    breakdown_energy,
    apply_canopy_hvac_relief,
    productive_stranded_carbon,
    embodied_amortised,
    maintenance_carbon_annual,
    calculate_surface_temp_delta,
    shade_proxy_score_from_canopy,
    MATERIAL_INTENSITY_REPURPOSE,
)


def derive_residential(ctx: DerivationContext) -> dict:
    asset = ctx.asset
    year = ctx.year
    assumptions = ctx.assumptions

    subtype = asset.get("subtype") or "terrace"
    subtype_cfg = get_subtype_or_default(subtype)  # noqa: F841

    metrics = ctx.business["asset_metrics"]
    row = metrics[
        (metrics["asset_id"] == asset["asset_id"]) &
        (metrics["year"] == year)
    ]
    if row.empty:
        occupancy = None
        energy_kwh = None
    else:
        raw = row.iloc[0]
        occupancy = _num(raw.get("occupancy_rate"))
        energy_kwh = _num(raw.get("energy_kwh"))

    floor_area = asset.get("floor_area_m2")

    if energy_kwh is None and floor_area:
        intensity_benchmark = get_energy_intensity(subtype)
        if intensity_benchmark is not None:
            energy_kwh = float(floor_area) * float(intensity_benchmark)

    energy_intensity = None
    if energy_kwh is not None and floor_area and float(floor_area) > 0:
        energy_intensity = energy_kwh / float(floor_area)

    # Phase 11 — energy breakdown
    energy_kwh = energy_kwh or 0.0
    breakdown = breakdown_energy(energy_kwh, "residential", assumptions)
    hvac_adj = apply_canopy_hvac_relief(
        breakdown["hvac_kwh"], ctx.canopy_coverage,
    )
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
    fa = float(floor_area) if floor_area else 0.0
    amortised = embodied_amortised(fa, MATERIAL_INTENSITY_REPURPOSE)
    maint_carbon = maintenance_carbon_annual(amortised["embodied_carbon_total_tco2e"])

    # Phase 11 — UHI
    uhi = calculate_surface_temp_delta(
        canopy_coverage_ratio=ctx.canopy_coverage,
        is_hard_surface=True,
    )
    shade = shade_proxy_score_from_canopy(ctx.canopy_coverage)

    # --- NOI ---
    rental_income = None
    if not row.empty:
        rental_income = _num(row.iloc[0].get("rental_income_rm"))
    opex = _num(asset.get("opex_annual_rm"))

    maintenance_base = _num(asset.get("maintenance_annual_rm"))
    completion_year = asset.get("completion_year")
    maintenance = maintenance_base
    if (
        maintenance_base is not None
        and completion_year is not None
        and not _isnan(completion_year)
    ):
        alpha = assumptions.get("asset_aging", {}).get("alpha", 0.03)
        years_old = max(0, year - int(completion_year))
        maintenance = maintenance_base * (1.0 + alpha) ** years_old

    noi = None
    if rental_income is not None:
        total_cost = (opex or 0.0) + (maintenance or 0.0)
        noi = rental_income - total_cost

    return {
        "asset_id": asset["asset_id"],
        "year": year,
        "subtype": subtype,
        "occupancy_rate": occupancy,
        "energy_kwh": energy_kwh_adjusted,
        "energy_kwh_hvac": hvac_adj,
        "energy_kwh_lighting_equipment": breakdown["lighting_equipment_kwh"],
        "energy_kwh_base_load": breakdown["base_load_kwh"],
        "energy_intensity_kwh_m2": energy_intensity,
        "noi_rm": noi,
        "carbon_operational_tco2e": carbon,
        "carbon_productive_tco2e": split["carbon_productive_tco2e"],
        "carbon_stranded_tco2e": split["carbon_stranded_tco2e"],
        "stranded_carbon_ratio": split["stranded_carbon_ratio"],
        "embodied_carbon_total_tco2e": amortised["embodied_carbon_total_tco2e"],
        "embodied_carbon_amortised_tco2e": amortised["embodied_carbon_amortised_tco2e"],
        "maintenance_carbon_tco2e": maint_carbon,
        "surface_temp_delta_c": uhi,
        "canopy_coverage": ctx.canopy_coverage,
        "shade_proxy_score": shade,
        "accessibility_score": ctx.accessibility_score,
        "metric_source": "derived",
        "model_version": __version__,
    }


def _num(v):
    if v is None:
        return None
    try:
        f = float(v)
        if math.isnan(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _isnan(v) -> bool:
    try:
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return False