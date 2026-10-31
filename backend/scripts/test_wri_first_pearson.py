"""Fetch WRI Tropical Tree Cover from GEE, compute per-asset mean canopy
percentage, and test Pearson correlation with Landsat surface-temperature ΔT.
"""
import os
import sys
from pathlib import Path

import ee
import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.stats import pearsonr
from shapely.ops import orient

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE = REPO_ROOT / "bukit_jelutong" / "processed"
WRI_ASSET = "projects/wri-datalab/TropicalTreeCover"
SCALE_M = 10  # WRI tree extent native resolution


def init_ee():
    project = os.environ.get("EARTHENGINE_PROJECT")
    if not project:
        raise RuntimeError(
            "Set EARTHENGINE_PROJECT first. Example (PowerShell):\n"
            '  $env:EARTHENGINE_PROJECT = "your-gcp-project-id"'
        )
    ee.Initialize(project=project)


def load_assets_and_thermal():
    assets = pd.read_csv(BASE / "business" / "assets.csv")[
        ["asset_id", "asset_type", "parcel_id"]
    ]
    thermal = pd.read_csv(BASE / "business" / "thermal_observations.csv")
    thermal = thermal[thermal["t_asset_c"].notna()][
        ["asset_id", "t_asset_c", "t_township_c", "surface_temp_delta_c"]
    ]

    parcels = gpd.read_file(BASE / "geometry" / "parcels_bj.geojson")
    parcels["asset_id"] = parcels["asset_id"].astype(str)

    footprint = (
        assets
        .merge(parcels[["asset_id", "geometry"]], on="asset_id", how="inner")
        .dropna(subset=["geometry"])
    )
    footprint = gpd.GeoDataFrame(footprint, geometry="geometry", crs=parcels.crs)
    footprint_wgs = footprint.to_crs("EPSG:4326")

    return footprint_wgs, thermal


def fix_and_orient_geometry(geom):
    """强制多边形拓扑合法并修正环绕方向（解决 BLD-0075 在 GEE 中反向死锁的核心）"""
    try:
        g = geom.buffer(0)
        if g.geom_type == 'Polygon':
            return orient(g, sign=1.0)
        elif g.geom_type == 'MultiPolygon':
            from shapely.geometry import MultiPolygon
            return MultiPolygon([orient(p, sign=1.0) for p in g.geoms])
        return g
    except Exception:
        return geom

import concurrent.futures

import concurrent.futures

def fetch_wri_means(footprint_wgs):
    footprint_clean = footprint_wgs.copy()
    footprint_clean["geometry"] = footprint_clean["geometry"].apply(lambda g: g.buffer(0))

    minx, miny, maxx, maxy = footprint_clean.total_bounds
    study_box = ee.Geometry.Rectangle([float(minx), float(miny), float(maxx), float(maxy)])

    image = (
        ee.ImageCollection(WRI_ASSET)
        .filterBounds(study_box)
        .select("b1")
        .mosaic()
    )

    features = []
    asset_ids_list = []  # 新增：单独存一份纯本地 Python ID 列表
    for _, row in footprint_clean.iterrows():
        aid = str(row["asset_id"])
        features.append(
            ee.Feature(
                ee.Geometry(row.geometry.__geo_interface__),
                {"asset_id": aid}
            )
        )
        asset_ids_list.append(aid)

    batch_size = 20
    total = len(features)
    print(f"Total assets: {total}. Processing in batches of {batch_size} with 15s Hard Timeout...")

    rows = []
    for i in range(0, total, batch_size):
        chunk = features[i:i + batch_size]
        chunk_ids = asset_ids_list[i:i + batch_size]  # 提取对应的纯本地 ID
        chunk_fc = ee.FeatureCollection(chunk)

        def _request_gee():
            return image.reduceRegions(
                collection=chunk_fc,
                reducer=ee.Reducer.mean().combine(reducer2=ee.Reducer.count(), sharedInputs=True),
                scale=SCALE_M,
                tileScale=16,
            ).getInfo()["features"]

        records = []
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(_request_gee)
        
        try:
            records = future.result(timeout=15)
        except concurrent.futures.TimeoutError:
            print(f"\n[TIMEOUT] Batch {i}-{i+len(chunk)} hangs. Force skipped.", flush=True)
        except Exception as exc:
            print(f"\n[ERROR] Batch {i}-{i+len(chunk)} failed ({exc}). Skipped.", flush=True)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        if not records:
            # 修正 Bug：直接遍历本地字符串 ID，彻底避开 ee.Feature 的解包错误
            records = [{"properties": {"asset_id": aid, "mean": None, "count": 0}} for aid in chunk_ids]

        for feat in records:
            props = feat["properties"]
            rows.append({
                "asset_id": props.get("asset_id"),
                "wri_treecover_mean": props.get("mean"),
                "wri_valid_pixels": props.get("count"),
                "wri_band": "b1",
            })
            
        print(f"[{min(i + batch_size, total)}/{total}] assets processed.", flush=True)

    return pd.DataFrame(rows)


