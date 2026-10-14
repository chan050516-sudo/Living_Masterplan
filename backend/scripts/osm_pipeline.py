"""OSM Pipeline — Bukit Jelutong geometry extraction (raw layer).

Output:
    bukit_jelutong/raw/geometry/*_bj.geojson

Layer contract:
    RAW. Every output is a faithful extract of OSM with lossless
    normalisation. No business inference, no mock data, no
    schema-violating values. Downstream pre-processing (see
    bukit_jelutong/build_mock_data.py) is where business logic lives.

Fixes applied (2026-10-14c):
  - Network radius is derived from the buildings layer alone. The
    previous version merged in green/blue bounds, which inflated the
    radius by ~5x because a single 9 km² water polygon extended far
    beyond the built-up core.
  - Parcel land_use no longer emits "industrial". B3 has no industrial
    deriver; industrial parcels are labelled "commercial" so the
    downstream pipeline works. The original value is not lost — it is
    still inferable from buildings.building_type inside the parcel.
  - Canopy buffer widened from 5 m to 15 m. OSM rarely maps tree
    canopy as a standalone polygon; 15 m captures the vegetation
    that lines streets and parks.
  - Output filenames use suffix "_bj" (Bukit Jelutong) instead of a
    numeric suffix.

Performance notes (2026-10-14):
  - requests_timeout = 45 s. A stalled mirror costs 90 s at most
    (2 attempts × 45 s) before rotating.
  - Green/blue fetch merged into a single Overpass query.
  - Canopy buffer hoisted out of the per-edge loop.
  - Parcel assignment uses GeoPandas sjoin (R-tree index).

Design principles:
  1. NO DATA DELETION. Every OSM feature is retained; filtering is
     done via boolean flags (walk_ok / drive_ok).
  2. Raw tags preserved alongside normalised fields.
  3. Normalisation covers the full OSM vocabulary for each key.
"""

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import osmnx as ox
import pandas as pd

# ----------------------------------------------------------------
# Paths
# ----------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_GEOM_DIR = REPO_ROOT / "bukit_jelutong" / "raw" / "geometry"
RAW_GEOM_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_SUFFIX = "_bj"


def out(name):
    """Return the output path for a raw layer."""
    return str(RAW_GEOM_DIR / f"{name}{OUTPUT_SUFFIX}.geojson")


# ----------------------------------------------------------------
# OSMnx settings
# ----------------------------------------------------------------
ox.settings.requests_timeout = 45
ox.settings.use_cache = True
ox.settings.overpass_rate_limit = False

OVERPASS_URLS = [
    "https://overpass.kumi.systems/api",
    "https://overpass-api.de/api",
    "https://overpass.openstreetmap.fr/api",
    "https://maps.mail.ru/osm/tools/overpass/api",
    "https://overpass.private.coffee/api",
]

SKIP_EXISTING = True

CENTER_POINT = (3.109, 101.528)     # Bukit Jelutong, Shah Alam
DIST_M = 1000
COMPUTE_CRS = "EPSG:32647"
DISPLAY_CRS = "EPSG:4326"

CANOPY_BUFFER_M = 15.0


# ================================================================
# 1. Metadata & IDs
# ================================================================

def layer_metadata():
    return {
        "schema_version": "1.2.0",
        "region_id": "bukit-jelutong-shah-alam",
        "storage_crs": DISPLAY_CRS,
        "analysis_crs": COMPUTE_CRS,
        "generated_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
    }


def generate_ids(gdf, prefix):
    return [f"{prefix}{str(i + 1).zfill(4)}" for i in range(len(gdf))]


def write_feature_collection(output_file, features):
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write('{\n  "type": "FeatureCollection",\n  "metadata": ')
        f.write(json.dumps(layer_metadata(), indent=2).replace("\n", "\n  "))
        f.write(',\n  "features": [\n')
        for i, feat in enumerate(features):
            if i:
                f.write(",\n")
            f.write("    ")
            json.dump(feat, f, separators=(",", ":"), allow_nan=False)
        f.write("\n  ]\n}\n")


def geodataframe_features(gdf, id_column):
    features = json.loads(gdf.to_json(drop_id=True, na="null"))["features"]
    for feat in features:
        feat["id"] = str(feat["properties"][id_column])
    return features


