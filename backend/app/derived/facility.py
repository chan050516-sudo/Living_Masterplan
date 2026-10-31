"""Community facility derived metrics — subtype-aware.

Phase 11 additions:
  - Energy sub-system split.
  - Productive vs stranded carbon (utilisation-based).
  - Life-cycle carbon.
  - Landsat 8 Level-2 temperature is attached by the shared derivation engine.
"""

import math
from .. import __version__
from .context import DerivationContext
from ..taxonomy import get_subtype_or_default, default_subtype_for
from .demand_mismatch import demographic_mismatch
from .environmental import (
    energy_from_subtype,
    operational_carbon,
    breakdown_energy,
    apply_canopy_hvac_relief,
    productive_stranded_carbon,
    embodied_amortised,
    maintenance_carbon_annual,
    embodied_amortised_for_subtype,
    MATERIAL_INTENSITY_REPURPOSE,
)


def derive_facility(ctx: DerivationContext) -> dict:
    asset = ctx.asset
    year = ctx.year
    assumptions = ctx.assumptions

    subtype = asset.get("subtype") or default_subtype_for("community_facility")
    subtype_cfg = get_subtype_or_default(subtype)

    metrics = ctx.business["asset_metrics"]
    row = metrics[
        (metrics["asset_id"] == asset["asset_id"]) &
        (metrics["year"] == year)
    ]
    raw = row.iloc[0] if not row.empty else None

    def _get(col):
        if raw is None:
            return None
        v = raw.get(col)
        if v is None:
            return None
        try:
            if math.isnan(float(v)):
                return None
        except (TypeError, ValueError):
            return None
        return float(v)

    utilisation = _get("utilisation_rate")

    service_coverage = None
    if ctx.walking_profile:
        service_coverage = ctx.walking_profile.get("coverage_ratio_10min")

    # Cost per user
    opex = asset.get("opex_annual_rm")
    maintenance = asset.get("maintenance_annual_rm")
    annual_users = None
    if utilisation is not None and asset.get("capacity"):
        annual_users = utilisation * float(asset["capacity"]) * 365.0

    cost_per_user = None
    if annual_users and annual_users > 0:
        total = 0.0
        if opex is not None:
            total += float(opex)
        if maintenance is not None:
            total += float(maintenance)
        cost_per_user = total / annual_users

    # --- Energy / carbon ---
    floor_area = float(asset.get("floor_area_m2") or 0.0)
    energy_kwh = energy_from_subtype(subtype, floor_area, default_intensity=120.0)

    breakdown = breakdown_energy(energy_kwh, "community_facility", assumptions)
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

    # Phase 11 — productive vs stranded using utilisation
    split = productive_stranded_carbon(carbon, utilisation)

    # Phase 11 — life-cycle
    amortised = embodied_amortised_for_subtype(floor_area, subtype)
    maint_carbon = maintenance_carbon_annual(amortised["embodied_carbon_total_tco2e"])

    # --- Demographic mismatch ---
    mismatch = None
    if ctx.catchment_population_profile:
        target_demographics = subtype_cfg.get("target_demographics", []) or []
        mismatch = demographic_mismatch(
            ctx.catchment_population_profile, target_demographics,
        )

    return {
        "asset_id": asset["asset_id"],
        "year": year,
        "subtype": subtype,
        "utilisation_rate": utilisation,
        "service_coverage": service_coverage,
        "cost_per_user_rm": cost_per_user,
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
        "surface_temp_delta_c": None,
        "demographic_mismatch": mismatch,
        "neighborhood_diversity": ctx.neighborhood_diversity,
        "accessibility_score": ctx.accessibility_score,
        "metric_source": "derived",
        "model_version": __version__,
    }
