"""Per-asset-type component resolvers.

Each resolver turns raw derived metrics into 0-100 component scores using
the three normalization functions from Part 4.2 and benchmarks.yml.
"""

from ..derived.normalize import s_benefit, s_cost, s_target


def _safe_get(row, key):
    v = row.get(key)
    if v is None:
        return None
    try:
        import math
        f = float(v)
        if math.isnan(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def resolve_commercial(asset, metrics, benchmarks):
    b = benchmarks["commercial"]
    return {
        "financial":     s_benefit(_safe_get(metrics, "noi_yield"),
                                   b["noi_yield"]["L"], b["noi_yield"]["U"]),
        "occupancy":     s_benefit(_safe_get(metrics, "occupancy_rate"),
                                   b["occupancy_rate"]["L"], b["occupancy_rate"]["U"]),
        "demand":        s_benefit(_safe_get(metrics, "dsr"),
                                   b["dsr"]["L"], b["dsr"]["U"]),
        "accessibility": _safe_get(metrics, "accessibility_score"),
        "environment": s_benefit(
            _safe_get(metrics, "shade_proxy_score"),
            b["shade_proxy_score"]["L"],
            b["shade_proxy_score"]["U"],
        ),
    }


def resolve_facility(asset, metrics, benchmarks):
    b = benchmarks["community_facility"]
    return {
        "utilisation":     s_target(_safe_get(metrics, "utilisation_rate"),
                                    b["utilisation_rate"]["L"], b["utilisation_rate"]["U"],
                                    b["utilisation_rate"]["H"]),
        "coverage":        s_benefit(_safe_get(metrics, "service_coverage"),
                                     b["service_coverage"]["L"], b["service_coverage"]["U"]),
        "accessibility":   _safe_get(metrics, "accessibility_score"),
        "cost_efficiency": s_cost(_safe_get(metrics, "cost_per_user_rm"),
                                  b["cost_per_user_rm"]["L"], b["cost_per_user_rm"]["U"]),
        "environment":     None,  # not computed in Phase 1
    }


def resolve_green(asset, metrics, benchmarks):
    b = benchmarks["green_space"]
    return {
        "green_coverage": s_benefit(_safe_get(metrics, "green_coverage"),
                                    b["green_coverage"]["L"], b["green_coverage"]["U"]),
        "canopy":         s_benefit(_safe_get(metrics, "canopy_coverage"),
                                    b["canopy_coverage"]["L"], b["canopy_coverage"]["U"]),
        "accessibility":  _safe_get(metrics, "accessibility_score"),
       "thermal": s_benefit(_safe_get(metrics, "shade_proxy_score"),
                                    b["shade_proxy_score"]["L"],
                                    b["shade_proxy_score"]["U"]),
        "usage":          s_benefit(_safe_get(metrics, "green_per_capita_m2"),
                                    b["green_per_capita_m2"]["L"], b["green_per_capita_m2"]["U"]),
    }


def resolve_parcel(asset, metrics, benchmarks):
    b = benchmarks["undeveloped_parcel"]

    developable = _safe_get(metrics, "developable_area_m2")
    land_area = asset.get("land_area_m2")
    feasibility = None
    if developable is not None and land_area and float(land_area) > 0:
        feasibility = float(developable) / float(land_area)

    return {
        "development_feasibility": s_benefit(feasibility,
                                             b["development_feasibility"]["L"],
                                             b["development_feasibility"]["U"]),
        "demand":        s_benefit(_safe_get(metrics, "demand_supply_gap"),
                                   b["demand_supply_gap"]["L"], b["demand_supply_gap"]["U"]),
        "accessibility": _safe_get(metrics, "accessibility_score"),
        "environment":   None,
        "risk":          None,
    }


def resolve_residential(asset, metrics, benchmarks):
    b = benchmarks["residential"]
    # Residential financial proxy: use noi_yield if available
    noi_yield = _safe_get(metrics, "noi_yield")
    financial = None
    if noi_yield is not None and "noi_yield" in b:
        financial = s_benefit(noi_yield, b["noi_yield"]["L"], b["noi_yield"]["U"])

    occ = _safe_get(metrics, "occupancy_rate")
    return {
        "financial":     financial,
        "occupancy":     s_benefit(occ, b["occupancy_rate"]["L"], b["occupancy_rate"]["U"]),
        "demand":        s_benefit(occ, b["occupancy_rate"]["L"], b["occupancy_rate"]["U"]),
        "accessibility": _safe_get(metrics, "accessibility_score"),
        "environment":   s_cost(_safe_get(metrics, "energy_intensity_kwh_m2"),
                                b["energy_intensity_kwh_m2"]["L"], b["energy_intensity_kwh_m2"]["U"]),
    }


RESOLVERS = {
    "commercial":         resolve_commercial,
    "community_facility": resolve_facility,
    "green_space":        resolve_green,
    "undeveloped_parcel": resolve_parcel,
    "residential":        resolve_residential,
}