import geopandas as gpd

for name in [
    "buildings",
    "amenities",
    "green_blue",
    "network_edges",
    "parcels",
]:
    gdf = gpd.read_file(f"{name}.geojson")
    print(f"{name}: {len(gdf)} 行数据")