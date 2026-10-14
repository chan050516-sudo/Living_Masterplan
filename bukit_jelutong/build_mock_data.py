"""Bukit Jelutong preprocessing: raw OSM -> processed geometry + business.

Reads the raw OSM extraction (bukit_jelutong/raw/geometry/*_bj.geojson)
and produces:

  processed/geometry/*.geojson
      Geometry layers with derived attributes.
  processed/business/*.csv
      assets, asset_metrics, development_projects,
      development_candidates, interventions.

Asset sources (2026-10-15):
    buildings     -> residential, commercial (from OSM building tags)
    amenities     -> community_facility (school, clinic, worship, ...)
                     + commercial (food_beverage, finance, retail)
    green_blue    -> green_space (park, public_space)
    parcels       -> undeveloped_parcel (parcels without buildings)

    Facilities are pulled from the amenities layer rather than from
    buildings because OSM tags school / clinic / worship zones as
    amenity polygons, not as typed building footprints. This removes
    the need for spatial joins and gives every facility a real
    location. Buildings with a community_facility tag are excluded
    from the asset layer to avoid duplication.

Inference corrections (2026-10-15):
  - Unknown building_type (OSM `building=yes`) no longer falls through
    to "vacant". Footprint brackets are used to infer subtype.
  - Attachments (roof, shed, hut, carport) and buildings < 40 m² are
    excluded from the asset layer.
  - Office floor range narrowed to (2, 5).
  - Apartment highrise floor range narrowed to (6, 12).
  - Oversized commercial (>10,000 m²) maps to supermarket instead of
    office.

Usage:
    python bukit_jelutong/build_mock_data.py
    python bukit_jelutong/build_mock_data.py --sample
"""

import argparse
import hashlib
from pathlib import Path

import geopandas as gpd
import pandas as pd

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


# ================================================================
# 1. Seeded randomness
# ================================================================

def seeded_uniform(key: str, lo: float, hi: float) -> float:
    h = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16)
    u = (h % 10_000_000) / 10_000_000.0
    return lo + (hi - lo) * u


def seeded_int(key: str, lo: int, hi: int) -> int:
    return int(round(seeded_uniform(key, lo, hi + 0.999999)))


# ================================================================
# 2. Building subtype inference
# ================================================================

FLOOR_RANGE_BY_SUBTYPE = {
    # Residential
    "bungalow":           (1, 2),
    "detached":           (1, 3),
    "semidetached":       (2, 3),
    "terrace":            (2, 2),
    "apartment_lowrise":  (3, 5),
    "apartment_highrise": (6, 12),
    "affordable_housing": (4, 8),
    "dormitory":          (3, 5),
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
    """
    Return the taxonomy subtype, or None when the building is an
    attachment or below MIN_BUILDING_FOOTPRINT_M2.
    """
    bt = str(raw).strip().lower() if raw else ""
    fp = float(footprint_m2 or 0)

    if bt in ATTACHMENT_RAW_VALUES:
        return None
    if fp < MIN_BUILDING_FOOTPRINT_M2:
        return None

    # Residential explicit tags.
    if bt == "bungalow":
        return "bungalow"
    if bt in {"detached", "detached_house"}:
        return "detached"
    if bt in {"semidetached_house", "semi-detached", "semi_detached"}:
        return "semidetached"
    if bt in {"terrace", "terraced_house", "row_house"}:
        return "terrace"
    if bt in {"apartments", "apartment"}:
        return "apartment_highrise" if fp > 2000 else "apartment_lowrise"
    if bt == "dormitory":
        return "dormitory"
    if bt == "house":
        if fp < 150:
            return "terrace"
        if fp < 400:
            return "semidetached"
        return "detached"

    # Commercial.
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

    # Community.
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

    # Fallback by building_type.
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
        if fp < 5000:
            return "supermarket"
        return "supermarket"

    if building_type == "community_facility":
        if fp > 5000:
            return "school"
        return "community_hall"

    if building_type == "industrial":
        return "office"

    # building_type == "unknown" (OSM building=yes).
    if building_type in {"unknown", "yes", ""}:
        if fp > 8000:
            return "school"
        if fp > 4000:
            return "apartment_lowrise"
        if fp > 1500:
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


# amenity_type -> (asset_type, subtype, default_footprint_m2)
# default_footprint_m2 is used when the amenity is a Point or a
# geometry smaller than 40 m².
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
    # "parking", "fuel", "bus_stop", "transit_station", "other"
    # are intentionally excluded: they are not revenue assets.
}


