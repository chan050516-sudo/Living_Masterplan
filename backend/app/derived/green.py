"""Green space derived metrics — G-01."""

import math
from .context import DerivationContext


def derive_green(ctx: DerivationContext) -> dict:
    asset = ctx.asset
    year = ctx.year

    # Green area from green_blue.geojson
    green_area = _green_area(ctx)
    land_area = asset.get("land_area_m2")
    canopy_area = _canopy_area(ctx)

    green_coverage = None
    if green_area is not None and land_area and float(land_area) > 0:
        green_coverage = green_area / float(land_area)

    canopy_coverage = None
    if canopy_area is not None and land_area and float(land_area) > 0:
        canopy_coverage = canopy_area / float(land_area)

    # Green per capita
    total_pop = _total_population(ctx)
    green_per_capita = None
    if green_area is not None and total_pop > 0:
        green_per_capita = green_area / total_pop

    accessibility = ctx.accessibility_score

    # Thermal exposure: f(surface_temp, canopy, impervious)
    thermal = _thermal_exposure(canopy_coverage)

    return {
        "asset_id": asset["asset_id"],
        "year": year,
        "green_coverage": green_coverage,
        "canopy_coverage": canopy_coverage,
        "green_per_capita_m2": green_per_capita,
        "accessibility_score": accessibility,
        "thermal_exposure": thermal,
        "metric_source": "derived",
        "model_version": "0.3.0",
    }


def _green_area(ctx: DerivationContext) -> float:
    gb = ctx.geometry.get("green_blue", {}).get("analysis")
    if gb is None or gb.empty:
        return None
    match = gb[gb["asset_id"] == ctx.asset["asset_id"]]
    if match.empty:
        return None
    return float(match.iloc[0].get("area_m2", 0))


def _canopy_area(ctx: DerivationContext) -> float:
    gb = ctx.geometry.get("green_blue", {}).get("analysis")
    if gb is None or gb.empty:
        return None
    match = gb[gb["asset_id"] == ctx.asset["asset_id"]]
    if match.empty:
        return None
    v = match.iloc[0].get("canopy_m2")
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _total_population(ctx: DerivationContext) -> float:
    pop = ctx.geometry.get("population", {}).get("analysis")
    if pop is None or pop.empty:
        return 0.0
    return float(pop["total_population"].sum())


def _thermal_exposure(canopy_coverage) -> float:
    if canopy_coverage is None:
        return 80.0
    return max(0.0, min(100.0, 80.0 - 100.0 * canopy_coverage))