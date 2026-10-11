"""Human-readable evidence strings for the diagnosis card.

Each string MUST be safe to display in UI without further formatting.
"""


def _fmt(v, decimals=2):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if abs(f) >= 1000:
        return f"{f:,.0f}"
    return f"{round(f, decimals)}"


def build_evidence(asset_type: str, metrics: dict) -> list:
    lines = []

    def _add(label, key, suffix="", decimals=2):
        v = _fmt(metrics.get(key), decimals)
        if v is not None:
            lines.append(f"{label}: {v}{suffix}")

    if asset_type == "commercial":
        occ = metrics.get("occupancy_rate")
        if occ is not None:
            lines.append(f"Occupancy: {round(occ * 100, 1)}%")
        vac = metrics.get("vacancy_duration_months")
        if vac is not None:
            lines.append(f"Vacancy: {int(vac)} months")
        _add("Effective demand", "effective_demand")
        _add("Effective supply", "effective_supply")
        _add("DSR", "dsr")
        _add("NOI (RM)", "noi_rm")
        _add("Rental income per visit (RM/person/day)", "rental_income_per_visit_proxy")
        _add("Maintenance surge (RM)", "maintenance_surge_rm")
        _add("Accessibility score", "accessibility_score", decimals=1)
        _add("Shade proxy score", "shade_proxy_score", decimals=1)

    elif asset_type == "community_facility":
        util = metrics.get("utilisation_rate")
        if util is not None:
            lines.append(f"Utilisation: {round(util * 100, 1)}%")
        cov = metrics.get("service_coverage")
        if cov is not None:
            lines.append(f"Service coverage: {round(cov * 100, 1)}%")
        _add("Cost per user (RM)", "cost_per_user_rm")
        _add("Accessibility score", "accessibility_score", decimals=1)

    elif asset_type == "green_space":
        g = metrics.get("green_coverage")
        if g is not None:
            lines.append(f"Green coverage: {round(g * 100, 1)}%")
        c = metrics.get("canopy_coverage")
        if c is not None:
            lines.append(f"Canopy coverage: {round(c * 100, 1)}%")
        _add("Green space per capita (m2)", "green_per_capita_m2")
        _add("Accessibility score", "accessibility_score", decimals=1)
        _add("Shade proxy score", "shade_proxy_score", decimals=1)

    elif asset_type == "undeveloped_parcel":
        _add("Developable area (m2)", "developable_area_m2")
        _add("Potential GFA (m2)", "potential_gfa_m2")
        _add("Demand-supply gap", "demand_supply_gap")
        _add("Infrastructure cost (RM)", "infrastructure_cost_rm")
        _add("Accessibility score", "accessibility_score", decimals=1)

    elif asset_type == "residential":
        occ = metrics.get("occupancy_rate")
        if occ is not None:
            lines.append(f"Occupancy: {round(occ * 100, 1)}%")
        _add("Accessibility score", "accessibility_score", decimals=1)

    return lines