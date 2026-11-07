"""Layer 2 — Low Value Realisation.

Whether the asset fails to realise its intended value.
Layer 1 asks "is it below benchmark"; Layer 2 asks "is it producing the
value it was built for".

Phase 16 (Gemini review fix):
  - residential branch added. Previously no branch existed, so an
    unsold developer-held unit could never satisfy "l1 AND l2" and
    never reached deadspace_candidate, regardless of how completely
    it failed to house anyone. This was the single largest dead
    path in the detection pipeline.
"""

DEFAULTS = {
    "noi_below": 0.0,
    "service_coverage_below": 0.60,
    "maintenance_surge_ratio_above": 1.5,
    "walking_coverage_10min_below": 0.30,
    # Phase 16 — residential
    "residential_occupancy_floor": 0.05,
    "residential_partial_occupancy": 0.40,
    "residential_long_vacancy_months": 24,
}


def evaluate(asset_type: str, asset: dict, metrics: dict,
             thresholds: dict = None) -> dict:
    t = {**DEFAULTS, **(thresholds or {})}
    reasons = []

    if asset_type == "commercial":
        noi = metrics.get("noi_rm")
        if noi is not None and noi < t["noi_below"]:
            reasons.append("negative_noi")

        surge = metrics.get("maintenance_surge_rm")
        base = asset.get("maintenance_annual_rm")
        if surge is not None and base and float(base) > 0:
            ratio = float(surge) / float(base)
            if ratio > t["maintenance_surge_ratio_above"]:
                reasons.append("maintenance_surge_high")

    elif asset_type == "community_facility":
        cov = metrics.get("service_coverage")
        if cov is not None and float(cov) < t["service_coverage_below"]:
            reasons.append("insufficient_coverage")

    elif asset_type == "green_space":
        cov = metrics.get("coverage_ratio_10min_walk")
        canopy = metrics.get("canopy_coverage")
        if cov is not None and float(cov) < t["walking_coverage_10min_below"]:
            if canopy is not None and float(canopy) > 0.05:
                reasons.append("low_accessibility_high_ecological_value")
            else:
                reasons.append("low_accessibility")

    elif asset_type == "undeveloped_parcel":
        gap = metrics.get("demand_supply_gap")
        if gap is not None and float(gap) < 0:
            reasons.append("weak_future_demand")

    elif asset_type == "residential":
        # A residential asset that was built to house people but
        # houses none is failing its fundamental mandate.
        occ = metrics.get("occupancy_rate")
        vac = metrics.get("vacancy_duration_months")

        occ_f = None
        try:
            if occ is not None:
                occ_f = float(occ)
        except (TypeError, ValueError):
            occ_f = None

        if occ_f is not None and occ_f <= t["residential_occupancy_floor"]:
            reasons.append("built_value_not_realized")
        elif (
            vac is not None
            and float(vac) >= t["residential_long_vacancy_months"]
            and occ_f is not None
            and occ_f < t["residential_partial_occupancy"]
        ):
            reasons.append("built_value_not_realized")

    return {"triggered": len(reasons) > 0, "reasons": reasons}
