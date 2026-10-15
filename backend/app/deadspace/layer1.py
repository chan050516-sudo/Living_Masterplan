"""Layer 1 — Underperformance.

Determine whether the asset is significantly below applicable
benchmark.

Phase 11 change: adds a stranded-carbon diagnostic flag. An asset
whose operational carbon is mostly wasted (because it is underused)
is flagged even if it does not breach any of the occupancy /
utilisation thresholds directly.
"""

DEFAULTS = {
    "occupancy_rate_below": 0.50,
    "vacancy_duration_above_months": 12.0,
    "utilisation_rate_below": 0.40,
    "dsr_below": 0.80,
    "demand_supply_gap_below": 0.0,
    "walking_coverage_5min_below": 0.20,
    "driving_coverage_10min_below": 0.50,
    "demographic_mismatch_above": 0.50,
    "neighborhood_diversity_below": 0.30,
    # Phase 11 — stranded carbon diagnostics
    "stranded_carbon_ratio_above": 0.50,
    "stranded_carbon_floor_tco2e": 100.0,
}


def evaluate(asset_type: str, metrics: dict, thresholds: dict = None) -> dict:
    t = {**DEFAULTS, **(thresholds or {})}
    reasons = []

    if asset_type == "commercial":
        occ = metrics.get("occupancy_rate")
        if occ is not None and occ < t["occupancy_rate_below"]:
            reasons.append("low_occupancy")

        vac = metrics.get("vacancy_duration_months")
        if vac is not None and vac > t["vacancy_duration_above_months"]:
            reasons.append("long_vacancy")

        dsr = metrics.get("dsr")
        if dsr is not None and dsr < t["dsr_below"]:
            reasons.append("dsr_below_threshold")

        wcov = metrics.get("coverage_ratio_5min_walk")
        if wcov is not None and wcov < t["walking_coverage_5min_below"]:
            reasons.append("walking_accessibility_deficit")

        dcov = metrics.get("coverage_ratio_10min_drive")
        if dcov is not None and dcov < t["driving_coverage_10min_below"]:
            reasons.append("driving_accessibility_deficit")

        mismatch = metrics.get("demographic_mismatch")
        if mismatch is not None and mismatch > t["demographic_mismatch_above"]:
            reasons.append("demographic_mismatch")

        diversity = metrics.get("neighborhood_diversity")
        if diversity is not None and diversity < t["neighborhood_diversity_below"]:
            reasons.append("low_neighborhood_diversity")

        _check_stranded(reasons, metrics, t)

    elif asset_type == "community_facility":
        util = metrics.get("utilisation_rate")
        if util is not None and util < t["utilisation_rate_below"]:
            reasons.append("low_utilisation")

        wcov = metrics.get("coverage_ratio_5min_walk")
        if wcov is not None and wcov < t["walking_coverage_5min_below"]:
            reasons.append("walking_accessibility_deficit")

        _check_stranded(reasons, metrics, t)

    elif asset_type == "residential":
        _check_stranded(reasons, metrics, t)

    elif asset_type == "undeveloped_parcel":
        gap = metrics.get("demand_supply_gap")
        if gap is not None and gap < t["demand_supply_gap_below"]:
            reasons.append("negative_demand_supply_gap")

    return {
        "triggered": len(reasons) > 0,
        "reasons": reasons,
    }


def _check_stranded(reasons: list, metrics: dict, t: dict) -> None:
    """
    Flag an asset whose operational carbon is mostly wasted.

    Requires BOTH:
      - stranded ratio above the threshold (default 50%), AND
      - absolute stranded carbon above the floor (default 100 tCO2e)

    The floor prevents small assets with high ratios but trivial
    absolute emissions from dominating the urgency list.
    """
    ratio = metrics.get("stranded_carbon_ratio")
    absolute = metrics.get("carbon_stranded_tco2e")

    if ratio is None or absolute is None:
        return
    try:
        r = float(ratio)
        a = float(absolute)
    except (TypeError, ValueError):
        return

    if r > t["stranded_carbon_ratio_above"] and a > t["stranded_carbon_floor_tco2e"]:
        reasons.append("high_stranded_carbon")