"""Quantify residential units hidden inside merged polygons.

Run from repo root:
    python backend/scripts/quantify_residential_units.py

Answers:
  1. For each residential subtype, how many polygons fall in each
     area bucket, and how many real units each bucket represents?
  2. Which asset_ids are the biggest mergers (top 20)?
  3. What fraction of assets are true single units vs merged?

Area buckets per subtype are calibrated against physical reality:
  terrace       single = 80-200 m²    typical unit = 140 m²
  semidetached  single = 150-400 m²   typical unit = 220 m²
  detached      single = 200-800 m²   typical unit = 400 m²
  apartment     whole building, unit_count uses ~50 m² GFA per unit

Read-only.
"""

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import load_paths


# Single-unit upper bound per subtype. Above this, the polygon is
# presumed to be a merged row / block.
SINGLE_UNIT_MAX_M2 = {
    "terrace":        200.0,
    "semidetached":   400.0,
    "detached":       800.0,
    "apartment_lowrise":  8000.0,   # treat as one building; count units by GFA
    "apartment_highrise": 30000.0,
}

# Typical per-unit footprint used to estimate unit_count from area.
TYPICAL_UNIT_FOOTPRINT_M2 = {
    "terrace":        140.0,
    "semidetached":   220.0,
    "detached":       400.0,
}

# Apartment: estimate from GFA (area × floors), not footprint.
APARTMENT_GFA_PER_UNIT_M2 = 85.0   # typical Malaysian apartment GFA per unit


def _hdr(t):
    print("\n" + "=" * 72)
    print(f"  {t}")
    print("=" * 72)


def _sub(t):
    print(f"\n  ── {t}")


def _estimate_units(area_m2, subtype, floors=None):
    """Estimate real household count from polygon footprint."""
    if subtype in TYPICAL_UNIT_FOOTPRINT_M2:
        fp = TYPICAL_UNIT_FOOTPRINT_M2[subtype]
        return max(1, round(area_m2 / fp))
    if subtype and subtype.startswith("apartment"):
        # Apartment: GFA = footprint × floors; units = GFA / 85
        fl = floors if floors and floors > 0 else 5.0
        gfa = area_m2 * fl
        return max(1, round(gfa / APARTMENT_GFA_PER_UNIT_M2))
    return 1


def _bucket(area_m2, subtype):
    """Return the area bucket label for a residential polygon."""
    max_single = SINGLE_UNIT_MAX_M2.get(subtype, 500.0)
    if area_m2 <= max_single:
        return "single"
    if area_m2 <= max_single * 3:
        return "small_merged"
    if area_m2 <= max_single * 8:
        return "large_merged"
    return "block"


