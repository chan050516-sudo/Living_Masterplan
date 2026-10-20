import pandas as pd
df = pd.read_csv("bukit_jelutong/processed/business/assets.csv")

print("=== asset_type distribution ===")
print(df["asset_type"].value_counts())

print("\n=== ownership_status distribution ===")
print(df["ownership_status"].value_counts())

print("\n=== converted shoplot (commercial + completion 2018-2026) ===")
shops = df[
    (df["asset_type"] == "commercial")
    & (df["completion_year"] >= 2018)
]
print(f"count: {len(shops)}")
print(shops[["asset_id", "subtype", "completion_year",
             "lettable_area_m2", "capacity"]].head(12))

print("\n=== unsold residential (ownership=developer_held) ===")
unsold = df[
    (df["asset_type"] == "residential")
    & (df["ownership_status"] == "developer_held")
]
print(f"count: {len(unsold)}")
print(unsold[["asset_id", "completion_year"]].head(5))



import geopandas as gpd
import json

parcels = gpd.read_file(
    "bukit_jelutong/processed/geometry/parcels_bj.geojson"
)
buildings = gpd.read_file(
    "bukit_jelutong/processed/geometry/buildings_bj.geojson"
)

vac = parcels[parcels["parcel_id"].str.startswith("P-VAC-")].to_crs("EPSG:32647")
b = buildings.to_crs("EPSG:32647")

print(f"Vacant parcels: {len(vac)}")
print(vac[["parcel_id", "area_m2"]].to_string())

# 检查 1：每个 P-VAC 和任何 building 是否重叠
overlaps = []
for _, v in vac.iterrows():
    try:
        inter_area = b.geometry.intersection(v.geometry).area.sum()
    except Exception:
        inter_area = 0.0
    if inter_area > 1.0:
        overlaps.append((v["parcel_id"], round(inter_area, 1)))

# 检查 2：P-VAC 之间是否相互重叠
from shapely.ops import unary_union
if len(vac) > 1:
    total_union = vac.geometry.union_all()
    total_area = vac.geometry.area.sum()
    union_area = total_union.area
    if abs(total_area - union_area) > 1.0:
        print(f"\nWARNING: P-VAC parcels overlap each other "
              f"(sum={total_area:.0f}, union={union_area:.0f})")
    else:
        print("\nP-VAC parcels do not overlap each other")

# 检查 3：每个 P-VAC 的面积
print(f"\nP-VAC area range: {vac['area_m2'].min():.0f} - {vac['area_m2'].max():.0f} m²")