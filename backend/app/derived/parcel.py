"""Undeveloped parcel derived metrics — P-05."""

import math
from .context import DerivationContext


def derive_parcel(ctx: DerivationContext) -> dict:
    asset = ctx.asset
    year = ctx.year

    land_area = asset.get("land_area_m2")
    restricted = _restricted_area(ctx)
    land_area_f = float(land_area) if land_area else 0.0

    developable = None
    if land_area_f > 0:
        developable = max(0.0, land_area_f - restricted)

    # FAR from benchmarks or assumption
    far = _far_for_land_use(ctx)
    potential_gfa = None
    if developable is not None and far:
        potential_gfa = developable * far

    # Demand-supply gap
    total_pop = _total_population(ctx)
    # Proxy: demand = population * commercial_per_capita_sum
    demand = total_pop * _commercial_demand_coefficient(ctx)   # m²
    supply = _commercial_supply(ctx)                            # m²
    gap = demand - supply                                        # m²

    # Infrastructure cost: distance-based
    infrastructure_cost = _infrastructure_cost(ctx)

    accessibility = ctx.accessibility_score

    return {
        "asset_id": asset["asset_id"],
        "year": year,
        "developable_area_m2": developable,
        "potential_gfa_m2": potential_gfa,
        "demand_supply_gap": gap,
        "infrastructure_cost_rm": infrastructure_cost,
        "accessibility_score": accessibility,
        "metric_source": "derived",
        "model_version": "0.3.0",
    }


def _restricted_area(ctx: DerivationContext) -> float:
    # For demo: no restricted area
    return 0.0


def _far_for_land_use(ctx: DerivationContext) -> float:
    # Planning assumption: FAR = 1.5 for undeveloped parcels in this zone
    return 1.5


def _total_population(ctx: DerivationContext) -> float:
    pop = ctx.geometry.get("population", {}).get("analysis")
    if pop is None or pop.empty:
        return 0.0
    return float(pop["total_population"].sum())


def _commercial_demand_coefficient(ctx: DerivationContext) -> float:
    """m²/person — sum of per-capita commercial demand across categories."""
    coeffs = ctx.assumptions.get("demand", {}).get("commercial_per_capita_m2", {})
    return sum(coeffs.values()) if coeffs else 0.48


def _commercial_supply(ctx: DerivationContext) -> float:
    assets = ctx.business["assets"]
    commercial = assets[assets["asset_type"] == "commercial"]
    total = commercial["lettable_area_m2"].fillna(0).sum()
    return float(total)


def _infrastructure_cost(ctx: DerivationContext) -> float:
    # Placeholder: RM 200 per m2 of developable area
    land_area = ctx.asset.get("land_area_m2")
    if not land_area:
        return 0.0
    return float(land_area) * 200.0