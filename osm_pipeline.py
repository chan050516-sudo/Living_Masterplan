import json
import math
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


def layer_metadata():
    return {
        "schema_version": "1.0.0",
        "region_id": "kuala-lumpur-malaysia",
        "storage_crs": "EPSG:4326",
        "analysis_crs": COMPUTE_CRS,
        "generated_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
    }


def write_feature_collection(output_file, features):
    with open(output_file, "w", encoding="utf-8") as output:
        output.write('{\n  "type": "FeatureCollection",\n  "metadata": ')
        output.write(json.dumps(layer_metadata(), indent=2).replace("\n", "\n  "))
        output.write(',\n  "features": [\n')
        for index, feature in enumerate(features):
            if index:
                output.write(",\n")
            output.write("    ")
            json.dump(feature, output, separators=(",", ":"), allow_nan=False)
        output.write("\n  ]\n}\n")


def geodataframe_features(gdf, id_column):
    features = json.loads(gdf.to_json(drop_id=True, na="null"))["features"]
    for feature in features:
        feature["id"] = str(feature["properties"][id_column])
    return features


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


def normalize_edge_type(value):
    """Map OSM highway tags to the controlled network edge vocabulary."""
    allowed_types = {
        "footway",
        "pedestrian",
        "path",
        "residential",
        "service",
        "living_street",
        "steps",
        "track",
        "secondary",
        "tertiary",
        "primary",
        "unclassified",
        "transit",
    }
    values = value if isinstance(value, (list, tuple, set)) else [value]
    for edge_type in values:
        if edge_type in allowed_types:
            return edge_type
    return None


def normalize_access_type(value):
    """Normalize OSM access tags to the network schema's access categories."""
    access = str(value).strip().lower()
    if access == "private":
        return "private"
    if access in {"no", "restricted", "destination", "customers"}:
        return "restricted"
    return "public"


def calculate_canopy_coverage_ratio(edge_geometry, canopy_geometry, canopy_fraction):
    """Estimate shade as the edge fraction in mapped canopy areas times their canopy ratio."""
    if edge_geometry.length == 0 or canopy_geometry.is_empty:
        return 0.0
    covered_length = edge_geometry.intersection(canopy_geometry).length
    return min(1.0, max(0.0, covered_length / edge_geometry.length * canopy_fraction))


def normalize_land_use(value):
    land_use = str(value).strip().lower()
    if land_use in {"commercial", "retail"}:
        return "commercial"
    if land_use in {"community_centre", "social_facility"}:
        return "community_facility"
    if land_use == "residential":
        return "residential"
    if land_use == "mixed_use":
        return "mixed_use"
    if land_use in {
        "brownfield",
        "construction",
        "greenfield",
        "vacant",
        "vacant_lot",
    }:
        return "undeveloped"
    if land_use in {"forest", "grass", "green", "meadow", "park", "recreation_ground"}:
        return "green_space"
    if land_use in {"railway", "road", "transport", "utility"}:
        return "infrastructure"
    return "unknown"


def normalize_green_type(leisure, natural, landuse, waterway):
    tags = {
        str(value).strip().lower()
        for value in (leisure, natural, landuse, waterway)
        if value is not None and not pd.isna(value)
    }
    if tags & {"drain", "ditch", "canal"}:
        return "drainage"
    if tags & {"water", "river", "stream", "riverbank", "wetland"}:
        return "water_body"
    if tags & {"wood", "forest", "tree_row", "trees"}:
        return "canopy"
    if tags & {"park", "nature_reserve"}:
        return "park"
    if tags & {"pitch", "golf_course", "recreation_ground", "grass", "scrub"}:
        return "public_space"
    return "public_space"


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
    write_feature_collection("buildings.geojson", features)
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
    gdf["land_use"] = gdf["landuse"].map(normalize_land_use)
    gdf["asset_id"] = None
    gdf["geometry_source"] = "OpenStreetMap"
    gdf["geometry_confidence"] = "low"

    final_gdf = gdf[
        [
            "parcel_id",
            "asset_id",
            "land_use",
            "area_m2",
            "geometry_source",
            "geometry_confidence",
            "geometry",
        ]
    ].to_crs(DISPLAY_CRS)
    write_feature_collection(
        "parcels.geojson", geodataframe_features(final_gdf, "parcel_id")
    )
    print(f"Saved {len(final_gdf)} parcels.")


