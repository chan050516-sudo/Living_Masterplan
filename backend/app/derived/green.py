"""Green space derived metrics — subtype-aware.

Phase 4 changes:
  - Subtype-specific canopy benchmark.
  - green_per_capita uses the walking catchment population (reachable),
    not the total mock population, to avoid the "12 km² parcel" effect.
  - Shade proxy from the engine-computed canopy coverage.
"""

import math
from .context import DerivationContext
from ..taxonomy import get_subtype_or_default


def derive_green(ctx: DerivationContext) -> dict:
    asset = ctx.asset
    year = ctx.year

    subtype = asset.get("subtype") or "park"
    subtype_cfg = get_subtype_or_default(subtype)

    green_area = _green_area(ctx)
    land_area = asset.get("land_area_m2")

    green_coverage = None
    if green_area is not None and land_area and float(land_area) > 0:
        green_coverage = green_area / float(land_area)

    # Canopy coverage was computed once by the engine via spatial overlay.
    canopy_coverage = ctx.canopy_coverage

    # green_per_capita uses reachable population from the walking profile,
    # falling back to zero when the profile has no data.
    reachable_pop = 0.0
    if ctx.walking_profile:
        reachable_pop = float(ctx.walking_profile.get("reachable_population") or 0.0)

    green_per_capita = None
    if green_area is not None and reachable_pop > 0:
        green_per_capita = green_area / reachable_pop

    shade = _shade_proxy_score(canopy_coverage)

    return {
        "asset_id": asset["asset_id"],
        "year": year,
        "subtype": subtype,
        "green_coverage": green_coverage,
        "canopy_coverage": canopy_coverage,
        "canopy_ratio_benchmark": subtype_cfg.get("canopy_ratio_benchmark"),
        "green_per_capita_m2": green_per_capita,
        "accessibility_score": ctx.accessibility_score,  # deprecated bridge
        "shade_proxy_score": shade,
        "neighborhood_diversity": ctx.neighborhood_diversity,
        "metric_source": "derived",
        "model_version": "0.4.0",
    }


def _green_area(ctx: DerivationContext) -> float:
    gb = ctx.geometry.get("green_blue", {}).get("analysis")
    if gb is None or gb.empty:
        return None
    match = gb[gb["asset_id"] == ctx.asset["asset_id"]]
    if match.empty:
        return None
    return float(match.iloc[0].get("area_m2", 0))


def _shade_proxy_score(canopy_coverage) -> float:
    if canopy_coverage is None:
        return 0.0
    try:
        c = float(canopy_coverage)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(100.0, 100.0 * c))