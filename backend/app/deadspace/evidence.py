"""Human-readable evidence strings for the diagnosis card.

Surfaces the productive vs stranded carbon split and observed Landsat
surface temperatures so the LLM and UI can reference their provenance.
"""


def _fmt(v, decimals=2):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    if abs(f) >= 1000:
        return f"{f:,.0f}"
    return f"{round(f, decimals)}"


def build_evidence(asset_type: str, subtype, metrics: dict,
                   proxy=None, survival=None, external=None) -> list:
    """
    `proxy` is set only for sold / advisory commercial assets. Their
    occupancy, vacancy and NOI are not visible to the developer, so those
    lines give way to the Google Places and LBS proxy lines (v6.0 §7.1).
    """
    lines = []
    sold = proxy is not None

    def _add(label, key, suffix="", decimals=2):
        v = _fmt(metrics.get(key), decimals)
        if v is not None:
            lines.append(f"{label}: {v}{suffix}")

    if subtype:
        lines.append(f"Subtype: {subtype}")

    _add_carbon_evidence(lines, metrics, asset_type,
                         proxied_occ=proxy.get("proxied_occupancy") if sold else None,
                         sold=sold)

    if asset_type == "commercial" and sold:
        _add_proxy_evidence(lines, external or {}, proxy, survival)
        _add("Counterfactual NOI if SDP had retained (RM, annual)", "noi_rm")
    elif asset_type == "commercial":
        occ = metrics.get("occupancy_rate")
        if occ is not None:
            lines.append(f"Occupancy: {round(occ * 100, 1)}%")
        vac = metrics.get("vacancy_duration_months")
        if vac is not None:
            lines.append(f"Vacancy: {int(vac)} months")
        _add("NOI (RM, annual)", "noi_rm")
        _add("NOI yield (annual)", "noi_yield", decimals=4)
    if asset_type == "commercial":
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
        if not sold:
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

    # Phase B.3 — trajectory narrative appended after the type-specific
    # evidence lines. The trajectory summary is what tells the reader
    # whether the flag is describing a fresh fall or a long decline.
    # The trajectory is an occupancy history, which a sold asset lacks.
    if not sold:
        _add_trajectory_evidence(lines, metrics)

    return lines


