"""Layer 1 — Underperformance.

Determine whether the asset is significantly below applicable
benchmark. Layer 1 now uses pure observed / derived flags rather
than a single score.

Phase 3 change: removed the dependency on performance_score. The
flags-based approach is peer-relative and more directly interpretable.
"""

DEFAULTS = {
    # Peer-relative thresholds. Values here are fallbacks used when
    # peer distribution is unavailable.
    "occupancy_rate_below": 0.50,
    "vacancy_duration_above_months": 12.0,
    "utilisation_rate_below": 0.40,
    "dsr_below": 0.80,
    "demand_supply_gap_below": 0.0,
    "walking_coverage_5min_below": 0.20,
    # FIX: raised from 0.40. At township scale (30 km/h), a 10-min
    # drive easily covers 5 km, so 0.40 almost never triggered. 0.50
    # is a more meaningful "sparse driving catchment" threshold.
    "driving_coverage_10min_below": 0.50,
    # Diagnostic indicators (derived per asset, see derived/commercial.py)
    "demographic_mismatch_above": 0.50,
    "neighborhood_diversity_below": 0.30,
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

        # Diagnostic flags (FLAG_WEIGHTS already reserved entries for these;
        # previously nothing generated them, so they never entered urgency).
        mismatch = metrics.get("demographic_mismatch")
        if mismatch is not None and mismatch > t["demographic_mismatch_above"]:
            reasons.append("demographic_mismatch")

        diversity = metrics.get("neighborhood_diversity")
        if diversity is not None and diversity < t["neighborhood_diversity_below"]:
            reasons.append("low_neighborhood_diversity")

    elif asset_type == "community_facility":
        util = metrics.get("utilisation_rate")
        if util is not None and util < t["utilisation_rate_below"]:
            reasons.append("low_utilisation")

        wcov = metrics.get("coverage_ratio_5min_walk")
        if wcov is not None and wcov < t["walking_coverage_5min_below"]:
            reasons.append("walking_accessibility_deficit")

    elif asset_type == "undeveloped_parcel":
        gap = metrics.get("demand_supply_gap")
        if gap is not None and gap < t["demand_supply_gap_below"]:
            reasons.append("negative_demand_supply_gap")

    return {
        "triggered": len(reasons) > 0,
        "reasons": reasons,
    }
    # NOTE: the old `urgency_contribution` field was computed here but
    # never consumed by detector.py; removed as dead code.