"""Bukit Jelutong preprocessing: raw OSM -> processed geometry + business.

Reads the raw OSM extraction (bukit_jelutong/raw/geometry/*_bj.geojson)
and produces:

  processed/geometry/*.geojson
      Geometry layers with derived attributes.
  processed/business/*.csv
      assets, asset_metrics, development_projects,
      development_candidates, interventions.

Asset sources:
    buildings     -> residential, commercial (from OSM building tags)
    amenities     -> community_facility (school, clinic, worship, ...)
                     + commercial (food_beverage, finance, retail)
    green_blue    -> green_space (park, public_space)
    parcels       -> undeveloped_parcel (synthesised)

Schema alignment pass (2026-10-15b):
  - bungalow / dormitory -> taxonomy-legal subtypes.
  - Undeveloped parcels synthesised.
  - P-UNASSIGNED orphans given real parcel geometries.
  - parcels.asset_id populated so B3 resolves asset geometry.

Schema alignment pass (2026-10-15c):
  - green_blue.asset_id rewritten from "unlinked-G-xxxx" to "G-xxxx"
    so derived/green.py can resolve canopy area per asset.
  - green_blue.canopy_m2 backfilled from area_m2 for vegetation
    polygons, so B3's canopy coverage is continuous instead of 0/1.
  - Amenity-derived assets receive their own synthetic parcel, so
    B3's walking pipeline and Huff supply model can resolve them.
    Without this, every f_and_b / services / clinic asset was
    silently skipped and DSR was NaN.

Usage:
    python bukit_jelutong/build_mock_data.py
    python bukit_jelutong/build_mock_data.py --sample
"""

import argparse
import hashlib
import math
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import yaml

# ----------------------------------------------------------------
# Paths
# ----------------------------------------------------------------
BUKIT_DIR = Path(__file__).resolve().parent
RAW_GEOM_DIR = BUKIT_DIR / "raw" / "geometry"
PROCESSED_DIR = BUKIT_DIR / "processed"
PROCESSED_GEOM_DIR = PROCESSED_DIR / "geometry"
PROCESSED_BIZ_DIR = PROCESSED_DIR / "business"

for d in (PROCESSED_GEOM_DIR, PROCESSED_BIZ_DIR):
    d.mkdir(parents=True, exist_ok=True)

SUFFIX = "_bj"
COMPUTE_CRS = "EPSG:32647"
DISPLAY_CRS = "EPSG:4326"

BASE_YEAR = 2026
MIN_BUILDING_FOOTPRINT_M2 = 40.0


# ----------------------------------------------------------------
# Taxonomy access (for target_area_m2 caps)
# ----------------------------------------------------------------
_TAXONOMY_PATH = BUKIT_DIR.parent / "backend" / "configs" / "taxonomy.yml"

try:
    with open(_TAXONOMY_PATH, encoding="utf-8") as _f:
        _TAXONOMY = yaml.safe_load(_f) or {}
except FileNotFoundError:
    _TAXONOMY = {}

_SUBTYPE_DEFS = _TAXONOMY.get("subtypes", {})


def _subtype_max_area(subtype: str):
    """
    Return the upper bound of target_area_m2 for a subtype, or None.

    Used to cap amenity floor area so an amenity hosted inside a
    much larger building does not inherit the building's entire
    footprint.
    """
    defn = _SUBTYPE_DEFS.get(subtype) or {}
    rng = defn.get("target_area_m2")
    if isinstance(rng, list) and len(rng) == 2:
        try:
            return float(rng[1])
        except (TypeError, ValueError):
            return None
    return None


# ================================================================
# 1. Seeded randomness
# ================================================================

def seeded_uniform(key: str, lo: float, hi: float) -> float:
    h = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16)
    u = (h % 10_000_000) / 10_000_000.0
    return lo + (hi - lo) * u


def seeded_int(key: str, lo: int, hi: int) -> int:
    u = seeded_uniform(key, 0.0, 1.0)
    return lo + int(math.floor(u * (hi - lo + 1)))


# ================================================================
# 2. Building subtype inference
# ================================================================

FLOOR_RANGE_BY_SUBTYPE = {
    # Residential
    "detached":           (1, 3),
    "semidetached":       (2, 3),
    "terrace":            (2, 2),
    "apartment_lowrise":  (3, 5),
    "apartment_highrise": (6, 12),
    "affordable_housing": (4, 8),
    # Commercial
    "convenience_retail": (1, 2),
    "f_and_b":            (1, 2),
    "supermarket":        (1, 2),
    "medical_retail":     (1, 2),
    "services":           (1, 2),
    "office":             (2, 5),
    "showroom":           (1, 2),
    # Community facility
    "school":             (1, 4),
    "clinic":             (1, 2),
    "community_hall":     (1, 2),
    "childcare":          (1, 2),
    "library":            (1, 3),
    "place_of_worship":   (1, 2),
    "public_service":     (1, 2),
    "sports_centre":      (1, 2),
}

ATTACHMENT_RAW_VALUES = {
    "roof", "shed", "hut", "carport", "garage", "garages",
    "greenhouse", "conservatory", "ruin", "ruins",
    "construction", "bunker", "tower", "bridge",
    "digester", "gasometer", "water_tower", "silo",
    "storage_tank", "service", "parking",
}