def _add_trajectory_evidence(lines: list, metrics: dict) -> None:
    """
    Phase B.3 — trajectory summary.

    Reads the trajectory_class and its supporting features from the
    enriched metrics and appends one human-readable line summarising
    the asset's five-year path. Skipped for assets whose trajectory is
    "unknown" (green_space, undeveloped_parcel, and any asset that B3
    could not classify).
    """
    tclass = metrics.get("trajectory_class")
    if not tclass or tclass == "unknown":
        return

    def _pct(v):
        try:
            return f"{round(float(v) * 100, 1)}%"
        except (TypeError, ValueError):
            return None

    if tclass == "stable":
        peak = _pct(metrics.get("peak_occupancy"))
        if peak:
            lines.append(f"Trajectory: stable (5-yr peak {peak})")
        else:
            lines.append("Trajectory: stable")

    elif tclass in ("rapid_decline", "recent_failure"):
        peak = _pct(metrics.get("peak_occupancy"))
        ysp = metrics.get("years_since_peak")
        msg = "Trajectory: rapid decline"
        if peak:
            msg += f" (from {peak} peak"
            if ysp is not None:
                try:
                    msg += f", {int(ysp)} yr ago"
                except (TypeError, ValueError):
                    pass
            msg += ")"
        lines.append(msg)

    elif tclass == "declining":
        peak = _pct(metrics.get("peak_occupancy"))
        ysp = metrics.get("years_since_peak")
        msg = "Trajectory: declining"
        if peak and ysp is not None:
            try:
                msg += f" (peak {peak} {int(ysp)} yrs ago)"
            except (TypeError, ValueError):
                pass
        lines.append(msg)

    elif tclass == "chronic_low":
        n = metrics.get("years_below_benchmark")
        msg = "Trajectory: chronic low"
        if n is not None:
            try:
                msg += f" ({int(n)} consecutive years below benchmark)"
            except (TypeError, ValueError):
                pass
        lines.append(msg)

    elif tclass == "recovering":
        lines.append("Trajectory: recovering from previous low")

    elif tclass == "never_alive":
        lines.append("Trajectory: never occupied since completion")
        

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
                         asset_type: str, proxied_occ=None,
                         sold=False) -> None:
    """
    Surface the productive/stranded carbon split, embodied carbon,
    and observed Landsat temperatures.

    - Embodied carbon is labelled as a subtype benchmark estimate,
      not a building-level BOM figure. The value is
      material_intensity × floor area from taxonomy.yml, identical
      for every building of the same subtype — it does not encode
      actual material choices.
    - For sold assets the split uses the proxied occupancy (tier 3a),
      because the observed occupancy is not available to the developer.
    """
    total = metrics.get("carbon_operational_tco2e")
    productive = metrics.get("carbon_productive_tco2e")
    stranded = metrics.get("carbon_stranded_tco2e")
    ratio = metrics.get("stranded_carbon_ratio")
    label = ""

    if sold:
        productive = stranded = ratio = None
        if total is not None and proxied_occ is not None:
            occ = min(max(float(proxied_occ), 0.0), 1.0)
            ratio = 1.0 - occ
            stranded = float(total) * ratio
            productive = float(total) * occ
            label = ", proxy estimate"

    if total is not None:
        tv = _fmt(total, 1)
        if tv is not None:
            lines.append(f"Operational carbon: {tv} tCO2e/yr")

    if stranded is not None and ratio is not None:
        sv = _fmt(stranded, 1)
        if sv is not None:
            pct = round(float(ratio) * 100, 1)
            lines.append(
                f"Stranded carbon (unused capacity{label}): {sv} tCO2e/yr ({pct}%)"
            )

    if productive is not None:
        pv = _fmt(productive, 1)
        if pv is not None:
            lines.append(f"Productive carbon (serving users{label}): {pv} tCO2e/yr")

    embodied = metrics.get("embodied_carbon_total_tco2e")
    if embodied is not None:
        ev = _fmt(embodied, 0)
        if ev is not None:
            lines.append(
                f"Embodied carbon locked in structure "
                f"(subtype benchmark estimate): {ev} tCO2e"
            )

    t_asset = metrics.get("t_asset_c")
    t_township = metrics.get("t_township_c")
    delta = metrics.get("surface_temp_delta_c")
    provenance = metrics.get("surface_temp_provenance")
    if all(_fmt(v) is not None for v in (t_asset, t_township, delta)):
        asset_temp = _fmt(t_asset, 1)
        township_temp = _fmt(t_township, 1)
        delta_temp = _fmt(abs(float(delta)), 1)
        sign = "+" if float(delta) > 0 else ("-" if float(delta) < 0 else "")
        source = f" [{provenance}]" if provenance else ""
        lines.append(
            f"Observed land surface temperature{source}: parcel "
            f"{asset_temp} °C; township baseline {township_temp} °C; "
            f"T = Tasset − Ttownship = {sign}{delta_temp} °C"
        )


def _add_proxy_evidence(lines: list, ext: dict, proxy: dict,
                        survival) -> None:
    """
    Tier-3a proxy lines for a sold / advisory asset. Worded so the LLM
    cites the source, never a bare occupancy or vacancy figure (v6.0 §7.1).
    """
    units = ext.get("unit_mix_unit_count")
    operating = ext.get("operational_place_count")
    if units and operating is not None:
        lines.append(
            f"Google Places business presence (mock): {int(operating)} of "
            f"{int(units)} units have an operating business"
        )
    turnover = ext.get("business_turnover_count")
    if turnover:
        lines.append(f"Google Places business turnover (mock): {int(turnover)} change(s) this year")
    vitality = _fmt(ext.get("business_vitality_score"), 2)
    if vitality is not None:
        lines.append(f"Google Places vitality score (mock, 0-1): {vitality}")

    users = _fmt(ext.get("lbs_unique_users_daily"), 0)
    dwell = _fmt(ext.get("lbs_dwell_time_minutes"), 0)
    if users is not None:
        tail = f", average dwell {dwell} min" if dwell is not None else ""
        lines.append(f"LBS foot traffic (mock): {users} daily visitors{tail}")
    island = _fmt(ext.get("flow_island_ratio"), 2)
    if island is not None:
        lines.append(f"LBS flow-island ratio (mock, below 0.3 = isolated): {island}")

    if survival and survival.get("estimated_revenue_rm") is not None:
        rev = _fmt(survival["estimated_revenue_rm"], 0)
        floor = _fmt(survival["survival_opex_floor_rm"], 0)
        lines.append(
            f"Survival check (estimate): footfall revenue RM {rev}/yr "
            f"vs minimum operating cost RM {floor}/yr"
        )

    if "data_conflict" in (proxy or {}).get("reasons", []):
        lines.append("Google Places and LBS disagree; proxies not conclusive")
