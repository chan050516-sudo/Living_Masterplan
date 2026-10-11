"""Layer 2 — Low Value Realisation.

Whether the asset fails to realise its intended value.
Layer 1 asks "is it below benchmark"; Layer 2 asks "is it producing the
value it was built for".
"""

DEFAULTS = {
    "noi_below": 0.0,
    "service_coverage_below": 0.60,
    "maintenance_surge_ratio_above": 1.5,
    "accessibility_below": 50.0,
}


def evaluate(asset_type: str, asset: dict, metrics: dict, thresholds: dict = None) -> dict:
    t = {**DEFAULTS, **(thresholds or {})}
    reasons = []

    if asset_type == "commercial":
        noi = metrics.get("noi_rm")
        if noi is not None and noi < t["noi_below"]:
            reasons.append("negative_noi")

        # Maintenance surge ratio
        surge = metrics.get("maintenance_surge_rm")
        base = asset.get("maintenance_annual_rm")
        if surge is not None and base and float(base) > 0:
            ratio = float(surge) / float(base)
            if ratio > t["maintenance_surge_ratio_above"]:
                reasons.append("maintenance_surge_high")

    elif asset_type == "community_facility":
        cov = metrics.get("service_coverage")
        if cov is not None and cov < t["service_coverage_below"]:
            reasons.append("insufficient_coverage")

    elif asset_type == "green_space":
        acc = metrics.get("accessibility_score")
        canopy = metrics.get("canopy_coverage")
        # High ecological value but poor access = improvement opportunity
        if acc is not None and acc < t["accessibility_below"]:
            if canopy is not None and canopy > 0.05:
                reasons.append("low_accessibility_high_ecological_value")
            else:
                reasons.append("low_accessibility")

    elif asset_type == "undeveloped_parcel":
        # Weak future demand signal from negative gap and low feasibility
        gap = metrics.get("demand_supply_gap")
        if gap is not None and gap < 0:
            reasons.append("weak_future_demand")

    return {"triggered": len(reasons) > 0, "reasons": reasons}