def normalise_scale(df):
    df = df.copy()
    df["wri_treecover_raw"] = df["wri_treecover_mean"]
    if df["wri_treecover_mean"].max(skipna=True) is not None and \
       df["wri_treecover_mean"].max(skipna=True) > 1.5:
        df["wri_treecover_fraction"] = df["wri_treecover_mean"] / 100.0
    else:
        df["wri_treecover_fraction"] = df["wri_treecover_mean"]
    return df


def main():
    init_ee()
    footprint_wgs, thermal = load_assets_and_thermal()
    print(f"Assets with footprint: {len(footprint_wgs)}")
    print(f"Assets with valid Landsat ΔT: {len(thermal)}")

    wri = fetch_wri_means(footprint_wgs)
    wri = normalise_scale(wri)

    assets = pd.read_csv(BASE / "business" / "assets.csv")[["asset_id", "asset_type"]]
    merged = (
        wri
        .merge(thermal, on="asset_id", how="inner")
        .merge(assets, on="asset_id", how="left")
        .dropna(subset=["wri_treecover_fraction", "surface_temp_delta_c"])
    )

    print(f"\nPaired samples (WRI + Landsat ΔT): {len(merged)}")
    if len(merged) < 30:
        print("Too few paired samples. Stopping.")
        return

    r_all, p_all = pearsonr(
        merged["wri_treecover_fraction"],
        merged["surface_temp_delta_c"],
    )

    non_green = merged[merged["asset_type"] != "green_space"]
    r_ng, p_ng = pearsonr(
        non_green["wri_treecover_fraction"],
        non_green["surface_temp_delta_c"],
    )

    print("\n" + "=" * 72)
    print("PEARSON CORRELATION: WRI tree cover fraction vs Landsat ΔT")
    print("=" * 72)
    print(f"All samples (n={len(merged)}):       r = {r_all:+.3f}  (p = {p_all:.4f})")
    print(f"Excl. green_space (n={len(non_green)}): r = {r_ng:+.3f}  (p = {p_ng:.4f})")

    print("\n" + "=" * 72)
    print("WRI TREE COVER DISTRIBUTION")
    print("=" * 72)
    print(merged["wri_treecover_fraction"].describe().round(3))
    print(f"\nzeros: {(merged['wri_treecover_fraction'] == 0).sum()} / {len(merged)}")
    print(f">0.3:  {(merged['wri_treecover_fraction'] > 0.3).sum()} / {len(merged)}")

    x = non_green["wri_treecover_fraction"].values
    y = non_green["surface_temp_delta_c"].values
    slope, intercept = np.polyfit(x, y, 1)
    print("\n" + "=" * 72)
    print("LINEAR FIT  ΔT = a + b × WRI_canopy_fraction   (excl. green_space)")
    print("=" * 72)
    print(f"  intercept = {intercept:+.3f} °C")
    print(f"  slope     = {slope:+.3f} °C per unit canopy fraction")
    print(f"  → 10-pt canopy increase → {slope * 0.10:+.3f} °C")
    print(f"  → 20-pt canopy increase → {slope * 0.20:+.3f} °C")

    print("\n" + "=" * 72)
    print("GATE B VERDICT")
    print("=" * 72)
    if r_ng <= -0.30 and p_ng < 0.01 and len(non_green) >= 500:
        print("✓ PASS — WRI canopy has a real, negative relationship with ΔT.")
        print("  → Proceed with canopy replacement and B4 coupling.")
    elif r_ng <= -0.20 and p_ng < 0.05:
        print("⚠ MARGINAL — relationship exists but weaker than -0.30.")
        print("  → Coupling will produce modest shifts; document the weakness.")
    else:
        print("✗ FAIL — WRI canopy does not explain ΔT at this resolution.")
        print("  → Do NOT couple. Keep WRI as a display field only.")

    out = BASE / "business" / "wri_canopy_test.csv"
    merged.to_csv(out, index=False)
    print(f"\nSaved paired data to: {out}")


if __name__ == "__main__":
    main()