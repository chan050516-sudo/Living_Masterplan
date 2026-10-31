import os
from pathlib import Path
import ee
import geopandas as gpd
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE = REPO_ROOT / "bukit_jelutong" / "processed"

# 1. 初始化
ee.Initialize(project=os.environ.get("EARTHENGINE_PROJECT"))

# 2. 读取地块
assets = pd.read_csv(BASE / "business" / "assets.csv")[["asset_id", "asset_type", "parcel_id"]]
parcels = gpd.read_file(BASE / "geometry" / "parcels_bj.geojson")
parcels["asset_id"] = parcels["asset_id"].astype(str)

footprint = assets.merge(parcels[["asset_id", "geometry"]], on="asset_id", how="inner").dropna(subset=["geometry"])
footprint = gpd.GeoDataFrame(footprint, geometry="geometry", crs=parcels.crs).to_crs("EPSG:4326")

# 3. 截取第 300 到 330 项
subset = footprint.iloc[300:330]
print(f"Testing assets in range [300:330], count: {len(subset)}")

# 4. 构建外包范围
minx, miny, maxx, maxy = subset.total_bounds
study_box = ee.Geometry.Rectangle([minx, miny, maxx, maxy])

image = (
    ee.ImageCollection("projects/wri-datalab/TropicalTreeCover")
    .filterBounds(study_box)
    .select("b1")
    .mosaic()
    .clip(study_box)
)

for idx, (_, row) in enumerate(subset.iterrows(), start=300):
    aid = row["asset_id"]
    geom = row.geometry
    geom_type = geom.geom_type
    coords_count = len(geom.exterior.coords) if geom_type == 'Polygon' else sum(len(p.exterior.coords) for p in geom.geoms)
    is_valid = geom.is_valid

    print(f"Index {idx} | asset_id: {aid} | Type: {geom_type} | Vertices: {coords_count} | Valid: {is_valid} ... ", end="", flush=True)

    try:
        ee_geom = ee.Geometry(geom.__geo_interface__)
        fc = ee.FeatureCollection([ee.Feature(ee_geom, {"asset_id": str(aid)})])
        res = image.reduceRegions(
            collection=fc, 
            reducer=ee.Reducer.mean(), 
            scale=10,
            tileScale=16
        ).getInfo()
        val = res["features"][0]["properties"].get("mean")
        print(f"OK (mean: {val})")
    except Exception as e:
        print(f"FAILED! -> {e}")