def infer_subtype(raw, footprint_m2, building_type):
    """Return the taxonomy subtype, or None for attachments / tiny."
    """
    bt = str(raw).strip().lower() if raw else ""
    fp = float(footprint_m2 or 0)

    if bt in ATTACHMENT_RAW_VALUES:
        return None
    if fp < MIN_BUILDING_FOOTPRINT_M2:
        return None

    if bt == "bungalow":
        return "detached"
    if bt in {"detached", "detached_house"}:
        return "detached"
    if bt in {"semidetached_house", "semi-detached", "semi_detached"}:
        return "semidetached"
    if bt in {"terrace", "terraced_house", "row_house"}:
        return "terrace"
    if bt in {"apartments", "apartment"}:
        return "apartment_highrise" if fp > 2000 else "apartment_lowrise"
    if bt == "dormitory":
        return "apartment_lowrise"
    if bt == "house":
        if fp < 150:
            return "terrace"
        if fp < 400:
            return "semidetached"
        return "detached"

    if bt == "supermarket":
        return "supermarket"
    if bt in {"convenience", "kiosk"}:
        return "convenience_retail"
    if bt in {"restaurant", "cafe", "fast_food", "food_court"}:
        return "f_and_b"
    if bt == "office":
        return "office"
    if bt == "showroom":
        return "showroom"

    if bt in {"school", "university", "college"}:
        return "school"
    if bt == "kindergarten":
        return "childcare"
    if bt in {"clinic", "hospital"}:
        return "clinic"
    if bt in {"community_centre", "social_facility"}:
        return "community_hall"
    if bt == "library":
        return "library"
    if bt in {"church", "cathedral", "mosque", "synagogue",
              "temple", "chapel", "place_of_worship"}:
        return "place_of_worship"
    if bt in {"sports_hall", "stadium", "sports_centre"}:
        return "sports_centre"
    if bt in {"government", "public", "civic", "townhall", "police"}:
        return "public_service"

    if building_type == "residential":
        if fp < 150:
            return "terrace"
        if fp < 400:
            return "semidetached"
        if fp > 2000:
            return "apartment_highrise"
        return "detached"

    if building_type == "commercial":
        if fp < 300:
            return "convenience_retail"
        if fp < 1000:
            return "f_and_b"
        return "supermarket"

    if building_type == "community_facility":
        if fp > 5000:
            return "school"
        return "community_hall"

    if building_type == "industrial":
        return "office"

    if building_type in {"unknown", "yes", ""}:
        if fp > 5000:
            return "school"
        if fp > 2500:
            return "apartment_lowrise"
        if fp > 1200:
            return "terrace"
        if fp > 400:
            return "detached"
        if fp > 100:
            return "terrace"
        return None

    return None


# ================================================================
# 3. Amenity remapping and asset conversion
# ================================================================

def normalize_amenity_type(raw: str) -> str:
    a = str(raw).strip().lower() if raw else ""
    if not a:
        return "other"
    if a == "hospital":
        return "hospital"
    if a in {"clinic", "doctors", "dentist", "pharmacy",
             "veterinary", "nursing_home", "social_facility"}:
        return "clinic"
    if a == "library":
        return "library"
    if a in {"school", "kindergarten", "college", "university",
             "language_school", "music_school", "driving_school",
             "childcare", "research_institute"}:
        return "school"
    if a == "place_of_worship":
        return "place_of_worship"
    if a in {"bus_station", "bus_stop"}:
        return "bus_stop"
    if a in {"ferry_terminal", "taxi"}:
        return "transit_station"
    if a == "fuel":
        return "fuel"
    if a in {"parking", "parking_entrance", "parking_space",
             "bicycle_parking", "motorcycle_parking",
             "charging_station"}:
        return "parking"
    if a in {"community_centre", "social_centre", "arts_centre",
             "theatre", "cinema", "events_venue", "exhibition_centre",
             "conference_centre", "public_building", "townhall",
             "courthouse", "police", "post_office", "fire_station",
             "embassy", "prison", "ranger_station"}:
        return "community_centre"
    if a in {"restaurant", "fast_food", "cafe", "bar", "pub",
             "biergarten", "food_court", "ice_cream"}:
        return "food_beverage"
    if a in {"bank", "atm", "bureau_de_change"}:
        return "finance"
    if a in {"marketplace", "shop", "vending_machine"}:
        return "retail"
    return "other"


AMENITY_TO_ASSET = {
    "school":             ("community_facility", "school",           3000.0),
    "clinic":             ("community_facility", "clinic",            400.0),
    "hospital":           ("community_facility", "clinic",           8000.0),
    "library":            ("community_facility", "library",          1200.0),
    "place_of_worship":   ("community_facility", "place_of_worship",  800.0),
    "community_centre":   ("community_facility", "community_hall",    600.0),
    "food_beverage":      ("commercial",         "f_and_b",           250.0),
    "finance":            ("commercial",         "services",          300.0),
    "retail":             ("commercial",         "convenience_retail",200.0),
}


def amenity_to_asset_row(row, index: int) -> dict:
    """Convert one amenity GeoJSON row into an asset row."""
    atype_map = AMENITY_TO_ASSET.get(row["amenity_type"])
    if atype_map is None:
        return None

    asset_type, subtype, default_fp = atype_map

    matched_fp = row.get("_matched_footprint_m2")
    if pd.notna(matched_fp) and float(matched_fp) >= MIN_BUILDING_FOOTPRINT_M2:
        fp = float(matched_fp)
    else:
        geom = row.get("geometry")
        if geom is not None and geom.geom_type in ("Polygon", "MultiPolygon"):
            fp = float(row.get("_area_m2") or 0.0)
            if fp < MIN_BUILDING_FOOTPRINT_M2:
                fp = default_fp
        else:
            fp = default_fp

    # FIX (2026-10-15c): cap by taxonomy target_area_m2 upper bound.
    # Without this, an amenity hosted inside a large commercial block
    # inherits the whole block's footprint and its carbon balloons.
    max_fp = _subtype_max_area(subtype)
    if max_fp is not None and fp > max_fp:
        fp = max_fp

    lo, hi = FLOOR_RANGE_BY_SUBTYPE.get(subtype, (1, 2))
    floors = seeded_int(f"{row['amenity_id']}-floors", lo, hi)
    floor_area = fp * floors

    lettable = floor_area * LETTABLE_FRACTION.get(asset_type, 0.85)
    capex = floor_area * CAPEX_PER_M2.get(asset_type, 2000.0)
    opex = capex * OPEX_FRACTION.get(asset_type, 0.05)
    maintenance = capex * MAINTENANCE_FRACTION.get(asset_type, 0.02)
    capacity = int(round(floor_area * CAPACITY_PER_M2.get(subtype, 1 / 60)))

    completion_year = BASE_YEAR - seeded_int(
        f"{row['amenity_id']}-age", 2, 25,
    )

    b_id = row.get("building_id")
    p_id = row.get("parcel_id")

    return {
        "asset_id": row["amenity_id"],
        "asset_type": asset_type,
        "subtype": subtype,
        "parcel_id": p_id if pd.notna(p_id) else None,
        "building_id": b_id if pd.notna(b_id) else None,
        "asset_name": f"{subtype.replace('_', ' ').title()} {row['amenity_id']}",
        "land_use": asset_type,
        "development_phase": 1,
        "status": "existing",
        "completion_year": completion_year,
        "target_demographic": TARGET_DEMOGRAPHIC_BY_SUBTYPE.get(subtype, "all"),
        "floor_area_m2": round(floor_area, 2),
        "lettable_area_m2": round(lettable, 2),
        "land_area_m2": round(fp, 2),
        "capex_initial_rm": round(capex, 2),
        "opex_annual_rm": round(opex, 2),
        "maintenance_annual_rm": round(maintenance, 2),
        "capacity": capacity,
        "data_completeness": 0.85 if pd.notna(b_id) else 0.70,
        "data_sources": (
            "osm_amenity;building_linked;derived"
            if pd.notna(b_id) else "osm_amenity;derived"
        ),
        # Phase 14 — execution authority. Amenity-derived assets are
        # split by asset_type: commercial amenity (food_beverage,
        # finance, retail) stays full_control; community_facility
        # amenities (school, clinic, etc.) are advisory.
        "authority": _AUTHORITY_BY_ASSET_TYPE.get(asset_type, "advisory"),
    }


