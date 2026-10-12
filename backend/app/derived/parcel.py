"""Undeveloped parcel derived metrics — Phase 4.

Changes:
  - Commercial demand coefficient now read from taxonomy (per-subtype
    sum) rather than from a hardcoded scalar in assumptions.yml.
  - Demand uses the reachable walking-catchment population, not the
    total mock population. This avoids inflating demand by residents
    who cannot realistically reach the parcel on foot.
  - FAR still falls back to a placeholder; see _far_for_land_use.
"""

import math
from .context import DerivationContext
from ..taxonomy import get_taxonomy


def derive_parcel(ctx: DerivationContext) -> dict:
    asset = ctx.asset
    year = ctx.year

    land_area = asset.get("land_area_m2")
    restricted = _restricted_area(ctx)
    land_area_f = float(land_area) if land_area else 0.0

    developable = None
    if land_area_f > 0:
        developable = max(0.0, land_area_f - restricted)

    far = _far_for_land_use(ctx)
    potential_gfa = None
    if developable is not None and far:
        potential_gfa = developable * far

    # Reachable population from walking profile
    reachable_pop = 0.0
    if ctx.walking_profile:
        reachable_pop = float(ctx.walking_profile.get("reachable_population") or 0.0)

    demand = reachable_pop * _commercial_demand_coefficient()
    supply = _commercial_supply(ctx)
    gap = demand - supply

    infrastructure_cost = _infrastructure_cost(ctx)
    accessibility = ctx.accessibility_score

    return {
        "asset_id": asset["asset_id"],
        "year": year,
        "subtype": asset.get("subtype") or "vacant",
        "developable_area_m2": developable,
        "potential_gfa_m2": potential_gfa,
        "demand_supply_gap": gap,
        "infrastructure_cost_rm": infrastructure_cost,
        "accessibility_score": accessibility,
        "metric_source": "derived",
        "model_version": "0.4.0",
    }


def _restricted_area(ctx: DerivationContext) -> float:
    # NOTE: placeholder. Real implementation should read from a
    # constraints layer (protected zones, drainage easements, setbacks).
    return 0.0


def _far_for_land_use(ctx: DerivationContext) -> float:
    # NOTE: hardcoded placeholder until zoning data is available.
    return 1.5


def _commercial_demand_coefficient() -> float:
    """
    Sum of per-capita commercial demand across all commercial subtypes.
    Value is in m²/person. Read from taxonomy so it stays consistent
    with the Huff demand pools.
    """
    tax = get_taxonomy()
    subtypes = tax.get("subtypes", {})
    total = 0.0
    for name, defn in subtypes.items():
        if defn.get("asset_class") == "commercial":
            total += defn.get("demand_coefficient_m2_per_person", 0.0)
    return total if total > 0 else 0.48


def _commercial_supply(ctx: DerivationContext) -> float:
    assets = ctx.business["assets"]
    commercial = assets[assets["asset_type"] == "commercial"]
    total = commercial["lettable_area_m2"].fillna(0).sum()
    return float(total)


def _infrastructure_cost(ctx: DerivationContext) -> float:
    # NOTE: placeholder of RM 200/m² of land.
    land_area = ctx.asset.get("land_area_m2")
    if not land_area:
        return 0.0
    return float(land_area) * 200.0