def process_network():
    print("Fetching Complete Study-Area Network...")
    study_layers = [
        gpd.read_file("buildings.geojson"),
        gpd.read_file("green_blue.geojson"),
    ]
    study_bounds = [
        layer.to_crs(COMPUTE_CRS).total_bounds for layer in study_layers if not layer.empty
    ]
    if not study_bounds:
        raise ValueError("Buildings and green/blue layers contain no study-area geometries.")
    west = min(bounds[0] for bounds in study_bounds)
    south = min(bounds[1] for bounds in study_bounds)
    east = max(bounds[2] for bounds in study_bounds)
    north = max(bounds[3] for bounds in study_bounds)
    center = (
        gpd.GeoSeries(
            [gpd.points_from_xy([CENTER_POINT[1]], [CENTER_POINT[0]])[0]],
            crs=DISPLAY_CRS,
        )
        .to_crs(COMPUTE_CRS)
        .iloc[0]
    )
    network_dist = max(
        math.hypot(x - center.x, y - center.y)
        for x in (west, east)
        for y in (south, north)
    ) + 100
    print(f"Study-area network radius: {network_dist:.0f} m (includes 100 m margin)")
    G = safe_ox_call(
        ox.graph_from_point,
        CENTER_POINT,
        dist=network_dist,
        network_type="all",
        retain_all=True,
    )

    _, edges = ox.graph_to_gdfs(G)
    edges = edges.reset_index()
    edges["edge_type"] = edges["highway"].map(normalize_edge_type)
    edges = edges[edges["edge_type"].notna()].copy()
    edges_proj = edges.to_crs(COMPUTE_CRS)
    edges["length_m"] = edges_proj.geometry.length
    edges["edge_id"] = generate_ids(edges, "E-")
    edges["from_node"] = edges["u"].map(lambda node_id: f"N-{node_id}")
    edges["to_node"] = edges["v"].map(lambda node_id: f"N-{node_id}")
    edges["walk_speed_kmh"] = 4.5

    access_foot = edges.get("access:foot", pd.Series(None, index=edges.index))
    access_general = edges.get("access", pd.Series(None, index=edges.index))
    edges["access_type"] = [
        normalize_access_type(foot_access if pd.notna(foot_access) else general_access)
        for foot_access, general_access in zip(access_foot, access_general)
    ]

    if not os.path.exists("green_blue.geojson"):
        raise FileNotFoundError(
            "green_blue.geojson is required to estimate network canopy coverage."
        )
    green = gpd.read_file("green_blue.geojson").to_crs(COMPUTE_CRS)
    green["canopy_fraction"] = green["canopy_m2"] / green["area_m2"]
    canopy_areas = green[
        (green["green_type"] == "canopy")
        & green["canopy_m2"].notna()
        & (green["canopy_fraction"] > 0)
    ]
    canopy_geometry = canopy_areas.geometry.union_all()
    canopy_fraction = (
        (canopy_areas["area_m2"] * canopy_areas["canopy_fraction"]).sum()
        / canopy_areas["area_m2"].sum()
        if not canopy_areas.empty
        else 0.0
    )
    edges["canopy_coverage_ratio"] = [
        calculate_canopy_coverage_ratio(geometry, canopy_geometry, canopy_fraction)
        for geometry in edges_proj.geometry
    ]

    final_edges = edges[
        [
            "edge_id",
            "edge_type",
            "from_node",
            "to_node",
            "length_m",
            "walk_speed_kmh",
            "access_type",
            "canopy_coverage_ratio",
            "geometry",
        ]
    ].to_crs(DISPLAY_CRS)
    write_feature_collection(
        "network_edges.geojson", geodataframe_features(final_edges, "edge_id")
    )
    print(f"Saved {len(final_edges)} network edges.")


def process_green_blue():
    print("Fetching Green & Blue Spaces...")
    # Split into smaller queries so each one is less likely to time out
    tag_sets = [
        {"leisure": ["park", "nature_reserve", "pitch", "golf_course"]},
        {"natural": ["water", "wood", "scrub", "tree_row"]},
        {"landuse": ["grass", "forest", "recreation_ground"]},
        {"waterway": ["canal", "ditch", "drain", "river", "stream"]},
    ]
    parts = [
        safe_ox_call(ox.features_from_point, CENTER_POINT, dist=DIST_M, tags=t)
        for t in tag_sets
    ]
    gdf = gpd.GeoDataFrame(pd.concat(parts), crs=parts[0].crs)
    gdf = gdf[~gdf.index.duplicated(keep="first")]

    # Make sure the columns exist even if a query returned nothing for that key
    for col in ["leisure", "natural", "landuse", "waterway"]:
        if col not in gdf.columns:
            gdf[col] = None

    gdf_proj = gdf.to_crs(COMPUTE_CRS)
    gdf["area_m2"] = gdf_proj.geometry.area

    gdf["green_id"] = generate_ids(gdf, "G-")
    gdf["green_type"] = [
        normalize_green_type(leisure, natural, landuse, waterway)
        for leisure, natural, landuse, waterway in zip(
            gdf["leisure"], gdf["natural"], gdf["landuse"], gdf["waterway"]
        )
    ]
    gdf["asset_id"] = gdf["green_id"].map(
        lambda green_id: f"unlinked-{green_id}"
    )
    gdf["canopy_m2"] = [
        area
        if green_type == "canopy" and geometry_type in {"Polygon", "MultiPolygon"}
        else None
        for area, green_type, geometry_type in zip(
            gdf["area_m2"], gdf["green_type"], gdf.geometry.type
        )
    ]
    gdf["geometry_source"] = "OpenStreetMap"

    final_gdf = gdf[
        [
            "green_id",
            "asset_id",
            "green_type",
            "area_m2",
            "canopy_m2",
            "geometry_source",
            "geometry",
        ]
    ].to_crs(DISPLAY_CRS)
    write_feature_collection(
        "green_blue.geojson", geodataframe_features(final_gdf, "green_id")
    )
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
    run_step(process_green_blue, "green_blue.geojson")
    run_step(process_network, "network_edges.geojson")
    run_step(process_amenities, "amenities.geojson")
    print("Task A2 & A5 Complete. Proceed to QGIS for Task A3 (Validation).")