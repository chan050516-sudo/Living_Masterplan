import geopandas as gpd
from pathlib import Path

base = Path(__file__).resolve().parents[2] / "bukit_jelutong" / "processed" / "geometry"
path = base / "green_blue_bj.geojson"
gdf = gpd.read_file(path)

bad = gdf[gdf["area_m2"] == 0]
if not bad.empty:
    print(f"Fixing {len(bad)} zero-area green assets...")
    gdf_proj = gdf.to_crs("EPSG:32647")
    gdf_proj["geometry"] = gdf_proj.geometry.make_valid()
    gdf_proj["area_m2"] = gdf_proj.geometry.area
    gdf = gdf_proj.to_crs("EPSG:4326")
    gdf.to_file(path, driver="GeoJSON")
    print("Fixed and saved.")
else:
    print("No zero-area assets found.")