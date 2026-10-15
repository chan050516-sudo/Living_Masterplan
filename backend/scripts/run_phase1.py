"""Run Phase 1 — compute derived metrics for the mock township."""

import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.derived.engine import compute_derived_metrics, merge_into_asset_metrics


def _fmt(v, decimals=3):
    if v is None:
        return "-"
    try:
        f = float(v)
        if math.isnan(f):
            return "-"
    except (TypeError, ValueError):
        return str(v)
    if abs(f) >= 1000:
        return f"{f:,.0f}"
    return f"{round(f, decimals)}"


def _section(title, width=72):
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)


def _print_asset(row, fields):
    print(f"\n  {row['asset_id']}")
    print("  " + "-" * 60)
    for label, key in fields:
        if key not in row.index:
            continue
        print(f"    {label:<32} {_fmt(row[key])}")


# Field lists per asset type
FIELDS_COMMERCIAL = [
    ("Subtype", "subtype"),
    ("Occupancy rate", "occupancy_rate"),
    ("Vacancy duration (months)", "vacancy_duration_months"),
    ("NOI (RM)", "noi_rm"),
    ("NOI yield", "noi_yield"),
    ("DSR", "dsr"),
    ("Demographic mismatch", "demographic_mismatch"),
    ("Neighborhood diversity", "neighborhood_diversity"),
    ("Walk 5-min (people)", "catchment_population_5min_walk"),
    ("Walk 10-min (people)", "catchment_population_10min_walk"),
    ("Walk 5-min coverage", "coverage_ratio_5min_walk"),
    ("Walk 10-min coverage", "coverage_ratio_10min_walk"),
    ("Median walk distance (m)", "median_walk_distance_m"),
    ("Drive 5-min (people)", "catchment_population_5min_drive"),
    ("Drive 10-min coverage", "coverage_ratio_10min_drive"),
    ("Carbon (tCO2e)", "carbon_operational_tco2e"),
]

FIELDS_FACILITY = [
    ("Subtype", "subtype"),
    ("Utilisation rate", "utilisation_rate"),
    ("Service coverage", "service_coverage"),
    ("Cost per user (RM)", "cost_per_user_rm"),
    ("Walk 5-min coverage", "coverage_ratio_5min_walk"),
    ("Walk 10-min coverage", "coverage_ratio_10min_walk"),
    ("Walk 15-min coverage", "coverage_ratio_15min_walk"),
    ("Drive 10-min coverage", "coverage_ratio_10min_drive"),
    ("Demographic mismatch", "demographic_mismatch"),
    ("Carbon (tCO2e)", "carbon_operational_tco2e"),
]

FIELDS_GREEN = [
    ("Subtype", "subtype"),
    ("Green coverage", "green_coverage"),
    ("Canopy coverage", "canopy_coverage"),
    ("Canopy benchmark", "canopy_ratio_benchmark"),
    ("Green per capita (m2)", "green_per_capita_m2"),
    ("Walk 10-min coverage", "coverage_ratio_10min_walk"),
    ("Drive 10-min coverage", "coverage_ratio_10min_drive"),
    ("Shade proxy score", "shade_proxy_score"),
]

FIELDS_PARCEL = [
    ("Subtype", "subtype"),
    ("Developable area (m2)", "developable_area_m2"),
    ("Potential GFA (m2)", "potential_gfa_m2"),
    ("Demand-supply gap", "demand_supply_gap"),
    ("Infrastructure cost (RM)", "infrastructure_cost_rm"),
    ("Walk 10-min coverage", "coverage_ratio_10min_walk"),
    ("Drive 10-min coverage", "coverage_ratio_10min_drive"),
]

FIELDS_RESIDENTIAL = [
    ("Subtype", "subtype"),
    ("Occupancy rate", "occupancy_rate"),
    ("Energy intensity (kWh/m2)", "energy_intensity_kwh_m2"),
    ("NOI (RM)", "noi_rm"),
    ("Walk 10-min coverage", "coverage_ratio_10min_walk"),
    ("Drive 10-min coverage", "coverage_ratio_10min_drive"),
]

FIELDS_BY_TYPE = {
    "commercial": FIELDS_COMMERCIAL,
    "community_facility": FIELDS_FACILITY,
    "green_space": FIELDS_GREEN,
    "undeveloped_parcel": FIELDS_PARCEL,
    "residential": FIELDS_RESIDENTIAL,
}


def main():
    repo_root = Path(__file__).resolve().parents[2]
    year = 2026

    print(f"\nRunning Phase 1 (B3) for year {year}...")
    derived = compute_derived_metrics(repo_root=repo_root, year=year)

    order = ["commercial", "community_facility", "green_space",
             "undeveloped_parcel", "residential"]

    from app.config import load_paths
    paths = load_paths()
    base_dir = repo_root / paths["base"] / "business"

    assets_path = base_dir / "assets.csv"
    assets_df = pd.read_csv(assets_path)
    type_map = dict(zip(assets_df["asset_id"], assets_df["asset_type"]))

    for atype in order:
        rows = derived[derived["asset_id"].map(type_map) == atype]
        if rows.empty:
            continue
        _section(f"{atype.upper()}")
        for _, row in rows.iterrows():
            _print_asset(row, FIELDS_BY_TYPE.get(atype, []))

    metrics_path = base_dir / "asset_metrics.csv"
    existing = pd.read_csv(metrics_path)
    merged = merge_into_asset_metrics(derived, existing, year=year)

    out_path = base_dir / "asset_metrics_enriched.csv"
    merged.to_csv(out_path, index=False)

    print("\n" + "=" * 72)
    print(f"  Wrote enriched metrics to: {out_path}")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    main()