def amenity_to_asset_row(row, index: int) -> dict:
    """
    Convert one amenity GeoJSON row into an asset row.

    Footprint resolution:
      - Polygon geometry: use its projected area.
      - Point geometry or very small polygon: use the subtype default.
    """
    atype_map = AMENITY_TO_ASSET.get(row["amenity_type"])
    if atype_map is None:
        return None

    asset_type, subtype, default_fp = atype_map

    # Footprint from geometry.
    geom = row.get("geometry")
    if geom is not None and geom.geom_type in ("Polygon", "MultiPolygon"):
        # Read the geometry from the projected copy.
        fp = float(row.get("_area_m2") or 0.0)
        if fp < MIN_BUILDING_FOOTPRINT_M2:
            fp = default_fp
    else:
        fp = default_fp

    # Floors from subtype range, deterministically seeded.
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

    return {
        "asset_id": row["amenity_id"],
        "asset_type": asset_type,
        "subtype": subtype,
        "parcel_id": None,
        "building_id": None,
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
        "data_completeness": 0.70,
        "data_sources": "osm_amenity;derived",
    }


# ================================================================
# 4. Capacity and cost tables
# ================================================================

CAPACITY_PER_M2 = {
    "terrace":            1 / 50,
    "semidetached":       1 / 55,
    "bungalow":           1 / 60,
    "detached":           1 / 60,
    "apartment_lowrise":  1 / 45,
    "apartment_highrise": 1 / 40,
    "affordable_housing": 1 / 35,
    "dormitory":          1 / 25,
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
    "bungalow":           "families",
    "detached":           "families",
    "apartment_lowrise":  "young_families",
    "apartment_highrise": "young_adults",
    "dormitory":          "students",
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


# ================================================================
# 5. Geometry processors
# ================================================================

def process_buildings_geometry(buildings: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf = buildings.copy()

    subtypes, floors_list, gfa_list, is_asset = [], [], [], []
    for _, row in gdf.iterrows():
        subtype = infer_subtype(
            raw=row.get("building_raw"),
            footprint_m2=float(row.get("footprint_m2") or 0),
            building_type=row.get("building_type") or "unknown",
        )
        subtypes.append(subtype)
        if subtype is None:
            floors_list.append(None)
            gfa_list.append(None)
            is_asset.append(False)
            continue
        lo, hi = FLOOR_RANGE_BY_SUBTYPE.get(subtype, (1, 2))
        fl = seeded_int(f"{row['building_id']}-floors", lo, hi)
        floors_list.append(fl)
        fp = float(row.get("footprint_m2") or 0)
        gfa_list.append(fp * fl)
        is_asset.append(True)

    gdf["subtype"] = subtypes
    gdf["floors_derived"] = floors_list
    gdf["gfa_derived_m2"] = gfa_list
    gdf["is_asset"] = is_asset
    gdf["floors"] = gdf["floors_derived"]
    gdf["gfa_m2"] = gdf["gfa_derived_m2"]

    n_assets = int(sum(is_asset))
    print(f"  buildings: {n_assets} assets, {len(gdf) - n_assets} excluded")
    return gdf


def process_amenities_geometry(amenities: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Add the normalised amenity_type and a projected area column.
    The raw amenity_type_raw is preserved.
    """
    gdf = amenities.copy()
    if "amenity_type_raw" not in gdf.columns:
        gdf["amenity_type_raw"] = gdf.get("amenity_type")
    gdf["amenity_type"] = gdf["amenity_type_raw"].apply(normalize_amenity_type)

    # Projected area (used by amenity_to_asset_row).
    proj = gdf.to_crs(COMPUTE_CRS)
    gdf["_area_m2"] = proj.geometry.area
    return gdf


def generate_population(buildings: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    residential = buildings[
        buildings["subtype"].isin({
            "terrace", "semidetached", "bungalow", "detached",
            "apartment_lowrise", "apartment_highrise",
            "affordable_housing", "dormitory",
        })
    ].copy()

    if residential.empty:
        return gpd.GeoDataFrame(
            columns=["population_id", "total_population", "age_0_14",
                     "age_15_64", "age_65_plus", "household_size",
                     "source", "geometry"],
            crs=DISPLAY_CRS,
        )

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
            gfa = float(b.get("gfa_derived_m2") or 0)
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

    return gpd.GeoDataFrame(rows, geometry="geometry", crs=COMPUTE_CRS).to_crs(DISPLAY_CRS)


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
    """
    Building-sourced assets: residential and commercial only.
    Community facilities come from the amenities layer.
    """
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
    """
    Amenity-sourced assets. Filters to those that map to a taxonomy
    subtype, then buckets into community_facility and commercial.
    """
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
    path = PROCESSED_GEOM_DIR / f"{name}{SUFFIX}.geojson"
    out = gdf.to_crs(DISPLAY_CRS).copy()
    # Drop helper columns.
    drop = [c for c in out.columns if c.startswith("_")]
    if drop:
        out = out.drop(columns=drop)
    if id_col and id_col in out.columns:
        out = out.set_index(id_col)
        out.index.name = None
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

    print("\nProcessing geometry...")
    buildings_p = process_buildings_geometry(buildings)
    amenities_p = process_amenities_geometry(amenities)
    population_p = generate_population(buildings_p)

    print("\nWriting processed geometry...")
    write_layer(buildings_p, "buildings", "building_id")
    write_layer(parcels, "parcels", "parcel_id")
    write_layer(green_blue, "green_blue", "green_id")
    write_layer(network, "network_edges", "edge_id")
    write_layer(amenities_p, "amenities", "amenity_id")
    write_layer(population_p, "population", "population_id")

    # ---- Asset assembly ----
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

    # 1. Buildings: residential + commercial
    for atype, records in building_assets.items():
        for i, rec in enumerate(records):
            asset_rows.append(derive_asset_row(rec, atype, i))

    # 2. Amenities: community_facility + commercial
    for atype, records in amenity_assets.items():
        for i, rec in enumerate(records):
            row = amenity_to_asset_row(rec, i)
            if row is not None:
                asset_rows.append(row)

    # 3. Green / parcel
    for atype, records in env_assets.items():
        for i, rec in enumerate(records):
            asset_rows.append(derive_asset_row(rec, atype, i))

    assets_df = pd.DataFrame(asset_rows)
    assets_df.to_csv(PROCESSED_BIZ_DIR / "assets.csv", index=False)
    print(f"  {len(assets_df)} assets total")
    print(f"    by type:    {dict(assets_df['asset_type'].value_counts())}")

    # Narrative anchors: first commercial is deadspace, first
    # community_facility is underperforming.
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
    print("\nBuilding interventions.csv...")
    pd.DataFrame([{
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
    }]).to_csv(PROCESSED_BIZ_DIR / "interventions.csv", index=False)
    print("  1 intervention (SC-CURRENT baseline)")

    print("\n" + "=" * 72)
    print(f"  Processed geometry -> {PROCESSED_GEOM_DIR}")
    print(f"  Processed business -> {PROCESSED_BIZ_DIR}")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    main()