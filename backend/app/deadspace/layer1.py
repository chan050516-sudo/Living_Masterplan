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
  - high_uhi_exposure: surface temperature proxy now participates
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
    "uhi_exposure_above_c": 7.0,
}


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


def _check_uhi(reasons: list, metrics: dict, asset_type: str, t: dict) -> None:
    """
    Flag assets whose surface temperature proxy shows severe heat
    exposure. Buildings only; green space legitimately produces a
    cooling benefit and is excluded.

    The threshold defaults to 7.0°C, which under the current UHI
    model corresponds to effective canopy < 0.075 — essentially no
    shade. Using 6.0 would fire on every commercial asset whose
    canopy falls back to the township-typical 0.10, defeating the
    purpose of the flag.
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