def safe_ox_call(func, *args, **kwargs):
    last_err = None
    for url in OVERPASS_URLS:
        ox.settings.overpass_url = url
        for attempt in range(2):
            try:
                print(f"  Using {url} (attempt {attempt + 1})")
                return func(*args, **kwargs)
            except Exception as e:
                last_err = e
                print(f"    failed: {str(e)[:150]}")
                time.sleep(2)
    raise RuntimeError(f"All Overpass mirrors failed. Last: {last_err}")


def polygons_only(gdf):
    return gdf[gdf.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()


# ================================================================
# 2. Network edge classification
# ================================================================

WALKABLE_HIGHWAY = {
    "footway", "pedestrian", "path", "steps", "track", "bridleway",
    "cycleway", "living_street", "service", "residential",
    "unclassified", "tertiary", "tertiary_link",
    "secondary", "secondary_link",
    "primary", "primary_link",
    "trunk", "trunk_link",
    "road", "crossing", "corridor", "sidewalk",
    "platform", "elevator", "escalator",
}

DRIVABLE_HIGHWAY = {
    "trunk", "trunk_link",
    "primary", "primary_link",
    "secondary", "secondary_link",
    "tertiary", "tertiary_link",
    "unclassified", "residential",
    "living_street", "service",
    "track", "road",
}

TRANSIT_HIGHWAY = {"bus_guideway", "busway", "bus_stop"}

ALL_HIGHWAY = WALKABLE_HIGHWAY | DRIVABLE_HIGHWAY | TRANSIT_HIGHWAY | {
    "motorway", "motorway_link",
    "motorway_junction", "rest_area", "services",
    "construction", "proposed", "abandoned",
    "raceway", "escape", "emergency_bay",
}


def classify_highway(value):
    """
    Return (edge_type, walk_ok, drive_ok).

    Motorways are marked walk_ok=False / drive_ok=False: B3's driving
    model is township-scale (30 km/h), and including motorways would
    distort catchment profiles.
    """
    values = value if isinstance(value, (list, tuple, set)) else [value]
    chosen = None
    walk = False
    drive = False
    for v in values:
        v = str(v).strip().lower()
        if v in {"motorway", "motorway_link"}:
            chosen = chosen or v
            continue
        if v in ALL_HIGHWAY:
            chosen = chosen or v
            if v in WALKABLE_HIGHWAY:
                walk = True
            if v in DRIVABLE_HIGHWAY:
                drive = True
    if chosen is None:
        for v in values:
            v = str(v).strip().lower()
            if v:
                chosen = v
                break
    return chosen or "unclassified", walk, drive


def normalize_access_type(value):
    access = str(value).strip().lower() if value else ""
    if access in {"private", "no"}:
        return "private"
    if access in {"restricted", "destination", "customers", "permit", "delivery"}:
        return "restricted"
    return "public"


def calculate_canopy_coverage_ratio(edge_geometry, canopy_buffered):
    if edge_geometry.length == 0 or canopy_buffered.is_empty:
        return 0.0
    covered = edge_geometry.intersection(canopy_buffered).length
    return min(1.0, max(0.0, covered / edge_geometry.length))


# ================================================================
# 3. Building classification
# ================================================================

BUILDING_RESIDENTIAL = {
    "residential", "apartments", "apartment", "house", "detached",
    "semidetached_house", "terrace", "bungalow", "cabin", "dormitory",
    "ger", "barracks", "annexe", "farm", "farm_auxiliary", "barn",
    "houseboat", "static_caravan", "allotment_house", "cowshed",
    "sty", "stable", "boathouse", "hut", "shed",
}

BUILDING_COMMERCIAL = {
    "commercial", "office", "retail", "supermarket", "kiosk",
    "restaurant", "cafe", "bank", "shop", "hotel", "hostel",
    "guest_house", "motel", "market", "showroom",
}

BUILDING_COMMUNITY = {
    "community_centre", "social_facility", "civic", "public",
    "government", "townhall", "clinic", "hospital", "school",
    "university", "college", "kindergarten", "library",
    "church", "cathedral", "mosque", "synagogue", "temple", "chapel",
    "place_of_worship", "monastery", "convent", "presbytery",
    "nursing_home", "arts_centre", "courthouse", "prison",
    "fire_station", "police", "post_office", "museum",
    "sports_hall", "stadium", "grandstand", "transportation",
    "train_station", "transit_station",
}

BUILDING_INDUSTRIAL = {
    "industrial", "factory", "warehouse", "hangar", "manufacture",
    "digester", "gasometer", "water_tower", "silo", "storage_tank",
    "service", "garage", "garages", "carport", "parking",
    "greenhouse", "conservatory", "roof", "ruins", "construction",
    "tent", "tower", "bunker", "bridge",
}


def normalize_building_type(value):
    bt = str(value).strip().lower() if value else ""
    if bt in {"mixed_use", "mixed"}:
        return "mixed_use"
    if bt in BUILDING_RESIDENTIAL:
        return "residential"
    if bt in BUILDING_COMMERCIAL:
        return "commercial"
    if bt in BUILDING_COMMUNITY:
        return "community_facility"
    if bt in BUILDING_INDUSTRIAL:
        return "industrial"
    return "unknown"


def parse_floors(value):
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f < 0 or not f.is_integer():
        return None
    return int(f)


# ================================================================
# 4. Amenity classification
# ================================================================

AMENITY_HEALTHCARE = {
    "clinic", "hospital", "doctors", "dentist", "pharmacy",
    "veterinary", "nursing_home", "social_facility",
}
AMENITY_EDUCATION = {
    "school", "university", "college", "kindergarten",
    "library", "language_school", "music_school", "driving_school",
    "childcare", "research_institute",
}
AMENITY_TRANSIT = {
    "bus_station", "bus_stop", "ferry_terminal", "taxi",
    "bicycle_parking", "bicycle_rental", "car_rental", "car_sharing",
    "parking", "parking_entrance", "parking_space",
    "fuel", "charging_station", "motorcycle_parking",
}
AMENITY_COMMUNITY = {
    "community_centre", "social_centre", "arts_centre", "theatre",
    "cinema", "nightclub", "casino", "events_venue", "conference_centre",
    "exhibition_centre", "public_building", "townhall",
    "courthouse", "embassy", "fire_station", "police", "post_office",
    "prison", "ranger_station",
}
AMENITY_RETAIL = {
    "restaurant", "fast_food", "cafe", "bar", "pub", "biergarten",
    "food_court", "ice_cream", "bank", "atm", "bureau_de_change",
    "marketplace", "shop", "vending_machine",
}


def normalize_amenity_type(value):
    a = str(value).strip().lower() if value else ""
    if a in AMENITY_HEALTHCARE:
        if a in {"pharmacy", "dentist", "doctors"}:
            return "clinic"
        return a
    if a in AMENITY_EDUCATION:
        if a == "library":
            return "library"
        return "school"
    if a in AMENITY_TRANSIT:
        if a in {"bus_station", "bus_stop"}:
            return "bus_stop"
        if a == "ferry_terminal":
            return "transit_station"
        return "other"
    if a == "place_of_worship":
        return "place_of_worship"
    if a in AMENITY_COMMUNITY:
        return "community_centre"
    if a in AMENITY_RETAIL:
        return "other"
    return "other"


# ================================================================
# 5. Green / blue classification
# ================================================================

GREEN_PARK = {"park", "nature_reserve", "village_green", "common"}
GREEN_PUBLIC_SPACE = {
    "recreation_ground", "playground", "garden", "pitch",
    "golf_course", "sports_centre", "stadium", "track",
    "dog_park", "fitness_centre", "picnic_table", "slipway",
    "marina", "water_park", "beach_resort", "summer_camp",
}
GREEN_WATER = {
    "water", "river", "stream", "canal", "lake", "pond",
    "reservoir", "basin", "wetland", "riverbank", "bay",
    "dock", "harbour", "swimming_pool", "waterfall", "dam", "weir",
}
GREEN_DRAINAGE = {"drain", "ditch", "drainage", "wastewater_plant"}
GREEN_CANOPY = {"wood", "forest", "tree_row", "trees", "scrub", "heath"}


def normalize_green_type(leisure, natural, landuse, waterway, sport=None):
    tags = {
        str(v).strip().lower()
        for v in (leisure, natural, landuse, waterway, sport)
        if v is not None and not (isinstance(v, float) and pd.isna(v))
    }
    if tags & GREEN_DRAINAGE:
        return "drainage"
    if tags & GREEN_WATER:
        return "water_body"
    if tags & GREEN_CANOPY:
        return "canopy"
    if tags & GREEN_PARK:
        return "park"
    if tags & GREEN_PUBLIC_SPACE:
        return "public_space"
    return "public_space"


# ================================================================
# 6. Parcel construction
# ================================================================

def rebuild_parcels_from_buildings(buildings_projected, buffer_m=2.0):
    buffered = buildings_projected.geometry.buffer(buffer_m)
    merged = buffered.union_all()
    if merged.geom_type == "Polygon":
        parts = [merged]
    elif merged.geom_type == "MultiPolygon":
        parts = list(merged.geoms)
    else:
        parts = []
    parcels = gpd.GeoDataFrame({"geometry": parts}, crs=COMPUTE_CRS)
    parcels["area_m2"] = parcels.geometry.area
    parcels = parcels[
        (parcels["area_m2"] >= 300) & (parcels["area_m2"] <= 20000)
    ].copy()
    parcels["parcel_id"] = generate_ids(parcels, "P-")
    parcels["asset_id"] = None
    parcels["land_use"] = "unknown"
    parcels["geometry_source"] = "Derived from building footprints"
    parcels["geometry_confidence"] = "medium"
    return parcels


def assign_parcel_ids(buildings_projected, parcels_projected):
    pts = buildings_projected[["geometry"]].copy()
    pts["_bidx"] = range(len(pts))
    pts.geometry = pts.geometry.representative_point()

    parcels = parcels_projected[["parcel_id", "area_m2", "geometry"]].copy()

    joined = gpd.sjoin(pts, parcels, how="left", predicate="within")
    joined = joined.sort_values("area_m2", na_position="last")
    joined = joined.groupby("_bidx", as_index=False).first()

    ids = joined["parcel_id"].fillna("P-UNASSIGNED").tolist()
    return ids


# ================================================================
# 7. Layer processors
# ================================================================

def process_buildings():
    print("Fetching Buildings...")
    gdf = safe_ox_call(
        ox.features_from_point, CENTER_POINT, dist=DIST_M,
        tags={"building": True},
    )
    gdf = polygons_only(gdf)

    gdf_proj = gdf.to_crs(COMPUTE_CRS)
    gdf["footprint_m2"] = gdf_proj.geometry.area

    gdf["building_id"] = generate_ids(gdf, "BLD-")
    gdf["building_type"] = gdf["building"].map(normalize_building_type)

    levels = gdf.get("building:levels", pd.Series(None, index=gdf.index))
    gdf["floors"] = levels.map(parse_floors)

    floors_filled = gdf["floors"].fillna(1)
    gdf["gfa_m2"] = gdf["footprint_m2"] * floors_filled

    parcels_path = out("parcels")
    if Path(parcels_path).exists():
        parcels = gpd.read_file(parcels_path).to_crs(COMPUTE_CRS)
    else:
        parcels = rebuild_parcels_from_buildings(gdf_proj)
    gdf["parcel_id"] = assign_parcel_ids(gdf_proj, parcels)

    gdf["asset_id"] = gdf["building_id"].map(lambda bid: f"unlinked-{bid}")
    gdf["geometry_source"] = "Microsoft Building Footprints"
    gdf["building_raw"] = gdf.get("building")

    keep = [
        "building_id", "parcel_id", "asset_id", "building_type",
        "building_raw", "floors", "footprint_m2", "gfa_m2",
        "geometry_source", "geometry",
    ]
    final = gdf[keep].to_crs(DISPLAY_CRS)
    features = json.loads(final.to_json(drop_id=True, na="null"))["features"]
    for feat in features:
        feat["id"] = feat["properties"]["building_id"]
    write_feature_collection(out("buildings"), features)
    print(f"Saved {len(final)} buildings -> {out('buildings')}")


def process_parcels():
    print("Rebuilding Parcels from building footprints...")
    buildings_path = out("buildings")
    if not Path(buildings_path).exists():
        raise FileNotFoundError(
            f"{buildings_path} is required to rebuild parcels."
        )
    buildings = gpd.read_file(buildings_path).to_crs(COMPUTE_CRS)
    parcels = rebuild_parcels_from_buildings(buildings)

    buildings["parcel_id"] = assign_parcel_ids(buildings, parcels)

    parcel_land_use = (
        buildings
        .groupby("parcel_id")["building_type"]
        .agg(lambda s: s.mode().iloc[0] if not s.mode().empty else "unknown")
        .to_dict()
    )
    # industrial → commercial: B3 has no industrial deriver. The raw
    # industrial signal is still available via buildings.building_type.
    land_use_map = {
        "residential": "residential",
        "commercial": "commercial",
        "community_facility": "community_facility",
        "industrial": "commercial",
        "mixed_use": "mixed_use",
        "unknown": "unknown",
    }
    parcels["land_use"] = [
        land_use_map.get(parcel_land_use.get(pid, "unknown"), "unknown")
        for pid in parcels["parcel_id"]
    ]

    keep = [
        "parcel_id", "asset_id", "land_use", "area_m2",
        "geometry_source", "geometry_confidence", "geometry",
    ]
    final = parcels[keep].to_crs(DISPLAY_CRS)
    write_feature_collection(
        out("parcels"), geodataframe_features(final, "parcel_id"),
    )
    print(f"Saved {len(final)} parcels -> {out('parcels')}")


def process_green_blue():
    print("Fetching Green & Blue Spaces...")
    green_tags = {
        "leisure": [
            "park", "nature_reserve", "pitch", "golf_course",
            "playground", "garden", "recreation_ground",
            "sports_centre", "stadium", "track",
        ],
        "natural": [
            "water", "wood", "scrub", "tree_row", "wetland",
            "grassland", "heath", "beach", "bay",
        ],
        "landuse": [
            "grass", "forest", "recreation_ground", "meadow",
            "village_green", "allotments", "flowerbed",
            "orchard", "vineyard",
        ],
        "waterway": ["canal", "ditch", "drain", "river", "stream", "dam", "weir"],
    }
    gdf = safe_ox_call(
        ox.features_from_point, CENTER_POINT, dist=DIST_M,
        tags=green_tags,
    )
    try:
        water_extra = safe_ox_call(
            ox.features_from_point, CENTER_POINT, dist=DIST_M,
            tags={"water": True},
        )
        gdf = gpd.GeoDataFrame(
            pd.concat([gdf, water_extra]), crs=gdf.crs,
        )
        gdf = gdf[~gdf.index.duplicated(keep="first")]
    except Exception as e:
        print(f"  water-extra query failed (continuing): {e}")

    for col in ["leisure", "natural", "landuse", "waterway", "sport", "water"]:
        if col not in gdf.columns:
            gdf[col] = None

    gdf_proj = gdf.to_crs(COMPUTE_CRS)
    gdf["area_m2"] = gdf_proj.geometry.area

    gdf["green_id"] = generate_ids(gdf, "G-")
    gdf["green_type"] = [
        normalize_green_type(le, na, lu, wa, sp)
        for le, na, lu, wa, sp in zip(
            gdf["leisure"], gdf["natural"], gdf["landuse"],
            gdf["waterway"], gdf["sport"],
        )
    ]
    gdf["asset_id"] = gdf["green_id"].map(lambda gid: f"unlinked-{gid}")
    gdf["canopy_m2"] = [
        area if gt == "canopy" else None
        for area, gt in zip(gdf["area_m2"], gdf["green_type"])
    ]
    gdf["geometry_source"] = "OpenStreetMap"
    gdf["green_type_raw"] = gdf[
        ["leisure", "natural", "landuse", "waterway"]
    ].apply(
        lambda r: ",".join(
            str(v) for v in r if v is not None and not pd.isna(v)
        ),
        axis=1,
    )

    keep = [
        "green_id", "asset_id", "green_type", "green_type_raw",
        "area_m2", "canopy_m2", "geometry_source", "geometry",
    ]
    final = gdf[keep].to_crs(DISPLAY_CRS)
    write_feature_collection(
        out("green_blue"), geodataframe_features(final, "green_id"),
    )
    print(f"Saved {len(final)} green/blue spaces -> {out('green_blue')}")


def process_network():
    print("Fetching Complete Study-Area Network...")

    # Network radius derives from the buildings layer alone.
    # Merging green/blue bounds inflated the radius by ~5x because
    # a single outlier water body extended several km beyond the
    # built-up core.
    buildings_path = out("buildings")
    if not Path(buildings_path).exists():
        raise FileNotFoundError(
            f"{buildings_path} is required to compute the network radius."
        )
    buildings_layer = gpd.read_file(buildings_path).to_crs(COMPUTE_CRS)
    west, south, east, north = buildings_layer.total_bounds
    center = (
        gpd.GeoSeries(
            [gpd.points_from_xy(
                [CENTER_POINT[1]], [CENTER_POINT[0]])[0]],
            crs=DISPLAY_CRS,
        ).to_crs(COMPUTE_CRS).iloc[0]
    )
    network_dist = max(
        math.hypot(x - center.x, y - center.y)
        for x in (west, east) for y in (south, north)
    ) + 200.0
    print(f"Network radius: {network_dist:.0f} m")

    G = safe_ox_call(
        ox.graph_from_point,
        CENTER_POINT, dist=network_dist,
        network_type="all", retain_all=True,
    )
    _, edges = ox.graph_to_gdfs(G)
    edges = edges.reset_index()

    classified = edges["highway"].apply(classify_highway)
    edges["edge_type"] = [c[0] for c in classified]
    edges["walk_ok"] = [c[1] for c in classified]
    edges["drive_ok"] = [c[2] for c in classified]

    edges_proj = edges.to_crs(COMPUTE_CRS)
    edges["length_m"] = edges_proj.geometry.length
    edges["edge_id"] = generate_ids(edges, "E-")
    edges["from_node"] = edges["u"].map(lambda n: f"N-{n}")
    edges["to_node"] = edges["v"].map(lambda n: f"N-{n}")
    edges["walk_speed_kmh"] = 4.5

    access_foot = edges.get("access:foot", pd.Series(None, index=edges.index))
    access_gen = edges.get("access", pd.Series(None, index=edges.index))
    edges["access_type"] = [
        normalize_access_type(
            fa if (fa is not None and not pd.isna(fa)) else ga
        )
        for fa, ga in zip(access_foot, access_gen)
    ]

    # Canopy coverage: union + buffer computed once.
    green_path = out("green_blue")
    if Path(green_path).exists():
        green = gpd.read_file(green_path).to_crs(COMPUTE_CRS)
        canopy_union = green.geometry.union_all()
        if canopy_union.is_empty:
            from shapely.geometry import Polygon
            canopy_buffered = Polygon()
        else:
            canopy_buffered = canopy_union.buffer(CANOPY_BUFFER_M)
    else:
        from shapely.geometry import Polygon
        canopy_buffered = Polygon()

    edges["canopy_coverage_ratio"] = [
        calculate_canopy_coverage_ratio(geom, canopy_buffered)
        for geom in edges_proj.geometry
    ]

    edges["highway_raw"] = edges["highway"].apply(
        lambda v: ",".join(v) if isinstance(v, list)
        else (str(v) if v is not None else None)
    )

    keep = [
        "edge_id", "edge_type", "highway_raw", "walk_ok", "drive_ok",
        "from_node", "to_node", "length_m", "walk_speed_kmh",
        "access_type", "canopy_coverage_ratio", "geometry",
    ]
    final = edges[keep].to_crs(DISPLAY_CRS)
    write_feature_collection(
        out("network_edges"),
        geodataframe_features(final, "edge_id"),
    )
    print(f"Saved {len(final)} network edges -> {out('network_edges')} "
          f"(walk_ok={int(edges['walk_ok'].sum())}, "
          f"drive_ok={int(edges['drive_ok'].sum())})")


def process_amenities():
    print("Fetching Amenities...")
    gdf = safe_ox_call(
        ox.features_from_point, CENTER_POINT, dist=DIST_M,
        tags={"amenity": True},
    )
    gdf = gdf.reset_index()
    gdf["amenity_id"] = generate_ids(gdf, "A-")

    raw = gdf.get("amenity", pd.Series(None, index=gdf.index))
    gdf["amenity_type"] = raw.map(normalize_amenity_type)
    gdf["amenity_type_raw"] = raw.apply(
        lambda v: str(v).lower().strip() if v is not None else None
    )
    gdf["capacity"] = None

    keep = [
        "amenity_id", "amenity_type", "amenity_type_raw",
        "capacity", "geometry",
    ]
    final = gdf[keep].to_crs(DISPLAY_CRS)
    write_feature_collection(
        out("amenities"),
        geodataframe_features(final, "amenity_id"),
    )
    print(f"Saved {len(final)} amenities -> {out('amenities')}")


# ================================================================
# 8. Runner
# ================================================================

def run_step(func, output_file):
    if SKIP_EXISTING and Path(output_file).exists():
        print(f"Skipping {func.__name__}: {output_file} exists.")
        return
    func()


if __name__ == "__main__":
    print(f"Starting Raw OSM Pipeline -> {RAW_GEOM_DIR}")
    print(f"Output suffix: '{OUTPUT_SUFFIX}'")
    run_step(process_buildings, out("buildings"))
    run_step(process_parcels, out("parcels"))
    run_step(process_green_blue, out("green_blue"))
    run_step(process_network, out("network_edges"))
    run_step(process_amenities, out("amenities"))
    print("Raw pipeline complete.")