import os
import sys
import urllib.request
from pathlib import Path
import ee
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.mask import mask
from shapely.geometry import mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE = REPO_ROOT / "bukit_jelutong" / "processed"
WRI_ASSET = "projects/wri-datalab/TropicalTreeCover"
SCALE_M = 10

def init_ee():
    project = os.environ.get("EARTHENGINE_PROJECT")
    if not project:
        raise ValueError("Set EARTHENGINE_PROJECT environment variable first.")
    ee.Initialize(project=project)

def get_footprints():
    parcels = gpd.read_file(BASE / "geometry" / "parcels_bj.geojson")
    buildings = gpd.read_file(BASE / "geometry" / "buildings_bj.geojson").to_crs(parcels.crs)
    green = gpd.read_file(BASE / "geometry" / "green_blue_bj.geojson").to_crs(parcels.crs)
    assets = pd.read_csv(BASE / "business" / "assets.csv")

    def group_by_key(df, key):
        if key not in df.columns: return {}
        df = df[df[key].notna() & df.geometry.notna()].copy()
        df[key] = df[key].astype(str)
        return {str(k): g.geometry.union_all() for k, g in df.groupby(key, sort=False)}

    b_dict = group_by_key(buildings, "building_id")
    g_dict = group_by_key(green, "asset_id")
    p_dict = group_by_key(parcels, "parcel_id")
    pa_dict = group_by_key(parcels, "asset_id")

    records = []
    for row in assets.to_dict(orient="records"):
        aid = str(row["asset_id"])
        geom = None
        if row.get("asset_type") == "green_space": geom = g_dict.get(aid)
        if geom is None and row.get("building_id") and str(row["building_id"]) != 'nan':
            geom = b_dict.get(str(row["building_id"]))
        if geom is None and row.get("parcel_id") and str(row["parcel_id"]) != 'nan':
            geom = p_dict.get(str(row["parcel_id"]))
        if geom is None: geom = pa_dict.get(aid)
        
        if geom is not None and not geom.is_empty:
            if not geom.is_valid: geom = geom.make_valid()
            records.append({"asset_id": aid, "geometry": geom})

    return gpd.GeoDataFrame(records, geometry="geometry", crs=parcels.crs).to_crs("EPSG:4326")

def main():
    init_ee()
    footprints = get_footprints()
    minx, miny, maxx, maxy = footprints.total_bounds
    region = ee.Geometry.Rectangle([minx, miny, maxx, maxy])
    
    image = ee.ImageCollection(WRI_ASSET).filterBounds(region).select("b1").mosaic()
    
    tif_path = BASE / "wri_treecover_bj.tif"
    print("Downloading WRI GeoTIFF from GEE...")
    url = image.getDownloadURL({
        "region": region, "scale": SCALE_M, "crs": "EPSG:32647", "format": "GEO_TIFF"
    })
    with urllib.request.urlopen(url) as resp:
        tif_path.write_bytes(resp.read())
    print(f"Saved to {tif_path}")

    # 本地 Zonal Stats
    proj = footprints.to_crs("EPSG:32647")
    results = []
    print(f"Running local zonal stats for {len(proj)} assets...")
    with rasterio.open(tif_path) as src:
        for _, row in proj.iterrows():
            try:
                out_image, _ = mask(src, [mapping(row.geometry)], crop=True, filled=False, all_touched=True)
                data = np.asarray(out_image.data, dtype='float64')
                valid = ~np.ma.getmaskarray(out_image) & np.isfinite(data) & (data != -9999) & (data != 0)
                count = int(valid.sum())
                mean_val = float(data[valid].mean()) if count > 0 else 0.0
                results.append({
                    "asset_id": row["asset_id"],
                    "wri_treecover_fraction": mean_val / 100.0 if mean_val > 1.5 else mean_val,
                    "wri_valid_pixels": count
                })
            except Exception:
                results.append({"asset_id": row["asset_id"], "wri_treecover_fraction": None, "wri_valid_pixels": 0})
                
    df = pd.DataFrame(results)
    out = BASE / "business" / "wri_canopy_observations.csv"
    df.to_csv(out, index=False)
    print(f"Extracted {len(df)} assets. Saved to {out}")

if __name__ == "__main__":
    main()