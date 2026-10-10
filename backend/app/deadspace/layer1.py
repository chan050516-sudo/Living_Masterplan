"""Layer 1 — Underperformance.

Determine whether the asset is significantly below applicable benchmark.
Returns (triggered, reasons) where reasons is a list of string codes.
"""

# Thresholds are read from assumptions.yml['deadspace']['layer1']
DEFAULTS = {
    "overall_score_below": 40.0,
    "occupancy_rate_below": 0.50,
    "vacancy_duration_above_months": 12.0,
    "utilisation_rate_below": 0.40,
    "dsr_below": 0.80,
    "demand_supply_gap_below": 0.0,
}


def evaluate(asset_type: str, metrics: dict, thresholds: dict = None) -> dict:
    t = {**DEFAULTS, **(thresholds or {})}
    reasons = []

    score = metrics.get("performance_score")
    if score is not None and score < t["overall_score_below"]:
        reasons.append("low_overall_score")

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

    elif asset_type == "community_facility":
        util = metrics.get("utilisation_rate")
        if util is not None and util < t["utilisation_rate_below"]:
            reasons.append("low_utilisation")

    elif asset_type == "undeveloped_parcel":
        gap = metrics.get("demand_supply_gap")
        if gap is not None and gap < t["demand_supply_gap_below"]:
            reasons.append("negative_demand_supply_gap")

    # green_space and residential do not use Layer 1 in this iteration

    return {"triggered": len(reasons) > 0, "reasons": reasons}