"""Layer 1 — Underperformance.

Determine whether the asset is significantly below applicable
benchmark.

Phase 11 change: adds a stranded-carbon diagnostic flag.

Phase 16 (Gemini review fix):
  - green_space branch added. Previously no branch existed, so
    every green asset was permanently exempt from "below benchmark"
    diagnosis, regardless of how badly its canopy or per-capita
    supply fell short.
  - below_benchmark_occupancy: early-warning threshold at 85% of
    the subtype's peer benchmark, above the hard low_occupancy
    floor. Gradual degradation (82% on a subtype benchmarked at
    92%) now surfaces as a monitor signal instead of passing as
    healthy.
  - high_stranded_carbon split into two severity tiers. The
    absolute 100 tCO2e floor remains for the severe tier but no
    longer silently exempts a fully-dead small asset.
  - high_uhi_exposure: observed parcel temperature above township baseline
    in diagnosis instead of being a zombie field.
"""

from ..taxonomy import get_subtype_or_default


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
    # Phase 16 — green_space thresholds
    "green_coverage_below": 0.20,
    "canopy_coverage_below": 0.15,
    "green_per_capita_below_m2": 2.0,
    # Phase 16 — early-warning band: occupancy between
    # [occupancy_rate_below, benchmark * 0.85) signals early decline.
    "below_benchmark_factor": 0.85,
    # Phase 16 — severe UHI exposure threshold (°C above baseline).
    # 7.0 corresponds to effective canopy < 0.075, i.e. essentially
    # no shade. Below that, the fallback canopy is at least nominally
    # shading the footprint.
    "uhi_exposure_above_c": 3.0,
    # Phase B.2 — per-subtype death thresholds
    "subtype_dead_occupancy_below": 0.10,
    "subtype_low_occupancy_below": 0.40,
}


# ------------------------------------------------------------------
# M8 — accessibility relevance by subtype
# ------------------------------------------------------------------
# Not every commercial asset fails by being unreachable on foot.
# A showroom, a supermarket with a 3 km competition radius, or an
# office tower is driven to; judging it against 5-minute walking
# coverage penalises a business model that never wanted footfall.
#
# These tables say: for this subtype, which accessibility metric
# actually matters for its commercial viability?
WALKING_CRITICAL_SUBTYPES = frozenset({
    "convenience_retail", "kopitiam", "cafe",
    "f_and_b", "medical_retail", "services",
    "clinic", "childcare",
    "community_hall", "library",
})

DRIVING_CRITICAL_SUBTYPES = frozenset({
    "supermarket", "office", "showroom", "entertainment",
    "sports_centre", "school", "restaurant",
})


