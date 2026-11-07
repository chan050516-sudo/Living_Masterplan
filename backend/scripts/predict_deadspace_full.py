"""Predict deadspace under the full v6.1 B6 (L1 + L2 with proxies).

This simulates what the fixed layer2.py will produce, WITHOUT
touching the actual code. Use this to validate whether the
frozen data can reach the demo target (50+ deadspace, 200+ flagged)
before you freeze.

Run:
    python backend/scripts/predict_deadspace_full.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from collections import Counter

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.taxonomy import get_subtype_or_default

with (BACKEND_DIR / "configs" / "paths.yml").open(encoding="utf-8") as f:
    PATHS = yaml.safe_load(f)
with (BACKEND_DIR / "configs" / "taxonomy.yml").open(encoding="utf-8") as f:
    TAXONOMY = yaml.safe_load(f)

BASE = REPO_ROOT / PATHS["base"]
BUSINESS = BASE / "business"

WALKING_CRITICAL = frozenset({
    "convenience_retail", "kopitiam", "cafe", "f_and_b",
    "medical_retail", "services", "clinic", "childcare",
    "community_hall", "library",
})
DRIVING_CRITICAL = frozenset({
    "supermarket", "office", "showroom", "entertainment",
    "sports_centre", "school", "restaurant",
})


def _load():
    assets = pd.read_csv(BUSINESS / "assets.csv")
    metrics = pd.read_csv(BUSINESS / "asset_metrics.csv")
    presence_p = BUSINESS / "asset_business_presence.csv"
    lbs_p = BUSINESS / "asset_lbs_metrics.csv"
    presence = pd.read_csv(presence_p) if presence_p.exists() else pd.DataFrame()
    lbs = pd.read_csv(lbs_p) if lbs_p.exists() else pd.DataFrame()
    return assets, metrics, presence, lbs


def _merge_proxies(merged: pd.DataFrame, presence: pd.DataFrame,
                   lbs: pd.DataFrame) -> pd.DataFrame:
    """Merge proxy tables onto the asset x metrics frame."""
    if not presence.empty:
        merged = merged.merge(
            presence[[
                "asset_id", "business_presence_ratio",
                "proxied_occupancy_google", "proxied_vacancy_duration",
                "business_vitality_score", "business_turnover_count",
            ]],
            on="asset_id", how="left",
        )
    if not lbs.empty:
        merged = merged.merge(
            lbs[[
                "asset_id", "lbs_unique_users_daily", "lbs_dwell_time_minutes",
                "capacity_users", "proxied_occupancy_lbs",
                "flow_island_ratio", "observed_demand_ratio",
                "traffic_exposure_vpd",
            ]],
            on="asset_id", how="left",
        )
    return merged


def _fill_occupancy(row):
    """Fill occupancy from observed, else proxy, else LBS."""
    if pd.notna(row.get("occupancy_rate")):
        return row["occupancy_rate"]
    for col in ("proxied_occupancy_lbs", "proxied_occupancy_google"):
        v = row.get(col)
        if pd.notna(v):
            return float(v)
    return None


def _fill_vacancy(row):
    if pd.notna(row.get("vacancy_duration_months")):
        return row["vacancy_duration_months"]
    v = row.get("proxied_vacancy_duration")
    if pd.notna(v):
        return float(v)
    return None


def _cf_noi(row):
    """Counterfactual NOI for sold commercial."""
    if pd.notna(row.get("noi_rm")):
        return float(row["noi_rm"])
    if row.get("asset_type") != "commercial":
        return None
    occ = row.get("occ_filled")
    if not pd.notna(occ):
        return None
    lettable = float(row.get("lettable_area_m2") or 0)
    rent = float(
        TAXONOMY.get("subtypes", {})
        .get(row.get("subtype", ""), {})
        .get("market_rent_rm_per_m2_year", 200.0)
    )
    opex = float(row.get("opex_annual_rm") or lettable * 200 * 0.08)
    maint = float(row.get("maintenance_annual_rm") or lettable * 200 * 0.025)
    return rent * lettable * float(occ) - opex - maint


def _estimate_survival_floor(row):
    """Estimate survival opex floor for operating_hemorrhage check."""
    lettable = float(row.get("lettable_area_m2") or 0)
    if lettable <= 0:
        return None
    subtype = row.get("subtype")
    # Reuse ASSUMPTIONS from assumptions.yml if wired, else use these
    # common values. Keep it simple.
    per_m2 = {
        "convenience_retail": 180, "f_and_b": 240, "cafe": 220,
        "restaurant": 280, "supermarket": 200, "services": 160,
        "medical_retail": 220,
    }.get(subtype, 200)
    return lettable * per_m2


def _estimate_revenue(row):
    """Estimate revenue from LBS users + conversion + spend."""
    users = row.get("lbs_unique_users_daily")
    if not pd.notna(users):
        return None
    subtype = row.get("subtype")
    conv = {
        "convenience_retail": 0.08, "f_and_b": 0.05, "cafe": 0.04,
        "restaurant": 0.03, "supermarket": 0.12, "services": 0.06,
        "medical_retail": 0.10,
    }.get(subtype, 0.05)
    spend = {
        "convenience_retail": 25, "f_and_b": 18, "cafe": 22,
        "restaurant": 45, "supermarket": 85, "services": 60,
        "medical_retail": 120,
    }.get(subtype, 30)
    return float(users) * conv * spend * 360


def _check_below_benchmark(row):
    occ = row.get("occ_filled")
    if not pd.notna(occ):
        return False
    subtype = row.get("subtype")
    if not subtype:
        return False
    try:
        bench = get_subtype_or_default(subtype).get("occupancy_benchmark")
        if bench is None:
            return False
        bench = float(bench)
    except (TypeError, ValueError):
        return False
    return bench > 0 and float(occ) < bench * 0.85 and float(occ) >= 0.50


def _check_accessibility(row):
    flags = []
    subtype = row.get("subtype") or ""
    if subtype in WALKING_CRITICAL:
        w = row.get("coverage_ratio_5min_walk")
        if pd.notna(w) and float(w) < 0.20:
            flags.append("walking_accessibility_deficit")
    if subtype in DRIVING_CRITICAL:
        d = row.get("coverage_ratio_10min_drive")
        if pd.notna(d) and float(d) < 0.50:
            flags.append("driving_accessibility_deficit")
    return flags


def _check_stranded(row):
    ratio = row.get("stranded_carbon_ratio")
    absolute = row.get("carbon_stranded_tco2e")
    if not pd.notna(ratio) or not pd.notna(absolute):
        return []
    try:
        r, a = float(ratio), float(absolute)
    except (TypeError, ValueError):
        return []
    if r > 0.50 and a > 100:
        return ["high_stranded_carbon"]
    if r > 0.50 and a > 10:
        return ["high_stranded_carbon_ratio_small_asset"]
    return []


def _check_subtype_mix(row):
    raw = row.get("occupancy_by_subtype_calc_json")
    if not isinstance(raw, str) or not raw:
        return []
    try:
        mix = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(mix, dict) or len(mix) <= 1:
        return []
    if any(isinstance(v, (int, float)) and float(v) < 0.10
           for v in mix.values()):
        return ["subtype_mix_dead"]
    if any(isinstance(v, (int, float)) and float(v) < 0.40
           for v in mix.values()):
        return ["subtype_mix_low"]
    return []


def _check_uhi(row, atype):
    if atype not in ("commercial", "residential", "community_facility"):
        return []
    v = row.get("surface_temp_delta_c")
    if not pd.notna(v):
        return []
    try:
        return ["high_uhi_exposure"] if float(v) >= 3.0 else []
    except (TypeError, ValueError):
        return []


def _check_trajectory(row):
    t = row.get("trajectory_class")
    if not isinstance(t, str) or t == "unknown":
        return []
    if t in ("rapid_decline", "recent_failure"):
        return ["rapid_decline"]
    if t == "declining":
        return ["falling_from_healthy"]
    if t == "chronic_low":
        return ["chronic_stagnation"]
    return []


def _evaluate(row):
    """L1 + L2 with FULL proxy integration.

    The L2 flags below (prefixed `proxy_` in comments) are what the
    fixed layer2.py will produce. They close the gap that kept 123
    assets stuck at "monitor" in the current data.
    """
    atype = row.get("asset_type")
    occ = row.get("occ_filled")
    vac = row.get("vac_filled")
    noi = row.get("noi_filled")
    util = row.get("utilisation_rate")
    presence = row.get("business_presence_ratio")
    proxy_occ_lbs = row.get("proxied_occupancy_lbs")
    flow_island = row.get("flow_island_ratio")
    survival = _estimate_survival_floor(row)
    revenue = _estimate_revenue(row)

    l1, l2 = [], []

    # ---- L1 ----
    if atype == "commercial":
        if pd.notna(occ) and float(occ) < 0.50:
            l1.append("low_occupancy")
        if _check_below_benchmark(row):
            l1.append("below_benchmark_occupancy")
        if pd.notna(vac) and float(vac) > 12:
            l1.append("long_vacancy")
        dsr = row.get("dsr")
        if pd.notna(dsr) and float(dsr) < 0.80:
            l1.append("dsr_below_threshold")
        l1.extend(_check_accessibility(row))
        mm = row.get("demographic_mismatch")
        if pd.notna(mm) and float(mm) > 0.40:
            l1.append("demographic_mismatch")
        nd = row.get("neighborhood_diversity")
        if pd.notna(nd) and float(nd) < 0.30:
            l1.append("low_neighborhood_diversity")
        l1.extend(_check_stranded(row))
        l1.extend(_check_subtype_mix(row))
        l1.extend(_check_uhi(row, atype))

    elif atype == "residential":
        if pd.notna(occ) and float(occ) < 0.50:
            l1.append("low_occupancy")
        if _check_below_benchmark(row):
            l1.append("below_benchmark_occupancy")
        if pd.notna(vac) and float(vac) > 12:
            l1.append("long_vacancy")
        l1.extend(_check_stranded(row))
        l1.extend(_check_uhi(row, atype))

    elif atype == "community_facility":
        if pd.notna(util) and float(util) < 0.40:
            l1.append("low_utilisation")
        w = row.get("coverage_ratio_5min_walk")
        if pd.notna(w) and float(w) < 0.20:
            l1.append("walking_accessibility_deficit")
        l1.extend(_check_stranded(row))
        l1.extend(_check_uhi(row, atype))

    elif atype == "green_space":
        if pd.notna(row.get("green_coverage")) and float(row["green_coverage"]) < 0.20:
            l1.append("low_green_coverage")
        if pd.notna(row.get("canopy_coverage")) and float(row["canopy_coverage"]) < 0.15:
            l1.append("low_canopy_coverage")
        if pd.notna(row.get("green_per_capita_m2")) and float(row["green_per_capita_m2"]) < 2.0:
            l1.append("low_green_per_capita")

    elif atype == "undeveloped_parcel":
        gap = row.get("demand_supply_gap")
        if pd.notna(gap) and float(gap) < 0:
            l1.append("negative_demand_supply_gap")
        l1.extend(_check_uhi(row, atype))

    l1.extend(_check_trajectory(row))

    # ---- L2 (EXTENDED — the flags below are what makes 50+ reachable) ----
    if atype == "commercial":
        if pd.notna(noi) and float(noi) < 0:
            l2.append("negative_noi")
        # Proxy-based L2 flags:
        if pd.notna(proxy_occ_lbs) and float(proxy_occ_lbs) < 0.30:
            l2.append("proxy_occupancy_low")
        if pd.notna(presence) and float(presence) < 0.40:
            l2.append("business_presence_low")
        if pd.notna(flow_island) and float(flow_island) < 0.30:
            l2.append("flow_island")
        if (survival is not None and revenue is not None
                and revenue < survival):
            l2.append("operating_hemorrhage")

    elif atype == "residential":
        held = row.get("developer_held_units")
        if (pd.notna(held) and float(held) > 0
                and pd.notna(occ) and float(occ) < 0.05):
            l2.append("built_value_not_realized")
        # Proxy L2:
        if pd.notna(occ) and float(occ) < 0.40:
            l2.append("proxy_occupancy_low")
        if pd.notna(vac) and float(vac) > 24:
            l2.append("long_vacancy_proxied")

    elif atype == "community_facility":
        cov = row.get("coverage_ratio_10min_walk")
        if pd.notna(cov) and float(cov) < 0.60:
            l2.append("insufficient_coverage")
        if pd.notna(util):
            subtype = row.get("subtype")
            bench = get_subtype_or_default(subtype).get("utilisation_benchmark", 0.55)
            try:
                bench = float(bench)
                if float(util) < bench * 0.75:
                    l2.append("utilisation_below_benchmark")
            except (TypeError, ValueError):
                pass

    elif atype == "green_space":
        cov = row.get("coverage_ratio_10min_walk")
        canopy = row.get("canopy_coverage")
        if pd.notna(cov) and float(cov) < 0.30:
            if pd.notna(canopy) and float(canopy) > 0.05:
                l2.append("low_accessibility_high_ecological_value")
            else:
                l2.append("low_accessibility")

    elif atype == "undeveloped_parcel":
        gap = row.get("demand_supply_gap")
        if pd.notna(gap) and float(gap) < 0:
            l2.append("weak_future_demand")

    # ---- Status ----
    l1_on = len(l1) > 0
    l2_on = len(l2) > 0
    flags = l1 + l2

    if not (l1_on or l2_on):
        return "healthy", flags

    if atype == "commercial":
        return ("deadspace_candidate" if l1_on and l2_on else "monitor"), flags
    if atype == "residential":
        return ("deadspace_candidate" if l1_on and l2_on else "monitor"), flags
    if atype == "community_facility":
        return ("underperforming_facility" if l1_on and l2_on else "monitor"), flags
    if atype == "green_space":
        return "improvement_opportunity", flags
    if atype == "undeveloped_parcel":
        return "development_risk", flags
    return "healthy", flags


def main():
    assets, metrics, presence, lbs = _load()
    m26 = metrics[metrics["year"] == 2026].copy()
    merged = assets.merge(m26, on="asset_id", how="left", suffixes=("", "_m"))
    merged = _merge_proxies(merged, presence, lbs)

    merged["occ_filled"] = merged.apply(_fill_occupancy, axis=1)
    merged["vac_filled"] = merged.apply(_fill_vacancy, axis=1)
    merged["noi_filled"] = merged.apply(_cf_noi, axis=1)

    results = merged.apply(_evaluate, axis=1, result_type="expand")
    merged["predicted_status"] = results[0]
    merged["predicted_flags"] = results[1]

    print("\n" + "=" * 78)
    print("  FULL v6.1 B6 prediction (L1 + L2 with proxies)")
    print("=" * 78)
    counts = merged["predicted_status"].value_counts()
    for status, n in counts.items():
        print(f"  {status:<30} {n:>5}  ({n / len(merged) * 100:.1f}%)")
    total_flagged = counts.drop("healthy", errors="ignore").sum()
    print(f"\n  Total flagged (non-healthy): {total_flagged}")
    print(f"  deadspace_candidate:         {counts.get('deadspace_candidate', 0)}")

    print("\n" + "=" * 78)
    print("  deadspace_candidate by asset_type")
    print("=" * 78)
    dsc = merged[merged["predicted_status"] == "deadspace_candidate"]
    for atype, g in dsc.groupby("asset_type"):
        print(f"  {atype:<25} {len(g):>5}")

    print("\n" + "=" * 78)
    print("  Flag frequency (top 20)")
    print("=" * 78)
    c = Counter()
    for flags in merged["predicted_flags"]:
        for f in flags:
            c[f] += 1
    for f, n in c.most_common(20):
        print(f"  {f:<45} {n:>4}")

    print("\n" + "=" * 78)
    print("  Target check")
    print("=" * 78)
    deadspace = counts.get("deadspace_candidate", 0)
    print(f"  deadspace_candidate >= 50:  "
          f"{'✅ PASS' if deadspace >= 50 else f'❌ FAIL ({deadspace})'}")
    print(f"  total flagged >= 200:       "
          f"{'✅ PASS' if total_flagged >= 200 else f'❌ FAIL ({total_flagged})'}")

    out = BUSINESS / "deadspace_prediction_full.csv"
    merged[[
        "asset_id", "asset_type", "subtype", "authority",
        "occ_filled", "noi_filled", "predicted_status",
    ]].to_csv(out, index=False)
    print(f"\nDetailed prediction: {out}")


if __name__ == "__main__":
    main()