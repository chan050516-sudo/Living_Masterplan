"""Validate Phase B.1 output against expected multi-year structure."""

import pandas as pd

ENRICHED = "bukit_jelutong/processed/business/asset_metrics_enriched.csv"
ASSETS = "bukit_jelutong/processed/business/assets.csv"
EXPECTED_YEARS = [2022, 2023, 2024, 2025, 2026]


def _hdr(title):
    print("\n" + "=" * 72)
    print(f"  {title}")
    print("=" * 72)


def _ok(msg):
    print(f"[ OK ] {msg}")


def _fail(msg):
    print(f"\n[FAIL] {msg}\n")
    raise SystemExit(1)


def main():
    df = pd.read_csv(ENRICHED)
    assets = pd.read_csv(ASSETS)

    _hdr("1. Row count and year coverage")
    print(f"  rows: {len(df)}")
    print(f"  years: {sorted(df['year'].unique())}")

    if len(df) < 4000:
        _fail(f"only {len(df)} rows — old single-year output")
    missing = [y for y in EXPECTED_YEARS if y not in df["year"].unique()]
    if missing:
        _fail(f"missing years: {missing}")
    _ok(f"{len(df)} rows, {EXPECTED_YEARS}")

    _hdr("2. Trajectory columns")
    required = [
        "peak_occupancy", "years_since_peak", "occupancy_trend_3yr",
        "years_below_benchmark", "trajectory_class",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        _fail(f"missing columns: {missing}")
    _ok("all trajectory columns present")

    _hdr("3. trajectory_class distribution (2026)")
    dist = df[df["year"] == 2026]["trajectory_class"].value_counts()
    for cls, count in dist.items():
        print(f"  {cls:<20} {count:>5}")
    _ok(f"{len(dist)} trajectory classes")

    _hdr("4. Unsold residential trajectory")
    unsold = assets[
        (assets["asset_type"] == "residential")
        & (assets["developer_held_units"] > 0)
    ]["asset_id"].head(2).tolist()
    for aid in unsold:
        sub = df[df["asset_id"] == aid].sort_values("year")
        print(f"\n  {aid}:")
        for _, r in sub.iterrows():
            print(f"    {int(r['year'])}  "
                  f"occ={r['occupancy_rate']:.3f}  "
                  f"occupied_units={r['occupied_units']}  "
                  f"class={r['trajectory_class']}")
    _ok("unsold trajectories printed")

    _hdr("5. BLD-0818 canopy + UHI")
    b818 = df[(df["asset_id"] == "BLD-0818") & (df["year"] == 2026)]
    if b818.empty:
        print("  (BLD-0818 not present)")
    else:
        canopy = float(b818["canopy_coverage"].iloc[0])
        uhi = float(b818["surface_temp_delta_c"].iloc[0])
        print(f"  canopy: {canopy}")
        print(f"  UHI:    {uhi} °C")
        if canopy > 0.95:
            _fail(f"canopy still {canopy} — landscape exclusion failed")
        _ok("canopy no longer dominated by landscape wood")

    _hdr("6. Commercial per-subtype demand")
    comm_ids = set(assets[assets["asset_type"] == "commercial"]["asset_id"])
    comm = df[(df["asset_id"].isin(comm_ids)) & (df["year"] == 2026)].head(3)
    for _, r in comm.iterrows():
        mix = r.get("effective_demand_by_subtype_json")
        print(f"  {r['asset_id']}:")
        print(f"    total: {r['effective_demand_m2']:.1f} m²")
        print(f"    subtypes: {mix if pd.notna(mix) else '(none)'}")
    if "effective_demand_by_subtype_json" not in df.columns:
        _fail("column missing")
    _ok("per-subtype demand present")

    print("\n" + "=" * 72)
    print("  All checks passed. Phase B.1 complete.")
    print("=" * 72 + "\n")

    # --- Phase B.2 checks ---
    print("\n" + "=" * 72)
    print("  7. Per-subtype breakdown")
    print("=" * 72)

    assets = pd.read_csv("bukit_jelutong/processed/business/assets.csv")
    comm_ids = set(assets[assets["asset_type"] == "commercial"]["asset_id"])
    comm_current = df[
        (df["asset_id"].isin(comm_ids)) & (df["year"] == 2026)
    ]

    # Count how many have per-subtype data
    has_dsr = comm_current["dsr_by_subtype_json"].notna().sum()
    has_carbon = comm_current["carbon_by_subtype_json"].notna().sum()
    print(f"  commercial assets with dsr_by_subtype_json: "
        f"{has_dsr}/{len(comm_current)}")
    print(f"  commercial assets with carbon_by_subtype_json: "
        f"{has_carbon}/{len(comm_current)}")

    if has_dsr == 0:
        print("[FAIL] no per-subtype DSR emitted — B.2 did not run")
        raise SystemExit(1)

    # Show 3 samples
    sample = comm_current[comm_current["dsr_by_subtype_json"].notna()].head(3)
    for _, r in sample.iterrows():
        print(f"\n  {r['asset_id']}:")
        print(f"    total dsr:     {r['dsr']:.3f}")
        print(f"    by subtype:    {r['dsr_by_subtype_json']}")
        print(f"    occupancy:     {r['occupancy_by_subtype_calc_json']}")
        print(f"    carbon:        {r['carbon_by_subtype_json']}")

    print("[ OK ] Phase B.2 fields present")


if __name__ == "__main__":
    main()