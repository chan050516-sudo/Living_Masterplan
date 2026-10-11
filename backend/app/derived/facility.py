"""Community facility derived metrics."""

import math
from .context import DerivationContext
from .accessibility import effective_distance, gaussian_falloff


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
    service_coverage = _service_coverage(ctx)

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
        "model_version": "0.3.2",
    }


def _service_coverage(ctx: DerivationContext) -> float:
    """
    Fraction of target population within walking catchment.

    Uses the precomputed distance matrix when available (Fix 1+4).
    """
    asset_node = ctx.asset.get("_walk_node")
    if not asset_node:
        return 0.0

    pop_layer = ctx.geometry.get("population", {})
    if not pop_layer:
        return 0.0
    pop_gdf = pop_layer.get("analysis")
    if pop_gdf is None or pop_gdf.empty:
        return 0.0

    threshold = ctx.assumptions.get("accessibility", {}).get("falloff_threshold_m", 800.0)

    total_pop = 0.0
    covered_pop = 0.0

    if ctx.distance_matrix is not None and asset_node in ctx.distance_matrix:
        row = ctx.distance_matrix[asset_node]
        for _, pop in pop_gdf.iterrows():
            pop_node = pop.get("_nearest_node")
            if not pop_node:
                continue
            pop_count = float(pop.get("total_population", 0))
            total_pop += pop_count
            d_eff = row.get(pop_node)
            f = gaussian_falloff(d_eff, threshold)
            covered_pop += pop_count * f
    else:
        # Fallback: single-pair queries
        G = ctx.graph
        for _, pop in pop_gdf.iterrows():
            pop_node = pop.get("_nearest_node")
            if not pop_node:
                continue
            pop_count = float(pop.get("total_population", 0))
            total_pop += pop_count
            d_eff = effective_distance(G, asset_node, pop_node)
            f = gaussian_falloff(d_eff, threshold)
            covered_pop += pop_count * f

    if total_pop <= 0:
        return 0.0
    return covered_pop / total_pop