def evaluate(asset_type: str, metrics: dict, thresholds: dict = None) -> dict:
    t = {**DEFAULTS, **(thresholds or {})}
    reasons = []

    if asset_type == "commercial":
        occ = metrics.get("occupancy_rate")
        if occ is not None and occ < t["occupancy_rate_below"]:
            reasons.append("low_occupancy")
        _check_below_benchmark(reasons, metrics, occ, t)

        vac = metrics.get("vacancy_duration_months")
        if vac is not None and vac > t["vacancy_duration_above_months"]:
            reasons.append("long_vacancy")

        dsr = metrics.get("dsr")
        if dsr is not None and dsr < t["dsr_below"]:
            reasons.append("dsr_below_threshold")

        # M8 — walking / driving accessibility is judged only for
        # subtypes whose business model actually depends on it. A
        # showroom's 5-min walk coverage is irrelevant to whether
        # it is deadspace; a café's is central.
        subtype = metrics.get("subtype") or ""
        if subtype in WALKING_CRITICAL_SUBTYPES:
            wcov = metrics.get("coverage_ratio_5min_walk")
            if wcov is not None and wcov < t["walking_coverage_5min_below"]:
                reasons.append("walking_accessibility_deficit")
        if subtype in DRIVING_CRITICAL_SUBTYPES:
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
        _check_subtype_mix(reasons, metrics, t)
        _check_uhi(reasons, metrics, asset_type, t)

    elif asset_type == "community_facility":
        util = metrics.get("utilisation_rate")
        if util is not None and util < t["utilisation_rate_below"]:
            reasons.append("low_utilisation")

        wcov = metrics.get("coverage_ratio_5min_walk")
        if wcov is not None and wcov < t["walking_coverage_5min_below"]:
            reasons.append("walking_accessibility_deficit")

        _check_stranded(reasons, metrics, t)
        _check_uhi(reasons, metrics, asset_type, t)

    elif asset_type == "residential":
        occ = metrics.get("occupancy_rate")
        if occ is not None and occ < t["occupancy_rate_below"]:
            reasons.append("low_occupancy")
        _check_below_benchmark(reasons, metrics, occ, t)

        vac = metrics.get("vacancy_duration_months")
        if vac is not None and vac > t["vacancy_duration_above_months"]:
            reasons.append("long_vacancy")

        _check_stranded(reasons, metrics, t)
        _check_uhi(reasons, metrics, asset_type, t)

    elif asset_type == "undeveloped_parcel":
        gap = metrics.get("demand_supply_gap")
        if gap is not None and gap < t["demand_supply_gap_below"]:
            reasons.append("negative_demand_supply_gap")
        _check_uhi(reasons, metrics, asset_type, t)

    elif asset_type == "green_space":
        g = metrics.get("green_coverage")
        if g is not None and float(g) < t["green_coverage_below"]:
            reasons.append("low_green_coverage")

        c = metrics.get("canopy_coverage")
        if c is not None and float(c) < t["canopy_coverage_below"]:
            reasons.append("low_canopy_coverage")

        gpc = metrics.get("green_per_capita_m2")
        if gpc is not None and float(gpc) < t["green_per_capita_below_m2"]:
            reasons.append("low_green_per_capita")

    # Phase B.3 — trajectory check applies to every asset type.
    _check_trajectory(reasons, metrics, t)

    return {
        "triggered": len(reasons) > 0,
        "reasons": reasons,
    }


def _check_below_benchmark(reasons: list, metrics: dict, occ, t: dict) -> None:
    """
    Early-warning threshold: the asset is below (benchmark * 0.85)
    but still at or above the hard low_occupancy floor. This is the
    "gradually declining" band that the hard floor alone cannot see.
    """
    if occ is None:
        return
    subtype = metrics.get("subtype")
    if not subtype:
        return
    benchmark = (get_subtype_or_default(subtype)
                 .get("occupancy_benchmark"))
    if benchmark is None:
        return
    try:
        benchmark = float(benchmark)
        occ_f = float(occ)
    except (TypeError, ValueError):
        return
    if benchmark <= 0:
        return
    factor = t.get("below_benchmark_factor", 0.85)
    if occ_f < benchmark * factor and occ_f >= t["occupancy_rate_below"]:
        reasons.append("below_benchmark_occupancy")


