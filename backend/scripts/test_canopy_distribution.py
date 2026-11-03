"""Diagnostic: canopy distribution + ΔT quantiles + threshold recommendation."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE = REPO_ROOT / "bukit_jelutong" / "processed" / "business"


def header(title):
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


# ------------------------------------------------------------------ Load
assets = pd.read_csv(BASE / "assets.csv")[["asset_id", "asset_type"]]
metrics = pd.read_csv(BASE / "asset_metrics_enriched.csv")
df = metrics[metrics["year"] == 2026].merge(assets, on="asset_id", how="left")

# coalesce canopy: canopy_coverage OR shade_proxy_score/100
canopy = pd.Series(np.nan, index=df.index)
if "canopy_coverage" in df.columns:
    canopy = df["canopy_coverage"].astype(float)
if "shade_proxy_score" in df.columns:
    canopy = canopy.fillna(df["shade_proxy_score"].astype(float) / 100.0)
df["_canopy"] = canopy


# ------------------------------------------------------------------ 1-2 (unchanged, keep for record)
header("1. CANOPY DISTRIBUTION BY ASSET TYPE (2026)")
print(df.groupby("asset_type")["_canopy"].describe())

header("2. HOW SPARSE IS OSM CANOPY?")
total = len(df)
print(f"Total assets:              {total}")
print(f"canopy == 0 (or missing):  {(df['_canopy'].fillna(0) == 0).sum()}  "
      f"({(df['_canopy'].fillna(0) == 0).sum()/total*100:.1f}%)")
print(f"canopy >= 0.30:            {(df['_canopy'] >= 0.30).sum()}  "
      f"({(df['_canopy'] >= 0.30).sum()/total*100:.1f}%)")


# ------------------------------------------------------------------ 3. Landsat
thermal_path = BASE / "thermal_observations.csv"
if not thermal_path.exists():
    print("\nNo thermal_observations.csv found. Stopping.")
    sys.exit(0)

thermal = pd.read_csv(thermal_path)
valid = thermal[thermal["t_asset_c"].notna()].copy()

header("3. LANDSAT COVERAGE")
print(f"With valid pixels:    {len(valid)} / {len(thermal)}  "
      f"({len(valid)/len(thermal)*100:.1f}%)")


# ------------------------------------------------------------------ 4. ΔT quantiles & threshold recommendation
header("4. ΔT QUANTILES (valid pixels only)  —  for high_uhi_exposure threshold")
q = valid["surface_temp_delta_c"].quantile(
    [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]
)
for k, v in q.items():
    print(f"  P{int(k*100):>2}  =  {v:+.2f} °C")

print()
print("Threshold recommendation (choose based on desired flag rate):")
for t in [2.0, 2.5, 3.0, 3.5, 4.0]:
    n = (valid["surface_temp_delta_c"] >= t).sum()
    pct = n / len(valid) * 100
    print(f"  ≥ {t:.1f} °C  →  {n:>3} assets flagged  ({pct:.1f}%)")


# ------------------------------------------------------------------ 5. Canopy vs ΔT paired (safe merge)
header("5. CANOPY vs ΔT — THE CRITICAL TEST (proof it cannot be regressed)")

paired = valid.merge(
    df[["asset_id", "asset_type", "_canopy"]],
    on="asset_id",
    how="inner",
).dropna(subset=["_canopy", "surface_temp_delta_c"])

print(f"Paired samples: {len(paired)}")
print(f"  with canopy == 0:      {(paired['_canopy'] == 0).sum()}")
print(f"  with 0 < canopy < 0.1: {((paired['_canopy'] > 0) & (paired['_canopy'] < 0.1)).sum()}")
print(f"  with canopy >= 0.3:    {(paired['_canopy'] >= 0.3).sum()}")

nz = paired[paired["_canopy"] > 0]
print(f"\nAmong the {len(nz)} assets with canopy > 0:")
print(nz["_canopy"].describe())

# correlation
r_all = paired["_canopy"].corr(paired["surface_temp_delta_c"])
print(f"\nPearson r (all paired):          {r_all:+.3f}")

non_green = paired[paired["asset_type"] != "green_space"]
if len(non_green) >= 5:
    r_ng = non_green["_canopy"].corr(non_green["surface_temp_delta_c"])
    print(f"Pearson r (excl. green_space):   {r_ng:+.3f}   (n={len(non_green)})")
    print(f"  → among non-green assets, "
          f"{(non_green['_canopy'] == 0).sum()} / {len(non_green)} have canopy == 0")
    if (non_green["_canopy"] == 0).sum() / len(non_green) > 0.9:
        print("  → REGRESSION INVALID: >90% of samples sit at x=0.")

# if only green drives the signal
green_only = paired[paired["asset_type"] == "green_space"]
print(f"\nAmong green_space only (n={len(green_only)}):")
print(f"  canopy mean = {green_only['_canopy'].mean():.3f}")
print(f"  ΔT    mean = {green_only['surface_temp_delta_c'].mean():+.3f} °C")


# ------------------------------------------------------------------ 6. Extremes
header("6. ΔT EXTREMES (sanity check)")
top_hot = valid.nlargest(10, "surface_temp_delta_c")[
    ["asset_id", "t_asset_c", "t_township_c", "surface_temp_delta_c"]
]
top_cool = valid.nsmallest(10, "surface_temp_delta_c")[
    ["asset_id", "t_asset_c", "t_township_c", "surface_temp_delta_c"]
]
print("\nHot 10 assets:")
print(top_hot.to_string(index=False))
print("\nCool 10 assets:")
print(top_cool.to_string(index=False))


# ------------------------------------------------------------------ Interpretation
header("INTERPRETATION")
zeros = (df["_canopy"].fillna(0) == 0).sum() / total
if zeros > 0.85:
    print("✗ {:.1f}% of assets have canopy == 0.".format(zeros * 100))
    print("  → REGRESSION IMPOSSIBLE. Path A (no coupling) is the only honest option.")
    print("  → Do NOT add canopy→temperature coupling to B4.")
print()
print("→ Update high_uhi_exposure threshold to match the P90/P95 above.")
print("→ Remove the high_uhi_exposure / uhi_data_anomaly filter in main.py,")
print("  then the flag will fire on the top 5-8% of assets.")