import json
import os
import time
from datetime import datetime, timezone

import geopandas as gpd
import osmnx as ox
import pandas as pd

# --- OSMnx 2.x settings ---
ox.settings.requests_timeout = 300
ox.settings.use_cache = True              # reruns reuse already-downloaded results
ox.settings.overpass_rate_limit = False   # mirrors may not support the /status check

# Base URLs: end with /api, NOT /interpreter (OSMnx 2.x appends it)
OVERPASS_URLS = [
    "https://overpass.private.coffee/api",
    "https://overpass.kumi.systems/api",
    "https://overpass.openstreetmap.fr/api",
    "https://maps.mail.ru/osm/tools/overpass/api",
    "https://overpass-api.de/api",
]

# Skip a step if its output file already exists (set False to force re-run)
SKIP_EXISTING = True

# Coordinates / CRS
CENTER_POINT = (3.1775, 101.5180)
DIST_M = 707
COMPUTE_CRS = "EPSG:32647"
DISPLAY_CRS = "EPSG:4326"


def generate_ids(gdf, prefix):
    """Generates sequential IDs matching the Masterplan ID convention."""
    return [f"{prefix}{str(i + 1).zfill(4)}" for i in range(len(gdf))]


def safe_ox_call(func, *args, **kwargs):
    """Try each Overpass mirror (with a retry) until one succeeds."""
    last_err = None
    for url in OVERPASS_URLS:
        ox.settings.overpass_url = url
        for attempt in range(2):
            try:
                print(f"Using {url} (attempt {attempt + 1})")
                return func(*args, **kwargs)
            except Exception as e:
                last_err = e
                print(f"  failed: {str(e)[:150]}")
                time.sleep(5)
    raise RuntimeError(f"All Overpass mirrors failed. Last error: {last_err}")


