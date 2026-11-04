"""Quick check: do woodland ('canopy') green spaces run cooler than parks?"""
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
BASE = REPO_ROOT / "bukit_jelutong" / "processed"


def main():
    thermal = pd.read_csv(BASE / "business" / "thermal_observations.csv")
    thermal = thermal[thermal["t_asset_c"].notna()][
        ["asset_id", "t_asset_c", "t_township_c", "surface_temp_delta_c"]
    ].copy()

    assets = pd.read_csv(BASE / "business" / "assets.csv")[
        ["asset_id", "asset_type", "subtype"]
    ]
    green_assets = assets[assets["asset_type"] == "green_space"].copy()

    green_gdf = gpd.read_file(BASE / "geometry" / "green_blue_bj.geojson")
    green_gdf["asset_id"] = green_gdf["asset_id"].astype(str)
    green_gdf["area_m2"] = green_gdf["area_m2"].astype(float)

    # For each asset_id, take the green_type of the LARGEST polygon
    # (a green asset may span multiple polygons of different types)
    dominant = (
        green_gdf
        .sort_values("area_m2", ascending=False)
        .drop_duplicates("asset_id", keep="first")
        [["asset_id", "green_type", "area_m2"]]
    )

    merged = (
        green_assets
        .merge(dominant, on="asset_id", how="left")
        .merge(thermal, on="asset_id", how="inner")
    )

    print(f"Green space assets with valid thermal: {len(merged)} / {len(green_assets)}")
    if len(merged) == 0:
        print("No green assets with valid thermal. Stopping.")
        return
    print(f"Township baseline: {merged['t_township_c'].iloc[0]:.2f} °C\n")

    print("=" * 72)
    print("BY DOMINANT GREEN_TYPE  (canopy = woodland / forest)")
    print("=" * 72)
    by_type = (
        merged
        .groupby("green_type")["surface_temp_delta_c"]
        .agg(["count", "mean", "median", "min", "max"])
        .round(3)
        .sort_values("mean")
    )
    print(by_type)

    print()
    print("=" * 72)
    print("BY SUBTYPE  (taxonomy label)")
    print("=" * 72)
    by_subtype = (
        merged
        .groupby("subtype")["surface_temp_delta_c"]
        .agg(["count", "mean", "median", "min", "max"])
        .round(3)
        .sort_values("mean")
    )
    print(by_subtype)

    print()
    print("=" * 72)
    print("KEY COMPARISON: canopy (forest) vs park (grassland)")
    print("=" * 72)
    canopy = merged[merged["green_type"] == "canopy"]
    park = merged[merged["green_type"] == "park"]
    public_space = merged[merged["green_type"] == "public_space"]
    water = merged[merged["green_type"] == "water_body"]

    def _stat(df, label):
        if len(df) == 0:
            print(f"  {label:<13} n=0")
            return
        print(f"  {label:<13} n={len(df):>3}  "
              f"mean ΔT = {df['surface_temp_delta_c'].mean():+.3f} °C  "
              f"median = {df['surface_temp_delta_c'].median():+.3f} °C")

    _stat(canopy, "canopy")
    _stat(park, "park")
    _stat(public_space, "public_space")
    _stat(water, "water_body")

    # Non-parametric test (samples may be small, not normally distributed)
    if len(canopy) >= 3 and len(park) >= 3:
        from scipy.stats import mannwhitneyu
        stat, p = mannwhitneyu(
            canopy["surface_temp_delta_c"],
            park["surface_temp_delta_c"],
            alternative="less",
        )
        diff = canopy["surface_temp_delta_c"].mean() - park["surface_temp_delta_c"].mean()
        print(f"\n  Mann-Whitney U (canopy < park): p = {p:.4f}")
        if p < 0.05:
            print(f"  → SIGNIFICANT: canopy is {abs(diff):.2f} °C cooler than park")
        elif p < 0.20:
            print(f"  → WEAK SIGNAL: canopy is {abs(diff):.2f} °C cooler (p={p:.3f}), "
                  f"sample size too small for confidence")
        else:
            print(f"  → NO SIGNAL: canopy and park are indistinguishable (diff = {diff:+.2f} °C)")

    # Also check: do any green assets show unusually strong cooling?
    print()
    print("=" * 72)
    print("COOLEST GREEN ASSETS (top 10)")
    print("=" * 72)
    top_cool = merged.nsmallest(10, "surface_temp_delta_c")[
        ["asset_id", "green_type", "subtype", "area_m2", "surface_temp_delta_c"]
    ]
    print(top_cool.to_string(index=False))


if __name__ == "__main__":
    main()