# ================================================================
# 4. Capacity and cost tables
# ================================================================

CAPACITY_PER_M2 = {
    "terrace":            1 / 50,
    "semidetached":       1 / 55,
    "detached":           1 / 60,
    "apartment_lowrise":  1 / 45,
    "apartment_highrise": 1 / 40,
    "affordable_housing": 1 / 35,
    "convenience_retail": 1 / 60,
    "f_and_b":            1 / 20,
    "supermarket":        1 / 15,
    "office":             1 / 15,
    "services":           1 / 60,
    "showroom":           1 / 40,
    "school":             1 / 8,
    "clinic":             1 / 30,
    "community_hall":     1 / 6,
    "childcare":          1 / 12,
    "library":            1 / 25,
    "place_of_worship":   1 / 4,
    "public_service":     1 / 40,
    "sports_centre":      1 / 15,
}

LETTABLE_FRACTION = {
    "residential":         1.0,
    "commercial":          0.85,
    "community_facility":  1.0,
    "green_space":         0.0,
    "undeveloped_parcel":  0.0,
}

CAPEX_PER_M2 = {
    "residential":         2500.0,
    "commercial":          3500.0,
    "community_facility":  3000.0,
    "green_space":         400.0,
    "undeveloped_parcel":  0.0,
}

OPEX_FRACTION = {
    "residential":         0.04,
    "commercial":          0.08,
    "community_facility":  0.10,
    "green_space":         0.02,
    "undeveloped_parcel":  0.0,
}

MAINTENANCE_FRACTION = {
    "residential":         0.015,
    "commercial":          0.025,
    "community_facility":  0.030,
    "green_space":         0.010,
    "undeveloped_parcel":  0.0,
}

TARGET_DEMOGRAPHIC_BY_SUBTYPE = {
    "terrace":            "young_families",
    "semidetached":       "families",
    "detached":           "families",
    "apartment_lowrise":  "young_families",
    "apartment_highrise": "young_adults",
    "convenience_retail": "all",
    "f_and_b":            "workers",
    "supermarket":        "all",
    "office":             "workers",
    "services":           "all",
    "showroom":           "all",
    "school":             "young_families",
    "clinic":             "all",
    "community_hall":     "all",
    "childcare":          "young_families",
    "library":            "all",
    "place_of_worship":   "all",
    "public_service":     "all",
    "sports_centre":      "young_adults",
}

# Phase 14 — execution authority per asset type.
_AUTHORITY_BY_ASSET_TYPE = {
    "commercial":          "full_control",
    "residential":         "shared",
    "community_facility":  "advisory",
    "green_space":         "advisory",
    "undeveloped_parcel":  "full_control",
}


# ================================================================
# 5. Geometry processors
# ================================================================

SUBTYPE_TO_BUILDING_TYPE = {
    "detached": "residential",
    "semidetached": "residential",
    "terrace": "residential",
    "apartment_lowrise": "residential",
    "apartment_highrise": "residential",
    "affordable_housing": "residential",
    "convenience_retail": "commercial",
    "f_and_b": "commercial",
    "supermarket": "commercial",
    "medical_retail": "commercial",
    "services": "commercial",
    "office": "commercial",
    "showroom": "commercial",
}


