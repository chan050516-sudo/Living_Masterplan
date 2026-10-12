"""Community facility derived metrics — subtype-aware.

Phase 4 changes:
  - Subtype-specific utilisation benchmark and is_core_amenity flag.
  - Service coverage = 10-min walking catchment ratio.
  - Carbon computed from subtype energy intensity.
  - Demographic mismatch between the facility subtype and its catchment.

FIX: when no asset_metrics row exists for the given year, the deriver
now returns None-valued fields instead of raising. This matches
commercial/residential behaviour and prevents one missing row from
aborting the whole B3 pass.
"""

import math
from .. import __version__
from .context import DerivationContext
from ..taxonomy import get_subtype_or_default, default_subtype_for
from .demand_mismatch import demographic_mismatch
from .environmental import energy_from_subtype, operational_carbon


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

    # Service coverage = 10-min walking catchment ratio.
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

    # --- Carbon (subtype-aware) ---
    floor_area = float(asset.get("floor_area_m2") or 0.0)
    energy_kwh = energy_from_subtype(subtype, floor_area, default_intensity=120.0)
    carbon = operational_carbon(
        energy_kwh,
        assumptions.get("environmental", {}).get("emission_factor_energy", 0.58),
    )

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
        "energy_kwh": energy_kwh,
        "carbon_operational_tco2e": carbon,
        "demographic_mismatch": mismatch,
        "neighborhood_diversity": ctx.neighborhood_diversity,
        "accessibility_score": ctx.accessibility_score,  # deprecated bridge
        "metric_source": "derived",
        "model_version": __version__,
    }