"""Human-readable evidence strings for the diagnosis card.

Phase 11 addition: surfaces the productive vs stranded carbon split
and the UHI surface temperature proxy so the LLM (and the UI) can
reference them directly.
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


def build_evidence(asset_type: str, subtype, metrics: dict) -> list:
    lines = []

    def _add(label, key, suffix="", decimals=2):
        v = _fmt(metrics.get(key), decimals)
        if v is not None:
            lines.append(f"{label}: {v}{suffix}")

    if subtype:
        lines.append(f"Subtype: {subtype}")

    _add_carbon_evidence(lines, metrics, asset_type)

    if asset_type == "commercial":
        occ = metrics.get("occupancy_rate")
        if occ is not None:
            lines.append(f"Occupancy: {round(occ * 100, 1)}%")
        vac = metrics.get("vacancy_duration_months")
        if vac is not None:
            lines.append(f"Vacancy: {int(vac)} months")
        _add("NOI (RM, annual)", "noi_rm")
        _add("NOI yield (annual)", "noi_yield", decimals=4)
        _add("DSR", "dsr")
        _add("Demographic mismatch", "demographic_mismatch", decimals=2)
        _add("Neighborhood diversity", "neighborhood_diversity", decimals=2)

        wcov = metrics.get("coverage_ratio_5min_walk")
        if wcov is not None:
            lines.append(f"Walk 5-min coverage: {round(wcov * 100, 1)}%")
        dcov = metrics.get("coverage_ratio_10min_drive")
        if dcov is not None:
            lines.append(f"Drive 10-min coverage: {round(dcov * 100, 1)}%")
        _add("Median walk distance (m)", "median_walk_distance_m")
        _add_subtype_mix_evidence(lines, metrics)

    elif asset_type == "community_facility":
        util = metrics.get("utilisation_rate")
        if util is not None:
            lines.append(f"Utilisation: {round(util * 100, 1)}%")
        cov = metrics.get("service_coverage")
        if cov is not None:
            lines.append(f"Service coverage: {round(cov * 100, 1)}%")
        _add("Cost per user (RM)", "cost_per_user_rm")

        wcov = metrics.get("coverage_ratio_5min_walk")
        if wcov is not None:
            lines.append(f"Walk 5-min coverage: {round(wcov * 100, 1)}%")

    elif asset_type == "residential":
        occ = metrics.get("occupancy_rate")
        if occ is not None and occ <= 0.05:
            lines.append("built_value_not_realized")

    elif asset_type == "green_space":
        g = metrics.get("green_coverage")
        if g is not None:
            lines.append(f"Green coverage: {round(g * 100, 1)}%")
        c = metrics.get("canopy_coverage")
        if c is not None:
            lines.append(f"Canopy coverage: {round(c * 100, 1)}%")
        _add("Green space per capita (m2)", "green_per_capita_m2")

    elif asset_type == "undeveloped_parcel":
        _add("Developable area (m2)", "developable_area_m2")
        _add("Potential GFA (m2)", "potential_gfa_m2")
        _add("Demand-supply gap", "demand_supply_gap")
        _add("Infrastructure cost (RM)", "infrastructure_cost_rm")

    return lines


def _add_subtype_mix_evidence(lines: list, metrics: dict) -> None:
    """
    Surface per-subtype occupancy for mixed-use commercial assets.

    Sorted ascending so the worst-off subtype is listed first —
    that is the one the reader cares about.
    """
    import json as _json
    raw = metrics.get("occupancy_by_subtype_calc_json")
    if raw is None:
        return
    try:
        occ_by = _json.loads(raw) if isinstance(raw, str) else raw
    except (_json.JSONDecodeError, TypeError):
        return
    if not isinstance(occ_by, dict) or len(occ_by) <= 1:
        return

    lines.append("Subtype occupancy:")
    for st, v in sorted(occ_by.items(), key=lambda kv: kv[1]):
        try:
            pct = round(float(v) * 100, 1)
        except (TypeError, ValueError):
            continue
        marker = ""
        try:
            fv = float(v)
            if fv < 0.10:
                marker = " [dead]"
            elif fv < 0.40:
                marker = " [low]"
        except (TypeError, ValueError):
            pass
        lines.append(f"  {st}: {pct}%{marker}")


def _add_carbon_evidence(lines: list, metrics: dict,
                         asset_type: str) -> None:
    """
    Surface the productive/stranded carbon split, embodied carbon,
    and UHI proxy. Phase 16 changes:

    - Embodied carbon is labelled as a subtype benchmark estimate,
      not a building-level BOM figure. The value is
      material_intensity × floor area from taxonomy.yml, identical
      for every building of the same subtype — it does not encode
      actual material choices.
    - UHI is classified via classify_uhi_meaning so a green space's
      cooling benefit is never presented as if it were heat
      exposure, and a building's negative delta is flagged as a
      data anomaly.
    """
    from ..derived.environmental import classify_uhi_meaning

    total = metrics.get("carbon_operational_tco2e")
    productive = metrics.get("carbon_productive_tco2e")
    stranded = metrics.get("carbon_stranded_tco2e")
    ratio = metrics.get("stranded_carbon_ratio")

    if total is not None:
        tv = _fmt(total, 1)
        if tv is not None:
            lines.append(f"Operational carbon: {tv} tCO2e/yr")

    if stranded is not None and ratio is not None:
        sv = _fmt(stranded, 1)
        if sv is not None:
            pct = round(float(ratio) * 100, 1)
            lines.append(
                f"Stranded carbon (unused capacity): {sv} tCO2e/yr ({pct}%)"
            )

    if productive is not None:
        pv = _fmt(productive, 1)
        if pv is not None:
            lines.append(f"Productive carbon (serving users): {pv} tCO2e/yr")

    embodied = metrics.get("embodied_carbon_total_tco2e")
    if embodied is not None:
        ev = _fmt(embodied, 0)
        if ev is not None:
            lines.append(
                f"Embodied carbon locked in structure "
                f"(subtype benchmark estimate): {ev} tCO2e"
            )

    uhi = metrics.get("surface_temp_delta_c")
    if uhi is not None:
        classification = classify_uhi_meaning(asset_type, uhi)
        uv = _fmt(uhi, 1)
        if uv is not None:
            if classification["kind"] == "cooling_benefit":
                lines.append(
                    f"Cooling benefit vs open-field baseline: {uv} °C"
                )
            elif classification["is_anomaly"]:
                lines.append(
                    f"Surface temperature delta (UHI proxy): {uv} °C "
                    f"[data anomaly — verify canopy overlay]"
                )
            else:
                sign = "+" if float(uhi) > 0 else ""
                lines.append(
                    f"Surface temperature delta (UHI proxy): "
                    f"{sign}{uv} °C"
                )