def _check_stranded(reasons: list, metrics: dict, t: dict) -> None:
    """
    Flag an asset whose operational carbon is mostly wasted.

    Two tiers:

    high_stranded_carbon — ratio AND absolute floor both exceeded.
        Carries the full urgency weight.

    high_stranded_carbon_ratio_small_asset — ratio exceeded but
        absolute emissions below the floor. A smaller building can
        be equally dead (100% unused) while emitting less in
        absolute terms. Recording it at a lower weight keeps the
        floor's protection against trivially small assets without
        silently exempting fully-dead small ones.
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

    ratio_hit = r > t["stranded_carbon_ratio_above"]
    absolute_hit = a > t["stranded_carbon_floor_tco2e"]

    if ratio_hit and absolute_hit:
        reasons.append("high_stranded_carbon")
    elif ratio_hit and a > 10.0:
        reasons.append("high_stranded_carbon_ratio_small_asset")


def _check_subtype_mix(reasons: list, metrics: dict, t: dict) -> None:
    """
    Flag a commercial asset whose subtype mix contains a dead or
    low-occupancy subtype.

    A mall with 8 subtypes can carry an aggregate occupancy of 0.75
    (well above low_occupancy's 0.50 threshold) while its entire
    F&B floor sits empty. That partial death is real deadspace —
    the capital invested in those specific units produced nothing —
    but the aggregate occupancy hides it. This check reads the
    per-subtype breakdown emitted by B3 and surfaces the partial
    death as its own flag.

    Two severity levels:

      subtype_mix_dead — at least one subtype below 10%.
      subtype_mix_low  — at least one subtype below 40% but none
                         below 10%.

    The `subtype_mix_dead` branch fires first; the two are not
    stacked. A healthy supermarket plus a dead F&B floor produces
    one flag, not two.
    """
    from json import loads, JSONDecodeError

    raw = metrics.get("occupancy_by_subtype_calc_json")
    if raw is None:
        return
    try:
        occ_by = loads(raw) if isinstance(raw, str) else raw
    except (JSONDecodeError, TypeError):
        return
    if not isinstance(occ_by, dict) or len(occ_by) <= 1:
        return

    dead_threshold = t.get("subtype_dead_occupancy_below", 0.10)
    low_threshold = t.get("subtype_low_occupancy_below", 0.40)

    any_dead = False
    any_low = False
    for v in occ_by.values():
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if fv < dead_threshold:
            any_dead = True
            break
        elif fv < low_threshold:
            any_low = True

    if any_dead:
        reasons.append("subtype_mix_dead")
    elif any_low:
        reasons.append("subtype_mix_low")


def _check_trajectory(reasons: list, metrics: dict, t: dict) -> None:
    """
    Phase B.3 — trajectory consumption.

    The snapshot flags above (low_occupancy, negative_noi, ...) describe
    the asset at 2026. They cannot distinguish:
      - an asset that was 90% occupied two years ago and is collapsing
      - an asset that has been 45% occupied for five years
      - an asset that is recovering from a 2024 crash

    The `trajectory_class` field (computed by B3 from the five-year
    history) fills that gap. Three flags are emitted:

      rapid_decline         — occupancy dropped >20% in the last year.
                              Imminent failure; treat as urgent.
      falling_from_healthy  — occupancy fell >25% from a 70%+ peak
                              over 2+ years. Slow bleed; early
                              warning, not yet critical.
      chronic_stagnation    — occupancy has been below 85% of the
                              subtype benchmark for 3+ years. Structural
                              low, but stable. Needs repurposing, not
                              emergency stabilisation.

    "recovering" and "never_alive" do not emit flags here:
      - recovering:  the asset is improving; urgency should fall, not rise.
      - never_alive: already captured by snapshot low_occupancy (which
                     fires for occupancy < 0.50 in every type).
    """
    tclass = metrics.get("trajectory_class")
    if tclass is None or tclass == "unknown":
        return

    if tclass in ("rapid_decline", "recent_failure"):
        reasons.append("rapid_decline")
    elif tclass == "declining":
        reasons.append("falling_from_healthy")
    elif tclass == "chronic_low":
        reasons.append("chronic_stagnation")
    # stable / recovering / never_alive → no flag


def _check_uhi(reasons: list, metrics: dict, asset_type: str, t: dict) -> None:
    """
    Flag assets whose observed surface temperature is well above the
    township asset-footprint baseline. Buildings only; lower values
    are valid observations and are not anomalies.

    The threshold defaults to a 7.0°C observed difference from the
    township baseline. This threshold is intentionally reserved for
    large local surface-temperature outliers.
    """
    if asset_type not in (
        "commercial", "residential", "community_facility",
    ):
        return
    uhi = metrics.get("surface_temp_delta_c")
    if uhi is None:
        return
    try:
        v = float(uhi)
    except (TypeError, ValueError):
        return
    if v >= t["uhi_exposure_above_c"]:
        reasons.append("high_uhi_exposure")
