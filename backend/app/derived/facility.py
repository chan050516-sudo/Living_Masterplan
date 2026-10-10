"""Community facility derived metrics — F-02."""

import math
from .context import DerivationContext


def derive_facility(ctx: DerivationContext) -> dict:
    asset = ctx.asset
    year = ctx.year

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

    utilisation = _get("utilisation_rate")
    accessibility = ctx.accessibility_score

    # Service coverage: target population served / target population
    service_coverage = _service_coverage(ctx)

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

    return {
        "asset_id": asset["asset_id"],
        "year": year,
        "utilisation_rate": utilisation,
        "service_coverage": service_coverage,
        "cost_per_user_rm": cost_per_user,
        "accessibility_score": accessibility,
        "metric_source": "derived",
        "model_version": "0.3.0",
    }


def _service_coverage(ctx: DerivationContext) -> float:
    """
    Fraction of target population within 10-min walk.
    Uses demand nodes from population.geojson and the graph.
    """
    from .accessibility import effective_distance, gaussian_falloff

    G = ctx.graph
    asset_id = ctx.asset["asset_id"]

    # Find the asset's nearest node (from context — set by engine)
    asset_node = ctx.asset.get("_walk_node")
    if not asset_node:
        return 0.0

    pop_layer = ctx.geometry.get("population", {})
    if not pop_layer:
        return 0.0
    pop_gdf = pop_layer.get("analysis")
    if pop_gdf is None or pop_gdf.empty:
        return 0.0

    # Sum population weighted by proximity
    total_pop = 0.0
    covered_pop = 0.0
    gamma = ctx.assumptions.get("accessibility", {}).get("canopy_impedance_gamma", 0.3)
    threshold = ctx.assumptions.get("accessibility", {}).get("falloff_threshold_m", 800.0)

    for _, pop in pop_gdf.iterrows():
        pop_node = pop.get("_nearest_node")
        if not pop_node:
            continue
        pop_count = float(pop.get("total_population", 0))
        total_pop += pop_count
        d_eff = effective_distance(G, asset_node, pop_node, gamma=gamma)
        f = gaussian_falloff(d_eff, threshold)
        covered_pop += pop_count * f

    if total_pop <= 0:
        return 0.0
    return covered_pop / total_pop