"""Run Phase 1 — compute derived metrics for the mock township."""

import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.derived.engine import compute_derived_metrics, merge_into_asset_metrics


# ---- Pretty print helpers -------------------------------------------------

def _fmt(v, decimals=3):
    """Format a value: None/NaN -> '-', float -> rounded string."""
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
    """Print one asset row in aligned key-value form."""
    print(f"\n  {row['asset_id']}")
    print("  " + "-" * 60)
    for label, key in fields:
        if key not in row.index:
            continue
        v = row[key]
        print(f"    {label:<28} {_fmt(v)}")


# ---- Field lists per asset type ------------------------------------------

FIELDS_COMMON = [
    ("Year", "year"),
]

FIELDS_COMMERCIAL = [
    ("Occupancy rate", "occupancy_rate"),
    ("Vacancy rate", "vacancy_rate"),
    ("Vacancy duration (months)", "vacancy_duration_months"),
    ("Footfall (daily)", "footfall_daily"),
    ("Footfall conversion (RM/p/day)", "footfall_conversion_rm_per_person"),
    ("Rental income (RM)", "rental_income_rm"),
    ("NOI (RM)", "noi_rm"),
    ("NOI yield", "noi_yield"),
    ("Maintenance surge (RM)", "maintenance_surge_rm"),
    ("Accessibility score", "accessibility_score"),
    ("Effective demand (Huff)", "effective_demand"),
    ("Effective supply", "effective_supply"),
    ("DSR", "dsr"),
    ("Thermal exposure", "thermal_exposure"),
]

FIELDS_FACILITY = [
    ("Utilisation rate", "utilisation_rate"),
    ("Service coverage", "service_coverage"),
    ("Cost per user (RM)", "cost_per_user_rm"),
    ("Accessibility score", "accessibility_score"),
]

FIELDS_GREEN = [
    ("Green coverage", "green_coverage"),
    ("Canopy coverage", "canopy_coverage"),
    ("Green per capita (m2)", "green_per_capita_m2"),
    ("Accessibility score", "accessibility_score"),
    ("Thermal exposure", "thermal_exposure"),
]

FIELDS_PARCEL = [
    ("Developable area (m2)", "developable_area_m2"),
    ("Potential GFA (m2)", "potential_gfa_m2"),
    ("Demand-supply gap", "demand_supply_gap"),
    ("Infrastructure cost (RM)", "infrastructure_cost_rm"),
    ("Accessibility score", "accessibility_score"),
]

FIELDS_RESIDENTIAL = [
    ("Occupancy rate", "occupancy_rate"),
    ("Energy intensity (kWh/m2)", "energy_intensity_kwh_m2"),
    ("NOI (RM)", "noi_rm"),
    ("Accessibility score", "accessibility_score"),
]

FIELDS_BY_TYPE = {
    "commercial": FIELDS_COMMERCIAL,
    "community_facility": FIELDS_FACILITY,
    "green_space": FIELDS_GREEN,
    "undeveloped_parcel": FIELDS_PARCEL,
    "residential": FIELDS_RESIDENTIAL,
}


# ---- Main ----------------------------------------------------------------

def main():
    repo_root = Path(__file__).resolve().parents[2]
    year = 2026

    print(f"\nRunning Phase 1 (B3) for year {year}...")
    derived = compute_derived_metrics(repo_root=repo_root, year=year)

    # Group by asset type
    order = ["commercial", "community_facility", "green_space",
             "undeveloped_parcel", "residential"]

    # Attach asset_type from assets.csv
    assets_path = repo_root / "mock" / "business" / "assets.csv"
    assets_df = pd.read_csv(assets_path)
    type_map = dict(zip(assets_df["asset_id"], assets_df["asset_type"]))

    for atype in order:
        rows = derived[derived["asset_id"].map(type_map) == atype]
        if rows.empty:
            continue
        _section(f"{atype.upper()}")
        for _, row in rows.iterrows():
            _print_asset(row, FIELDS_BY_TYPE.get(atype, []))

    # Merge and write
    metrics_path = repo_root / "mock" / "business" / "asset_metrics.csv"
    existing = pd.read_csv(metrics_path)
    merged = merge_into_asset_metrics(derived, existing, year=year)

    out_path = repo_root / "mock" / "business" / "asset_metrics_enriched.csv"
    merged.to_csv(out_path, index=False)

    print("\n" + "=" * 72)
    print(f"  Wrote enriched metrics to:")
    print(f"    {out_path}")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    main()