def main():
    repo_root = Path(__file__).resolve().parents[2]
    paths = load_paths()
    base = repo_root / paths["base"]

    assets = pd.read_csv(base / "business" / "assets.csv")
    buildings = gpd.read_file(base / "geometry" / "buildings_bj.geojson").to_crs(32647)

    # Join area and floors from buildings layer
    b_idx = {}
    for _, r in buildings.iterrows():
        bid = str(r["building_id"])
        b_idx[bid] = {
            "area_m2": float(r.geometry.area),
            "floors": r.get("floors"),
        }

    res = assets[assets["asset_type"] == "residential"].copy()
    res["area_m2"] = res["asset_id"].astype(str).map(
        lambda a: b_idx.get(a, {}).get("area_m2")
    )
    res["floors"] = res["asset_id"].astype(str).map(
        lambda a: b_idx.get(a, {}).get("floors")
    )
    res = res[res["area_m2"].notna()].copy()

    print(f"repo_root: {repo_root}")
    print(f"residential assets: {len(res)}")
    print(f"total residential footprint: {res['area_m2'].sum():,.0f} m²")

    # -------- Per-subtype bucket distribution --------
    _hdr("1. Area bucket distribution per subtype")
    print(f"  {'subtype':<22} {'bucket':<14} {'count':>6} {'area (m²)':>14} "
          f"{'est. units':>12}")

    for subtype in sorted(res["subtype"].unique()):
        sub = res[res["subtype"] == subtype]
        for bucket in ("single", "small_merged", "large_merged", "block"):
            group = sub[sub.apply(
                lambda r: _bucket(r["area_m2"], subtype), axis=1,
            ) == bucket]
            if group.empty:
                continue
            units = sum(
                _estimate_units(r["area_m2"], subtype, r.get("floors"))
                for _, r in group.iterrows()
            )
            print(
                f"  {subtype:<22} {bucket:<14} {len(group):>6} "
                f"{group['area_m2'].sum():>14,.0f} "
                f"{units:>12,}"
            )

    # -------- Aggregate summary --------
    _hdr("2. Township-level summary")
    res["_bucket"] = res.apply(
        lambda r: _bucket(r["area_m2"], r["subtype"]), axis=1,
    )
    res["_units"] = res.apply(
        lambda r: _estimate_units(r["area_m2"], r["subtype"], r.get("floors")),
        axis=1,
    )

    print(f"  polygon count:        {len(res)}")
    print(f"  estimated real units: {res['_units'].sum():,}")
    print(f"  multiplier:           "
          f"{res['_units'].sum() / len(res):.2f}x")

    print(f"\n  by bucket:")
    for bucket in ("single", "small_merged", "large_merged", "block"):
        group = res[res["_bucket"] == bucket]
        if group.empty:
            continue
        pct_poly = len(group) / len(res) * 100
        pct_units = group["_units"].sum() / res["_units"].sum() * 100
        print(
            f"    {bucket:<14}  polygons={len(group):>4} ({pct_poly:>5.1f}%)  "
            f"units={group['_units'].sum():>5,} ({pct_units:>5.1f}%)"
        )

    # -------- Top mergers --------
    _hdr("3. Top 20 largest mergers (by estimated unit count)")

    res_sorted = res.sort_values("_units", ascending=False)
    print(f"  {'asset_id':<12} {'subtype':<14} {'area (m²)':>10} "
          f"{'floors':>7} {'units':>6}")
    for _, r in res_sorted.head(20).iterrows():
        fl = r.get("floors")
        fl_s = f"{int(fl)}" if pd.notna(fl) else "?"
        print(
            f"  {r['asset_id']:<12} {r['subtype']:<14} "
            f"{r['area_m2']:>10,.1f} {fl_s:>7} {int(r['_units']):>6}"
        )

    # -------- Suspicious small-area apartments --------
    _hdr("4. Suspicious polygons (area vs subtype mismatch)")

    _sub("apartments under 500 m² (too small to be a building)")
    small_apt = res[
        res["subtype"].str.startswith("apartment")
        & (res["area_m2"] < 500)
    ]
    if small_apt.empty:
        print("    none")
    else:
        for _, r in small_apt.iterrows():
            print(f"    {r['asset_id']}  {r['subtype']}  "
                  f"area={r['area_m2']:.1f} m²")

    _sub("detached under 150 m² (too small for a villa)")
    small_det = res[
        (res["subtype"] == "detached") & (res["area_m2"] < 150)
    ]
    if small_det.empty:
        print("    none")
    else:
        for _, r in small_det.iterrows():
            print(f"    {r['asset_id']}  area={r['area_m2']:.1f} m²")

    _sub("terrace over 5000 m² (very large merged strip)")
    big_terr = res[
        (res["subtype"] == "terrace") & (res["area_m2"] > 5000)
    ]
    if big_terr.empty:
        print("    none")
    else:
        for _, r in big_terr.iterrows():
            print(f"    {r['asset_id']}  area={r['area_m2']:.1f} m²  "
                  f"units≈{int(r['_units'])}")

    # -------- Write a proposal CSV --------
    _hdr("5. Proposal — unit_count column for assets.csv")
    print("  For each residential asset, the proposed unit_count is:")
    print("    terrace / semidetached / detached: area / typical_footprint")
    print("    apartment: (area × floors) / 85")

    out_df = res[["asset_id", "subtype", "area_m2", "_units"]].rename(
        columns={"_units": "proposed_unit_count"},
    ).sort_values("asset_id")
    out_path = base / "business" / "proposed_unit_counts.csv"
    out_df.to_csv(out_path, index=False)
    print(f"\n  wrote {len(out_df)} rows -> {out_path}")

    # Non-residential assets get unit_count=1 by default
    print(f"\n  Non-residential assets (default unit_count=1): "
          f"{len(assets) - len(res)}")


if __name__ == "__main__":
    main()