def process_buildings_geometry(buildings: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf = buildings.copy()

    subtypes, floors_list, gfa_list, is_asset = [], [], [], []
    updated_btypes = []

    for _, row in gdf.iterrows():
        orig_btype = row.get("building_type") or "unknown"
        subtype = infer_subtype(
            raw=row.get("building_raw"),
            footprint_m2=float(row.get("footprint_m2") or 0),
            building_type=orig_btype,
        )
        subtypes.append(subtype)

        if subtype is None:
            floors_list.append(None)
            gfa_list.append(None)
            is_asset.append(False)
            updated_btypes.append(orig_btype)
            continue

        derived_btype = SUBTYPE_TO_BUILDING_TYPE.get(subtype, orig_btype)
        updated_btypes.append(derived_btype)

        lo, hi = FLOOR_RANGE_BY_SUBTYPE.get(subtype, (1, 2))
        fl = seeded_int(f"{row['building_id']}-floors", lo, hi)
        floors_list.append(int(fl))
        fp = float(row.get("footprint_m2") or 0)
        gfa_list.append(fp * fl)
        is_asset.append(True)

    gdf["subtype"] = subtypes
    gdf["building_type"] = updated_btypes
    gdf["is_asset"] = is_asset
    gdf["floors"] = floors_list
    gdf["gfa_m2"] = gfa_list

    return gdf


def resolve_unassigned_parcels(
    buildings: gpd.GeoDataFrame,
    parcels: gpd.GeoDataFrame,
) -> tuple:
    """Give every building a resolvable parcel_id."""
    mask = (
        buildings["parcel_id"].isna()
        | (buildings["parcel_id"].astype(str) == "P-UNASSIGNED")
    )
    if not mask.any():
        return buildings, parcels

    orphan = buildings[mask].copy()
    new_parcels = []

    for i, (idx, row) in enumerate(orphan.iterrows()):
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        parcel_geom = geom.buffer(2.0)
        pid = f"P-FIX-{i + 1:04d}"
        new_parcels.append({
            "parcel_id": pid,
            "asset_id": None,
            "land_use": "unknown",
            "area_m2": float(parcel_geom.area),
            "geometry_source": "Derived",
            "geometry_confidence": "low",
            "geometry": parcel_geom,
        })
        buildings.loc[idx, "parcel_id"] = pid

    if not new_parcels:
        return buildings, parcels

    new_gdf = gpd.GeoDataFrame(new_parcels, crs=buildings.crs)
    parcels_extended = gpd.GeoDataFrame(
        pd.concat([parcels, new_gdf], ignore_index=True),
        crs=parcels.crs,
    )
    return buildings, parcels_extended


def mock_undeveloped_parcels(
    parcels: gpd.GeoDataFrame,
    n: int = 3,
) -> gpd.GeoDataFrame:
    """Synthesise a handful of vacant parcels."""
    if parcels.empty or n <= 0:
        return parcels.iloc[0:0].copy()

    ranked = parcels.sort_values("area_m2", ascending=False).head(n * 4)
    step = max(1, len(ranked) // n)
    picked = ranked.iloc[::step].head(n).copy()

    picked["parcel_id"] = [f"P-VAC-{i + 1:02d}" for i in range(len(picked))]
    picked["asset_id"] = picked["parcel_id"]
    picked["land_use"] = "undeveloped"
    picked["geometry_source"] = "Derived"
    picked["geometry_confidence"] = "low"

    return picked


def process_amenities_geometry(
    amenities: gpd.GeoDataFrame,
    buildings: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Normalise amenity_type and link to intersecting buildings."""
    gdf = amenities.copy()
    if "amenity_type_raw" not in gdf.columns:
        gdf["amenity_type_raw"] = gdf.get("amenity_type")
    gdf["amenity_type"] = gdf["amenity_type_raw"].apply(normalize_amenity_type)

    proj = gdf.to_crs(COMPUTE_CRS)
    gdf["_area_m2"] = proj.geometry.area

    b_proj = buildings.to_crs(COMPUTE_CRS)[
        ["building_id", "parcel_id", "footprint_m2", "geometry"]
    ]
    joined = gpd.sjoin(proj, b_proj, how="left", predicate="intersects")
    joined = joined[~joined.index.duplicated(keep="first")]

    gdf["building_id"] = joined["building_id"].values
    gdf["parcel_id"] = joined["parcel_id"].values
    gdf["_matched_footprint_m2"] = joined["footprint_m2"].values

    return gdf


def generate_population(buildings: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Generate population nodes from residential buildings."""
    residential = buildings[
        buildings["subtype"].isin({
            "terrace", "semidetached", "detached",
            "apartment_lowrise", "apartment_highrise",
            "affordable_housing",
        })
    ].copy()

    if residential.empty:
        return _empty_population_gdf()

    residential = residential.to_crs(COMPUTE_CRS)
    centroids = residential.geometry.representative_point()

    grid = 400.0
    residential = residential.assign(
        _cell=list(zip((centroids.x // grid).astype(int),
                       (centroids.y // grid).astype(int))),
    )

    rows = []
    for i, (cell, group) in enumerate(residential.groupby("_cell"), 1):
        total = 0.0
        for _, b in group.iterrows():
            gfa = float(b.get("gfa_m2") or 0)
            total += gfa * CAPACITY_PER_M2.get(b["subtype"], 1 / 60)
        total = int(round(total))
        if total < 50:
            continue

        has_apartment = group["subtype"].isin(
            {"apartment_highrise", "apartment_lowrise"}
        ).any()
        if has_apartment:
            r014, r1564 = 0.18, 0.68
        else:
            r014, r1564 = 0.22, 0.62

        p014 = int(round(total * r014))
        p1564 = int(round(total * r1564))
        p65 = total - p014 - p1564
        centroid = group.geometry.union_all().centroid
        pop_id = f"POP-{i:04d}"
        rows.append({
            "population_id": pop_id,
            "total_population": total,
            "age_0_14": p014, "age_15_64": p1564, "age_65_plus": p65,
            "household_size": round(seeded_uniform(f"{pop_id}-hh", 3.2, 4.5), 2),
            "source": "mock_from_residential_buildings",
            "geometry": centroid,
        })

    if not rows:
        return _empty_population_gdf()

    return gpd.GeoDataFrame(
        rows, geometry="geometry", crs=COMPUTE_CRS,
    ).to_crs(DISPLAY_CRS)


def _empty_population_gdf() -> gpd.GeoDataFrame:
    from shapely.geometry import Point  # noqa: F401
    gdf = gpd.GeoDataFrame(
        {
            "population_id": pd.Series(dtype="object"),
            "total_population": pd.Series(dtype="int64"),
            "age_0_14": pd.Series(dtype="int64"),
            "age_15_64": pd.Series(dtype="int64"),
            "age_65_plus": pd.Series(dtype="int64"),
            "household_size": pd.Series(dtype="float64"),
            "source": pd.Series(dtype="object"),
        },
        geometry=pd.Series(dtype="object"),
        crs=DISPLAY_CRS,
    )
    return gdf


# ================================================================
# 6. Asset selection
# ================================================================

SAMPLE_QUOTA = {
    "residential":         8,
    "commercial":          10,
    "community_facility":  10,
    "green_space":         3,
    "undeveloped_parcel":  2,
}


def select_building_assets(buildings: gpd.GeoDataFrame,
                           full: bool = True) -> dict:
    out = {"residential": [], "commercial": []}
    eligible = buildings[buildings["subtype"].notna()].copy()
    for atype in out.keys():
        sub = eligible[eligible["building_type"] == atype].copy()
        sub = sub.sort_values("footprint_m2", ascending=False)
        if not full:
            sub = sub.head(SAMPLE_QUOTA[atype])
        out[atype] = sub.to_dict("records")
    return out


def select_amenity_assets(amenities: gpd.GeoDataFrame,
                          full: bool = True) -> dict:
    out = {"community_facility": [], "commercial": []}
    for _, row in amenities.iterrows():
        atype_map = AMENITY_TO_ASSET.get(row["amenity_type"])
        if atype_map is None:
            continue
        asset_type, _, _ = atype_map
        out[asset_type].append(row.to_dict())
    if not full:
        for k in out:
            out[k] = out[k][:SAMPLE_QUOTA[k]]
    return out


def select_green_and_parcel_assets(buildings, green_blue, parcels,
                                   full: bool = True) -> dict:
    out = {"green_space": [], "undeveloped_parcel": []}

    gb = green_blue[
        green_blue["green_type"].isin(["park", "public_space"])
    ].copy().sort_values("area_m2", ascending=False)
    if not full:
        gb = gb.head(SAMPLE_QUOTA["green_space"])
    out["green_space"] = gb.to_dict("records")

    occupied = set(buildings["parcel_id"].dropna().unique())
    vacant = parcels[~parcels["parcel_id"].isin(occupied)].copy()
    vacant = vacant.sort_values("area_m2", ascending=False)
    if not full:
        vacant = vacant.head(SAMPLE_QUOTA["undeveloped_parcel"])
    out["undeveloped_parcel"] = vacant.to_dict("records")
    return out


# ================================================================
# 7. Row builders
# ================================================================

def derive_asset_row(record: dict, atype: str, index: int) -> dict:
    subtype = record.get("subtype") or _default_subtype(atype)

    if atype in ("green_space", "undeveloped_parcel"):
        land_area = float(record.get("area_m2") or 0.0)
        floor_area = 0.0
    else:
        floor_area = float(record.get("gfa_m2") or 0.0)
        land_area = floor_area * 0.5

    lettable = floor_area * LETTABLE_FRACTION.get(atype, 0.85)
    capex = floor_area * CAPEX_PER_M2.get(atype, 2000.0)
    opex = capex * OPEX_FRACTION.get(atype, 0.05)
    maintenance = capex * MAINTENANCE_FRACTION.get(atype, 0.02)
    capacity = int(round(floor_area * CAPACITY_PER_M2.get(subtype, 1 / 60)))

    seed_base = (
        record.get("building_id")
        or record.get("green_id")
        or record.get("parcel_id")
        or f"{atype}-{index}"
    )
    completion_year = BASE_YEAR - seeded_int(f"{seed_base}-age", 2, 25)

    return {
        "asset_id": _asset_id_for(record, atype, index),
        "asset_type": atype,
        "subtype": subtype,
        "parcel_id": record.get("parcel_id"),
        "building_id": record.get("building_id"),
        "asset_name": f"{atype.replace('_', ' ').title()} {index + 1}",
        "land_use": atype,
        "development_phase": 1,
        "status": "existing",
        "completion_year": completion_year,
        "target_demographic": TARGET_DEMOGRAPHIC_BY_SUBTYPE.get(subtype, "all"),
        "floor_area_m2": round(floor_area, 2),
        "lettable_area_m2": round(lettable, 2),
        "land_area_m2": round(land_area, 2),
        "capex_initial_rm": round(capex, 2),
        "opex_annual_rm": round(opex, 2),
        "maintenance_annual_rm": round(maintenance, 2),
        "capacity": capacity,
        "data_completeness": 0.75,
        "data_sources": "osm;derived",
        # Phase 14 — execution authority. Community facilities and
        # green spaces are assumed to have been transferred to the
        # local authority; the developer retains advisory rights only.
        "authority": _AUTHORITY_BY_ASSET_TYPE.get(atype, "advisory"),
    }


def _asset_id_for(record: dict, atype: str, index: int) -> str:
    if atype == "green_space":
        return record.get("green_id") or f"G-{index:02d}"
    if atype == "undeveloped_parcel":
        return record.get("parcel_id") or f"P-{index:02d}"
    return record.get("building_id") or f"A-{index:02d}"


def _default_subtype(atype: str) -> str:
    return {
        "residential":         "terrace",
        "commercial":          "convenience_retail",
        "community_facility":  "community_hall",
        "green_space":         "park",
        "undeveloped_parcel":  "vacant",
    }.get(atype, "vacant")


def derive_metrics_row(asset: dict, demo_role: str) -> dict:
    aid = asset["asset_id"]
    atype = asset["asset_type"]

    row = {
        "asset_id": aid, "year": BASE_YEAR,
        "occupancy_rate": None, "vacancy_rate": None,
        "vacancy_duration_months": None, "footfall_daily": None,
        "utilisation_rate": None, "rental_income_rm": None,
        "energy_kwh": None, "metric_source": "observed",
        "model_version": "0.4.0",
    }

    if atype == "commercial":
        if demo_role == "deadspace":
            occ = seeded_uniform(f"{aid}-occ", 0.18, 0.28)
            vac_dur = seeded_int(f"{aid}-vacdur", 12, 24)
            footfall = seeded_int(f"{aid}-footfall", 100, 300)
            rental = seeded_int(f"{aid}-rental", 800_000, 1_200_000)
        else:
            occ = seeded_uniform(f"{aid}-occ", 0.72, 0.92)
            vac_dur = seeded_int(f"{aid}-vacdur", 0, 6)
            footfall = seeded_int(f"{aid}-footfall", 300, 900)
            rental = seeded_int(f"{aid}-rental", 1_500_000, 3_000_000)
        row["occupancy_rate"] = round(occ, 3)
        row["vacancy_rate"] = round(1 - occ, 3)
        row["vacancy_duration_months"] = vac_dur
        row["footfall_daily"] = footfall
        row["rental_income_rm"] = rental

    elif atype == "community_facility":
        if demo_role == "underperforming":
            util = seeded_uniform(f"{aid}-util", 0.15, 0.30)
        else:
            util = seeded_uniform(f"{aid}-util", 0.55, 0.85)
        row["utilisation_rate"] = round(util, 3)

    elif atype == "residential":
        row["occupancy_rate"] = round(
            seeded_uniform(f"{aid}-occ", 0.82, 0.98), 3,
        )

    return row


# ================================================================
# 8. Write helpers
# ================================================================

def write_layer(gdf: gpd.GeoDataFrame, name: str, id_col: str = None):
    """
    Write a GeoDataFrame to processed/geometry as GeoJSON.

    The id column (edge_id / parcel_id / building_id / ...) is kept as
    a normal property column. We do NOT call set_index, because
    GeoPandas would then write it as a feature-level `id` that
    read_file() does not restore as a column. Downstream B3 code reads
    these ids as ordinary columns.
    """
    path = PROCESSED_GEOM_DIR / f"{name}{SUFFIX}.geojson"
    out = gdf.to_crs(DISPLAY_CRS).copy()

    drop = [c for c in out.columns if c.startswith("_")]
    if drop:
        out = out.drop(columns=drop)

    out = out.reset_index(drop=True)
    out.to_file(path, driver="GeoJSON")
    print(f"  wrote {path.name}  ({len(out)} features)")


# ================================================================
# 9. Main
# ================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", action="store_true")
    args = parser.parse_args()
    full = not args.sample

    print("=" * 72)
    print(f"  Bukit Jelutong preprocessing "
          f"({'full' if full else 'sample'} mode)")
    print("=" * 72)

    print("\nReading raw geometry...")
    buildings = gpd.read_file(RAW_GEOM_DIR / f"buildings{SUFFIX}.geojson")
    parcels = gpd.read_file(RAW_GEOM_DIR / f"parcels{SUFFIX}.geojson")
    green_blue = gpd.read_file(RAW_GEOM_DIR / f"green_blue{SUFFIX}.geojson")
    network = gpd.read_file(RAW_GEOM_DIR / f"network_edges{SUFFIX}.geojson")
    amenities = gpd.read_file(RAW_GEOM_DIR / f"amenities{SUFFIX}.geojson")

    print(f"  buildings:      {len(buildings)}")
    print(f"  parcels:        {len(parcels)}")
    print(f"  green_blue:     {len(green_blue)}")
    print(f"  network_edges:  {len(network)}")
    print(f"  amenities:      {len(amenities)}")

    # ------------------------------------------------------------------
    # FIX (2026-10-15c) — green layer normalisation
    # ------------------------------------------------------------------
    # (a) raw pipeline writes asset_id = "unlinked-G-xxxx", but
    #     assets.csv uses plain "G-xxxx" (from green_id). B3's
    #     green.py looks up by asset_id, so without this rewrite
    #     every green asset ends up with green_coverage = NaN.
    if "asset_id" in green_blue.columns and "green_id" in green_blue.columns:
        green_blue["asset_id"] = green_blue["green_id"]

    # (b) raw canopy_m2 is almost always NaN because OSM rarely maps
    #     tree canopy as a standalone polygon. Backfill it from the
    #     polygon's own area for vegetation types so B3's per-asset
    #     sum has something to work with.
    if "canopy_m2" in green_blue.columns and "green_type" in green_blue.columns:
        veg_types = {
            "canopy", "park", "pocket_park",
            "green_corridor", "public_space",
        }
        is_veg = green_blue["green_type"].isin(veg_types)
        needs_fill = is_veg & green_blue["canopy_m2"].isna()
        green_blue.loc[needs_fill, "canopy_m2"] = green_blue.loc[needs_fill, "area_m2"]

    print("\nProcessing geometry...")
    buildings_p = process_buildings_geometry(buildings)
    buildings_p, parcels = resolve_unassigned_parcels(buildings_p, parcels)

    amenities_p = process_amenities_geometry(amenities, buildings_p)
    population_p = generate_population(buildings_p)

    undeveloped_mocks = mock_undeveloped_parcels(parcels, n=3)
    parcels = gpd.GeoDataFrame(
        pd.concat([parcels, undeveloped_mocks], ignore_index=True),
        crs=parcels.crs,
    )
    print(f"  synthesised undeveloped parcels: {len(undeveloped_mocks)}")

    print("\nSelecting assets...")
    building_assets = select_building_assets(buildings_p, full=full)
    amenity_assets = select_amenity_assets(amenities_p, full=full)
    env_assets = select_green_and_parcel_assets(
        buildings_p, green_blue, parcels, full=full,
    )

    for src, bucket in (("buildings", building_assets),
                        ("amenities", amenity_assets),
                        ("green/parcel", env_assets)):
        for atype, records in bucket.items():
            if records:
                print(f"  [{src:<12}] {atype:<22} {len(records)}")

    # ---- assets.csv ----
    print("\nBuilding assets.csv...")
    asset_rows = []

    amenity_rows = []
    occupied_building_ids = set()
    for atype, records in amenity_assets.items():
        for i, rec in enumerate(records):
            row = amenity_to_asset_row(rec, i)
            if row is not None:
                amenity_rows.append(row)
                if row.get("building_id"):
                    occupied_building_ids.add(row["building_id"])

    for atype, records in building_assets.items():
        for i, rec in enumerate(records):
            if rec.get("building_id") in occupied_building_ids:
                continue
            asset_rows.append(derive_asset_row(rec, atype, i))

    asset_rows.extend(amenity_rows)

    for i, rec in enumerate(env_assets["green_space"]):
        asset_rows.append(derive_asset_row(rec, "green_space", i))

    for i, (_, rec) in enumerate(undeveloped_mocks.iterrows()):
        asset_rows.append(
            derive_asset_row(rec.to_dict(), "undeveloped_parcel", i)
        )

    assets_df = pd.DataFrame(asset_rows)

    # ------------------------------------------------------------------
    # FIX (2026-10-15c) — amenity independent parcels
    # ------------------------------------------------------------------
    # Amenity-derived assets (A-xxxx) share a host building's parcel.
    # B3 resolves every asset's entry point by looking up
    # `parcels.asset_id == aid`, so the 1:1 mapping leaves them
    # without a resolvable parcel and silently skips them from the
    # walking pipeline and the Huff supply model. This is the root
    # cause of missing DSR on every f_and_b / services asset.
    #
    # Give each amenity its own synthetic parcel so it becomes a
    # first-class citizen in B3.
    amenity_aids = [
        aid for aid in assets_df["asset_id"]
        if isinstance(aid, str) and aid.startswith("A-")
    ]

    if amenity_aids:
        new_amenity_parcels = []
        for i, aid in enumerate(amenity_aids):
            match = amenities_p[amenities_p["amenity_id"] == aid]
            if match.empty:
                continue
            geom = match.iloc[0].geometry
            if geom is None or geom.is_empty:
                continue

            try:
                geom_proj = gpd.GeoSeries(
                    [geom], crs=amenities_p.crs
                ).to_crs(COMPUTE_CRS).iloc[0]
                if geom_proj.geom_type == "Point":
                    parcel_geom_proj = geom_proj.buffer(15.0)
                else:
                    parcel_geom_proj = geom_proj.buffer(2.0)
                parcel_geom = gpd.GeoSeries(
                    [parcel_geom_proj], crs=COMPUTE_CRS
                ).to_crs(parcels.crs).iloc[0]
            except Exception:
                continue

            new_pid = f"P-AMN-{i + 1:04d}"
            new_amenity_parcels.append({
                "parcel_id": new_pid,
                "asset_id": aid,
                "land_use": "community_facility",
                "area_m2": float(parcel_geom_proj.area),
                "geometry_source": "Derived",
                "geometry_confidence": "low",
                "geometry": parcel_geom,
            })
            assets_df.loc[
                assets_df["asset_id"] == aid, "parcel_id"
            ] = new_pid

        if new_amenity_parcels:
            ap_gdf = gpd.GeoDataFrame(
                new_amenity_parcels, crs=parcels.crs,
            )
            parcels = gpd.GeoDataFrame(
                pd.concat([parcels, ap_gdf], ignore_index=True),
                crs=parcels.crs,
            )
            print(f"  created {len(new_amenity_parcels)} amenity parcels")

     # ------------------------------------------------------------------
    # FIX (2026-10-15d) — green_space independent parcels
    # ------------------------------------------------------------------
    # Green space assets have no parcel_id in the green_blue layer,
    # so B3 cannot resolve their geometry and skips them entirely.
    # This is why `reachable_population_walk` was 0 for every park and
    # `green_per_capita_m2` was always NaN. Give each green asset its
    # own parcel derived from its polygon.
    green_aids = [
        aid for aid in assets_df["asset_id"]
        if isinstance(aid, str) and aid.startswith("G-")
    ]

    if green_aids:
        new_green_parcels = []
        for i, aid in enumerate(green_aids):
            match = green_blue[green_blue["green_id"] == aid]
            if match.empty:
                continue
            geom = match.iloc[0].geometry
            if geom is None or geom.is_empty:
                continue

            try:
                geom_proj = gpd.GeoSeries(
                    [geom], crs=green_blue.crs
                ).to_crs(COMPUTE_CRS).iloc[0]
                if geom_proj.geom_type in ("Point", "LineString", "MultiLineString"):
                    # Points / lines do not have meaningful area;
                    # buffer them into a small polygon.
                    parcel_geom_proj = geom_proj.buffer(15.0)
                else:
                    parcel_geom_proj = geom_proj
                parcel_geom = gpd.GeoSeries(
                    [parcel_geom_proj], crs=COMPUTE_CRS
                ).to_crs(parcels.crs).iloc[0]
            except Exception:
                continue

            new_pid = f"P-GRN-{i + 1:04d}"
            new_green_parcels.append({
                "parcel_id": new_pid,
                "asset_id": aid,
                "land_use": "green_space",
                "area_m2": float(parcel_geom_proj.area),
                "geometry_source": "Derived",
                "geometry_confidence": "low",
                "geometry": parcel_geom,
            })
            assets_df.loc[
                assets_df["asset_id"] == aid, "parcel_id"
            ] = new_pid

        if new_green_parcels:
            gp_gdf = gpd.GeoDataFrame(
                new_green_parcels, crs=parcels.crs,
            )
            parcels = gpd.GeoDataFrame(
                pd.concat([parcels, gp_gdf], ignore_index=True),
                crs=parcels.crs,
            )
            print(f"  created {len(new_green_parcels)} green parcels")

    # ---- Write parcel -> asset_id mapping ----
    if not parcels.empty and not assets_df.empty:
        pid_to_aid = {}
        for _, r in assets_df.iterrows():
            pid = r.get("parcel_id")
            aid = r.get("asset_id")
            if pid is None or aid is None:
                continue
            try:
                if pd.isna(pid) or pd.isna(aid):
                    continue
            except (TypeError, ValueError):
                pass
            pid_to_aid.setdefault(str(pid), str(aid))
        parcels["asset_id"] = parcels["parcel_id"].map(
            lambda p: pid_to_aid.get(str(p))
        )

    assets_df.to_csv(PROCESSED_BIZ_DIR / "assets.csv", index=False)
    print(f"  {len(assets_df)} assets total")
    print(f"    by type:    {dict(assets_df['asset_type'].value_counts())}")

    print("\nWriting processed geometry...")
    write_layer(buildings_p, "buildings", "building_id")
    write_layer(parcels, "parcels", "parcel_id")
    write_layer(green_blue, "green_blue", "green_id")
    write_layer(network, "network_edges", "edge_id")
    write_layer(amenities_p, "amenities", "amenity_id")
    write_layer(population_p, "population", "population_id")

    # ---- Narrative anchors ----
    commercial = assets_df[assets_df["asset_type"] == "commercial"]
    facility = assets_df[assets_df["asset_type"] == "community_facility"]
    anchor_deadspace = (
        commercial["asset_id"].iloc[0] if not commercial.empty else None
    )
    anchor_facility = (
        facility["asset_id"].iloc[0] if not facility.empty else None
    )

    # ---- asset_metrics.csv ----
    print("\nBuilding asset_metrics.csv...")
    metric_rows = []
    for _, asset in assets_df.iterrows():
        role = "healthy"
        if asset["asset_id"] == anchor_deadspace:
            role = "deadspace"
        elif asset["asset_id"] == anchor_facility:
            role = "underperforming"
        metric_rows.append(derive_metrics_row(asset.to_dict(), role))

    metrics_df = pd.DataFrame(metric_rows).reindex(columns=[
        "asset_id", "year", "occupancy_rate", "vacancy_rate",
        "vacancy_duration_months", "footfall_daily",
        "utilisation_rate", "rental_income_rm", "energy_kwh",
        "metric_source", "model_version",
    ])
    metrics_df.to_csv(PROCESSED_BIZ_DIR / "asset_metrics.csv", index=False)
    print(f"  {len(metrics_df)} metric rows")

    # ---- development_projects.csv ----
    print("\nBuilding development_projects.csv...")
    undeveloped = assets_df[assets_df["asset_type"] == "undeveloped_parcel"]
    project_rows = []
    for i, (_, asset) in enumerate(undeveloped.iterrows()):
        project_rows.append({
            "project_id": f"PRJ-{i + 1:02d}",
            "parcel_id": asset["parcel_id"],
            "asset_id": None,
            "project_name": f"Proposed development on {asset['asset_id']}",
            "project_status": "proposed",
            "planned_start_year": 2027,
            "planned_delivery_year": 2030,
            "gfa_m2": 12000, "units": 80, "land_use": "commercial",
            "capex_rm": 2_700_000, "scenario_dependency": "current_plan",
        })
    pd.DataFrame(project_rows).to_csv(
        PROCESSED_BIZ_DIR / "development_projects.csv", index=False,
    )
    print(f"  {len(project_rows)} projects")

    # ---- development_candidates.csv ----
    print("\nBuilding development_candidates.csv...")
    if not undeveloped.empty:
        target_parcel = undeveloped.iloc[0]["parcel_id"]
        candidates = [
            {"candidate_id": "CAND-01", "parcel_id": target_parcel,
             "development_type": "childcare", "target_gfa_m2": 1200,
             "target_units": 1, "target_demographic": "young_families",
             "expected_capex_rm": 1_800_000, "expected_completion_year": 2029,
             "expected_demand_coverage": 0.72, "expected_utilisation": 0.78,
             "expected_carbon_tco2e": 145, "expected_accessibility_delta": 0.08,
             "feasibility_status": "feasible",
             "constraint_notes": "Complies with land use plan"},
            {"candidate_id": "CAND-02", "parcel_id": target_parcel,
             "development_type": "community_hall", "target_gfa_m2": 900,
             "target_units": 1, "target_demographic": "all_residents",
             "expected_capex_rm": 1_200_000, "expected_completion_year": 2029,
             "expected_demand_coverage": 0.68, "expected_utilisation": 0.72,
             "expected_carbon_tco2e": 110, "expected_accessibility_delta": 0.10,
             "feasibility_status": "feasible",
             "constraint_notes": "Complies with land use plan"},
            {"candidate_id": "CAND-03", "parcel_id": target_parcel,
             "development_type": "park", "target_gfa_m2": 3600,
             "target_units": 0, "target_demographic": "public",
             "expected_capex_rm": 400_000, "expected_completion_year": 2027,
             "expected_demand_coverage": 1.00, "expected_utilisation": 0.85,
             "expected_carbon_tco2e": 15, "expected_accessibility_delta": 0.15,
             "feasibility_status": "feasible",
             "constraint_notes": "Low CAPEX ecological upgrade"},
        ]
        pd.DataFrame(candidates).to_csv(
            PROCESSED_BIZ_DIR / "development_candidates.csv", index=False,
        )
        print(f"  {len(candidates)} candidates")
    else:
        pd.DataFrame().to_csv(
            PROCESSED_BIZ_DIR / "development_candidates.csv", index=False,
        )
        print("  0 candidates")

    # ---- interventions.csv ----
    # Baseline + two contrasting scenarios so B4 has something to
    # compare. All IDs are resolved dynamically because OSM-derived
    # asset IDs are not known ahead of time.
    print("\nBuilding interventions.csv...")

    intervention_rows = [{
        "scenario_id": "SC-CURRENT",
        "intervention_id": "INT-000",
        "target_asset_id": None,
        "intervention_type": "no_op",
        "parameters_json": "{}",
        "expected_derived_json": None,
        "expected_source": None,
        "construction_start_year": BASE_YEAR,
        "construction_duration_months": 0,
        "activation_year": BASE_YEAR,
        "during_construction_status": "operational",
        "capex_delta_rm": 0,
        "opex_delta_rm": 0,
        "validation_status": "validated",
        "status": "applied",
    }]

    # SC-REPURPOSE: repurpose the first commercial asset to a clinic,
    # plus a walkability upgrade on the same asset's nearest edge.
    if not commercial.empty:
        repurpose_target = commercial.iloc[0]["asset_id"]
        intervention_rows.append({
            "scenario_id": "SC-REPURPOSE",
            "intervention_id": "INT-001",
            "target_asset_id": repurpose_target,
            "intervention_type": "repurpose",
            "parameters_json": json.dumps({
                "to_subtype": "clinic",
                "new_capacity": 200,
            }),
            "expected_derived_json": json.dumps({
                "utilisation": 0.72,
                "service_coverage": 0.65,
            }),
            "expected_source": "mock_estimate",
            "construction_start_year": BASE_YEAR + 1,
            "construction_duration_months": 18,
            "activation_year": BASE_YEAR + 2,
            "during_construction_status": "unavailable",
            "capex_delta_rm": 1_200_000,
            "opex_delta_rm": 60_000,
            "validation_status": "validated",
            "status": "simulated",
        })
        intervention_rows.append({
            "scenario_id": "SC-REPURPOSE",
            "intervention_id": "INT-002",
            "target_asset_id": repurpose_target,
            "intervention_type": "pedestrian_upgrade",
            "parameters_json": json.dumps({"canopy_boost": 0.30}),
            "expected_derived_json": None,
            "expected_source": None,
            "construction_start_year": BASE_YEAR + 1,
            "construction_duration_months": 6,
            "activation_year": BASE_YEAR + 2,
            "during_construction_status": "partial",
            "capex_delta_rm": 180_000,
            "opex_delta_rm": 5_000,
            "validation_status": "validated",
            "status": "simulated",
        })

    # SC-DELAY: postpone the first development project to 2033.
    if not undeveloped.empty:
        first_project_id = "PRJ-01"   # matches the naming above
        intervention_rows.append({
            "scenario_id": "SC-DELAY",
            "intervention_id": "INT-003",
            "target_asset_id": first_project_id,
            "intervention_type": "delay_development",
            "parameters_json": json.dumps({"until": 2033}),
            "expected_derived_json": None,
            "expected_source": None,
            "construction_start_year": BASE_YEAR + 1,
            "construction_duration_months": 0,
            "activation_year": BASE_YEAR + 1,
            "during_construction_status": "operational",
            "capex_delta_rm": 0,
            "opex_delta_rm": 0,
            "validation_status": "validated",
            "status": "simulated",
        })

    pd.DataFrame(intervention_rows).to_csv(
        PROCESSED_BIZ_DIR / "interventions.csv", index=False,
    )
    print(f"  {len(intervention_rows)} interventions "
          f"({sum(1 for r in intervention_rows if r['scenario_id'] == 'SC-CURRENT')} current, "
          f"{sum(1 for r in intervention_rows if r['scenario_id'] == 'SC-REPURPOSE')} repurpose, "
          f"{sum(1 for r in intervention_rows if r['scenario_id'] == 'SC-DELAY')} delay)")

    print("\n" + "=" * 72)
    print(f"  Processed geometry -> {PROCESSED_GEOM_DIR}")
    print(f"  Processed business -> {PROCESSED_BIZ_DIR}")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    main()