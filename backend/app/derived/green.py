"""Green space derived metrics — subtype-aware.

Phase 4 changes:
  - Subtype-specific canopy benchmark.
  - green_per_capita uses the walking catchment population (reachable),
    not the total mock population, to avoid the "12 km² parcel" effect.
  - Shade proxy from the engine-computed canopy coverage.

Phase 4b (per-subtype service radius):
  - green_per_capita_m2 denominator is now the population the green
    space ACTUALLY SERVES, not the whole 5 km walking reachable set.
  - A 20,000 m² neighbourhood park serves its 15-minute walk
    catchment, not the entire township. Dividing by
    `reachable_population` (60-80% of the township) systematically
    understates green_per_capita by 2-4x and makes
    `low_green_per_capita` fire on well-served parks.
  - Service radius is per-subtype: parks and corridors serve the
    township scale, pocket parks serve only their immediate
    neighbourhood, sports fields are a mid-range destination.
"""

import math
from .. import __version__
from .context import DerivationContext
from ..taxonomy import get_subtype_or_default
from .environmental import (
    shade_proxy_score_from_canopy,
    calculate_surface_temp_delta,
    effective_canopy_for_uhi
)


# ---------------------------------------------------------------
# Phase 4b — per-subtype service radius
# ---------------------------------------------------------------
# The service radius decides which catchment population becomes the
# denominator of green_per_capita_m2. It is chosen to match how
# PLANMalaysia's 2 m²/person green space standard is defined: the
# population within a reasonable walking distance of the asset, not
# the entire municipality.
#
#   park / green_corridor / water_body — township-scale, 15-min walk
#   sports_field                      — destination use, 10-min walk
#   pocket_park                       — local, 5-min walk
#
# The fallback chain in `_resolve_served_population` handles the case
# where the primary threshold yields 0 population (data gap, network
# fragmentation, or genuinely isolated asset) by trying wider bands
# before giving up.
SERVICE_THRESHOLD_BY_SUBTYPE = {
    "park":            "15min",
    "green_corridor":  "15min",
    "water_body":      "15min",
    "sports_field":    "10min",
    "pocket_park":     "5min",
}

# Fallback order when the primary threshold's population is 0 or
# missing. Always widens first (a broken 5-min band is more likely
# to be a data gap than a genuinely isolated pocket park), then
# narrows as a last resort.
_THRESHOLD_CHAIN = {
    "5min":  ["5min", "10min", "15min"],
    "10min": ["10min", "15min", "5min"],
    "15min": ["15min", "10min", "5min"],
}


def _resolve_served_population(ctx, subtype):
    """
    Return the population the green space serves.

    Resolution order:
      1. Service threshold for this subtype.
      2. Wider threshold fallback (see _THRESHOLD_CHAIN).
      3. reachable_population — the old denominator, used only
         when every minute-band is 0 / missing. This preserves the
         pre-Phase-4b behaviour for assets with a fragmented
         walking network rather than silently producing None.
      4. 0.0 — green_per_capita is undefined (correct outcome when
         no population reaches the asset at all).

    The minute-band keys are the RAW profile keys from
    `accessibility.catchment_profile` — `catchment_population_5min`,
    not `catchment_population_5min_walk`. The `_walk` suffix is
    added later by `_flatten_profiles` on the merged row, not on the
    in-context walking_profile.
    """
    if not ctx.walking_profile:
        return 0.0

    requested = SERVICE_THRESHOLD_BY_SUBTYPE.get(subtype, "15min")
    chain = _THRESHOLD_CHAIN.get(requested, ["15min", "10min", "5min"])

    for band in chain:
        key = f"catchment_population_{band}"
        val = ctx.walking_profile.get(key)
        if val is None:
            continue
        try:
            f = float(val)
        except (TypeError, ValueError):
            continue
        if f > 0:
            return f

    # Every minute band is 0 or missing. Fall back to the old
    # denominator so we do not regress an asset whose network is
    # broken at the minute-band level but does have reachable
    # population.
    val = ctx.walking_profile.get("reachable_population")
    if val is not None:
        try:
            f = float(val)
            if f > 0:
                return f
        except (TypeError, ValueError):
            pass

    return 0.0


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

    # Phase 4b — denominator is the population this green space
    # actually serves, per subtype.
    served_pop = _resolve_served_population(ctx, subtype)
    green_per_capita = None
    if green_area is not None and served_pop > 0:
        green_per_capita = green_area / served_pop

    shade = shade_proxy_score_from_canopy(canopy_coverage)

    canopy_for_uhi = effective_canopy_for_uhi(canopy_coverage, "green_space")
    uhi = calculate_surface_temp_delta(
        canopy_coverage_ratio=canopy_for_uhi,
        is_hard_surface=False,
    )

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
        "surface_temp_delta_c": uhi,
        "metric_source": "derived",
        "model_version": __version__,
    }


def _green_area(ctx: DerivationContext) -> float:
    gb = ctx.geometry.get("green_blue", {}).get("analysis")
    if gb is None or gb.empty:
        return None
    match = gb[gb["asset_id"] == ctx.asset["asset_id"]]
    if match.empty:
        return None
    return float(match.iloc[0].get("area_m2", 0))