def polygons_only(gdf):
    return gdf[gdf.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()


def normalize_building_type(value):
    """Map OSM building tags to the controlled building-type vocabulary."""
    building_type = str(value).strip().lower()
    categories = {
        "commercial": {
            "commercial",
            "office",
            "retail",
        },
        "community_facility": {
            "community_centre",
            "social_facility",
        },
        "residential": {
            "apartments",
            "bungalow",
            "detached",
            "house",
            "residential",
            "semidetached_house",
            "terrace",
        },
        "mixed_use": {"mixed_use"},
        "industrial": {
            "factory",
            "industrial",
            "warehouse",
        },
        "institutional": {
            "college",
            "kindergarten",
            "school",
            "university",
        },
    }
    for category, values in categories.items():
        if building_type in values:
            return category
    return "unknown"


def parse_floors(value):
    """Return a non-negative integer floor count, or None when OSM has no usable value."""
    try:
        floors = float(value)
    except (TypeError, ValueError):
        return None
    if floors < 0 or not floors.is_integer():
        return None
    return int(floors)


def assign_parcel_ids(buildings_projected, parcels_projected):
    """Link each building to the smallest parcel polygon covering its representative point."""
    parcel_geometries = [
        (row.parcel_id, row.geometry, row.geometry.area)
        for row in parcels_projected.itertuples()
    ]
    parcel_ids = []
    for geometry in buildings_projected.geometry:
        point = geometry.representative_point()
        candidates = [
            (parcel_id, area)
            for parcel_id, parcel_geometry, area in parcel_geometries
            if parcel_geometry.covers(point)
        ]
        parcel_ids.append(
            min(candidates, key=lambda candidate: candidate[1])[0]
            if candidates
            else "P-UNASSIGNED"
        )
    return parcel_ids


def process_buildings():
    print("Fetching Buildings...")
    tags = {"building": True}
    gdf = safe_ox_call(
        ox.features_from_point, CENTER_POINT, dist=DIST_M, tags=tags
    )
    gdf = polygons_only(gdf)

    gdf_proj = gdf.to_crs(COMPUTE_CRS)
    gdf["area_m2"] = gdf_proj.geometry.area
    if not os.path.exists("parcels.geojson"):
        raise FileNotFoundError(
            "parcels.geojson is required to assign building parcel_id values."
        )
    parcels = gpd.read_file("parcels.geojson").to_crs(COMPUTE_CRS)
    gdf["building_id"] = generate_ids(gdf, "BLD-")
    gdf["parcel_id"] = assign_parcel_ids(gdf_proj, parcels)
    gdf["asset_id"] = gdf["building_id"].map(
        lambda building_id: f"unlinked-{building_id}"
    )
    gdf["building_type"] = gdf["building"].map(normalize_building_type)
    levels = gdf.get("building:levels", pd.Series(None, index=gdf.index))
    gdf["floors"] = levels.map(parse_floors)
    gdf["gfa_m2"] = gdf["area_m2"]
    gdf["geometry_source"] = "OpenStreetMap"

    final_gdf = gdf[
        [
            "building_id",
            "parcel_id",
            "asset_id",
            "building_type",
            "floors",
            "gfa_m2",
            "geometry_source",
            "geometry",
        ]
    ].to_crs(DISPLAY_CRS)
    features = json.loads(final_gdf.to_json(drop_id=True, na="null"))["features"]
    for feature in features:
        feature["id"] = feature["properties"]["building_id"]
    metadata = {
        "schema_version": "1.0.0",
        "region_id": "kuala-lumpur-malaysia",
        "storage_crs": "EPSG:4326",
        "analysis_crs": COMPUTE_CRS,
        "generated_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
    }
    with open("buildings.geojson", "w", encoding="utf-8") as output:
        output.write('{\n  "type": "FeatureCollection",\n  "metadata": ')
        output.write(json.dumps(metadata, indent=2).replace("\n", "\n  "))
        output.write(',\n  "features": [\n')
        for index, feature in enumerate(features):
            if index:
                output.write(",\n")
            output.write("    ")
            json.dump(feature, output, separators=(",", ":"), allow_nan=False)
        output.write("\n  ]\n}\n")
    print(f"Saved {len(final_gdf)} buildings.")


def process_parcels():
    print("Fetching Parcels (Land Use)...")
    tags = {
        "landuse": [
            "residential",
            "commercial",
            "retail",
            "industrial",
            "construction",
            "brownfield",
        ]
    }
    gdf = safe_ox_call(
        ox.features_from_point, CENTER_POINT, dist=DIST_M, tags=tags
    )
    gdf = polygons_only(gdf)

    gdf_proj = gdf.to_crs(COMPUTE_CRS)
    gdf["area_m2"] = gdf_proj.geometry.area

    gdf["parcel_id"] = generate_ids(gdf, "P-")
    gdf["land_use"] = gdf["landuse"].fillna("unclassified")
    gdf["geometry_source"] = "OSM"
    gdf["geometry_confidence"] = "Low (OSM inferred)"

    final_gdf = gdf[
        [
            "parcel_id",
            "land_use",
            "area_m2",
            "geometry_source",
            "geometry_confidence",
            "geometry",
        ]
    ].to_crs(DISPLAY_CRS)
    final_gdf.to_file("parcels.geojson", driver="GeoJSON")
    print(f"Saved {len(final_gdf)} parcels.")


def process_network():
    print("Fetching Walk Network...")
    G = safe_ox_call(
        ox.graph_from_point, CENTER_POINT, dist=DIST_M, network_type="walk"
    )

    nodes, edges = ox.graph_to_gdfs(G)

    edges_proj = edges.to_crs(COMPUTE_CRS)
    edges["length_m"] = edges_proj.geometry.length
    edges = edges.reset_index()

    edges["edge_id"] = generate_ids(edges, "E-")
    edges["edge_type"] = edges["highway"].astype(str)
    edges["walk_speed_kmh"] = 4.5

    final_edges = edges[
        [
            "edge_id",
            "edge_type",
            "u",
            "v",
            "length_m",
            "walk_speed_kmh",
            "geometry",
        ]
    ].to_crs(DISPLAY_CRS)
    final_edges = final_edges.rename(columns={"u": "from_node", "v": "to_node"})
    final_edges.to_file("network_edges.geojson", driver="GeoJSON")
    print(f"Saved {len(final_edges)} network edges.")


def process_green_blue():
    print("Fetching Green & Blue Spaces...")
    # Split into smaller queries so each one is less likely to time out
    tag_sets = [
        {"leisure": ["park", "nature_reserve", "pitch", "golf_course"]},
        {"natural": ["water", "wood", "scrub", "tree_row"]},
        {"landuse": ["grass", "forest", "recreation_ground"]},
    ]
    parts = [
        safe_ox_call(ox.features_from_point, CENTER_POINT, dist=DIST_M, tags=t)
        for t in tag_sets
    ]
    gdf = gpd.GeoDataFrame(pd.concat(parts), crs=parts[0].crs)
    gdf = gdf[~gdf.index.duplicated(keep="first")]
    gdf = polygons_only(gdf)

    # Make sure the columns exist even if a query returned nothing for that key
    for col in ["leisure", "natural", "landuse"]:
        if col not in gdf.columns:
            gdf[col] = None

    gdf_proj = gdf.to_crs(COMPUTE_CRS)
    gdf["area_m2"] = gdf_proj.geometry.area

    gdf["green_id"] = generate_ids(gdf, "G-")
    gdf["green_type"] = (
        gdf["leisure"]
        .combine_first(gdf["natural"])
        .combine_first(gdf["landuse"])
        .fillna("unknown")
    )
    gdf["canopy_m2"] = gdf["area_m2"] * 0.5
    gdf["geometry_source"] = "OSM"

    final_gdf = gdf[
        [
            "green_id",
            "green_type",
            "area_m2",
            "canopy_m2",
            "geometry_source",
            "geometry",
        ]
    ].to_crs(DISPLAY_CRS)
    final_gdf.to_file("green_blue.geojson", driver="GeoJSON")
    print(f"Saved {len(final_gdf)} green/blue spaces.")


def process_amenities():
    print("Fetching Amenities...")
    tags = {"amenity": True}
    gdf = safe_ox_call(
        ox.features_from_point, CENTER_POINT, dist=DIST_M, tags=tags
    )

    gdf = gdf.reset_index()
    gdf["amenity_id"] = generate_ids(gdf, "A-")
    gdf["amenity_type"] = gdf["amenity"].fillna("unknown")
    gdf["capacity"] = 0

    final_gdf = gdf[
        ["amenity_id", "amenity_type", "capacity", "geometry"]
    ].to_crs(DISPLAY_CRS)
    final_gdf.to_file("amenities.geojson", driver="GeoJSON")
    print(f"Saved {len(final_gdf)} amenities.")


def run_step(func, output_file):
    if SKIP_EXISTING and os.path.exists(output_file):
        print(f"Skipping {func.__name__}: {output_file} already exists.")
        return
    func()


if __name__ == "__main__":
    print("Starting Module A GeoJSON Pipeline...")
    run_step(process_parcels, "parcels.geojson")
    run_step(process_buildings, "buildings.geojson")
    run_step(process_network, "network_edges.geojson")
    run_step(process_green_blue, "green_blue.geojson")
    run_step(process_amenities, "amenities.geojson")
    print("Task A2 & A5 Complete. Proceed to QGIS for Task A3 (Validation).")