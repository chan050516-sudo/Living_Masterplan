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

    ownership_status = _OWNERSHIP_STATUS_BY_TYPE.get(
        asset_type, "public_transferred",
    )
    authority = _AUTHORITY_BY_OWNERSHIP.get(ownership_status, "advisory")

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
        "ownership_status": ownership_status,
        "authority": authority,
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

# Phase 15 — ownership status and authority mapping.
#
# In a real township, ownership is not a single axis. A residential
# unit can be:
#   - developer_held      — Sime Darby owns it outright (unsold
#                           inventory, sample units, rental stock)
#   - sold                — individual buyer owns it (SPA signed,
#                           vacant possession issued)
#   - strata_jmb          — stratified parcel, managed by a JMB / MC
#   - public_transferred  — handed over to a local authority
#
# Authority is derived from ownership. A developer can repurpose an
# unsold unit but cannot repurpose an owner-occupied one.
_OWNERSHIP_STATUS_BY_TYPE = {
    "residential":         "sold",
    "commercial":          "developer_held",
    "undeveloped_parcel":  "developer_held",
    "community_facility":  "public_transferred",
    "green_space":         "public_transferred",
}

_AUTHORITY_BY_OWNERSHIP = {
    "developer_held":      "full_control",
    "sold":                "advisory",
    "public_transferred":  "advisory",
    "strata_jmb":          "shared",
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


def _evict_buildings_from_parcels(
    buildings: gpd.GeoDataFrame,
    parcels: gpd.GeoDataFrame,
    n=3,
    min_area_m2=4500.0,
    prefer_edge=True,
) -> tuple:
    """
    Phase 15d — clear the buildings off a small number of parcels
    and relabel them as undeveloped.

    Why this exists
    ---------------
    The pure grid-scanning approach produced parcels whose shapes
    were the residual of "cell minus buildings" — hourglass- and
    L-shaped polygons with wildly varying areas. They read as
    algorithmic artefacts on the 3D map.

    Existing parcels, by contrast, are real, planning-verified
    shapes with a road frontage. Evicting the buildings from the
    largest and most peripheral ones yields exactly the kind of
    plot a developer would call "undeveloped land".

    Selection priority (highest to lowest):
      1. Peripheral (distance from township centroid) — real
         undeveloped land is at the edge, not in the core.
      2. Large parcel area.
      3. Fewer buildings (cheaper to evict, fewer households to
         rebase).

    Returns
    -------
    (buildings_after, parcels_after, n_evicted)
        parcels_after has the evicted parcels renamed to
        P-VAC-01 ... P-VAC-N so the caller can start the
        synthesised parcels at N+1.
    """
    if buildings.empty or parcels.empty or n <= 0:
        return buildings, parcels, 0

    parcels_proj = parcels.to_crs("EPSG:32647")
    b_parcel_counts = buildings["parcel_id"].value_counts().to_dict()
    centroid = parcels_proj.geometry.union_all().centroid

    candidates = []
    for pid, count in b_parcel_counts.items():
        if pid in (None, "P-UNASSIGNED"):
            continue
        pr_match = parcels[parcels["parcel_id"] == pid]
        if pr_match.empty:
            continue
        area = float(pr_match.iloc[0].get("area_m2") or 0)
        if area < min_area_m2:
            continue

        pr_proj_match = parcels_proj[parcels_proj["parcel_id"] == pid]
        if pr_proj_match.empty:
            continue
        dist = pr_proj_match.iloc[0].geometry.centroid.distance(centroid)

        candidates.append({
            "parcel_id": pid,
            "area_m2": area,
            "building_count": int(count),
            "distance_m": float(dist),
        })

    if not candidates:
        return buildings, parcels, 0

    if prefer_edge:
        candidates.sort(
            key=lambda c: (-c["distance_m"], -c["area_m2"], c["building_count"])
        )
    else:
        candidates.sort(key=lambda c: -c["area_m2"])

    evicted_pids = []
    evicted_bids = set()
    for cand in candidates:
        if len(evicted_pids) >= n:
            break
        pid = cand["parcel_id"]
        bids = set(
            buildings[buildings["parcel_id"] == pid]["building_id"].tolist()
        )
        if not bids:
            continue
        evicted_pids.append(pid)
        evicted_bids |= bids

    if not evicted_pids:
        return buildings, parcels, 0

    buildings_after = buildings[
        ~buildings["building_id"].isin(evicted_bids)
    ].copy()

    parcels_after = parcels.copy()
    for i, pid in enumerate(evicted_pids):
        new_pid = f"P-VAC-{i + 1:02d}"
        mask = parcels_after["parcel_id"] == pid
        parcels_after.loc[mask, "parcel_id"] = new_pid
        parcels_after.loc[mask, "asset_id"] = new_pid
        parcels_after.loc[mask, "land_use"] = "undeveloped"

    print(
        f"  evicted {len(evicted_bids)} buildings from "
        f"{len(evicted_pids)} parcels → P-VAC-01..{len(evicted_pids):02d}"
    )
    for cand, pid in zip(candidates[:len(evicted_pids)], evicted_pids):
        print(
            f"    {pid} → P-VAC: {cand['area_m2']:.0f} m², "
            f"{cand['building_count']} buildings, "
            f"{cand['distance_m']:.0f} m from centre"
        )

    return buildings_after, parcels_after, len(evicted_pids)


def _synthesize_vacant_parcels(
    buildings_gdf,
    green_blue_gdf,
    n=9,
    cell_size_m=150.0,
    min_area_m2=1000.0,
    max_area_m2=10000.0,
    min_spacing_m=250.0,
    edge_buffer_m=2.0,
    start_index=0,
):
    """
    Synthesise truly vacant parcels by carving the gaps between
    buildings.

    Parameters
    ----------
    n : int
        Target count.
    cell_size_m : float
        Grid cell width for the primary scan. 150 m matches a
        typical shoplot block. If the primary scan yields too few
        candidates, smaller sizes (100, 80, 60) are tried in turn.
    min_area_m2 / max_area_m2 : float
        Residual polygon must fall in this range.
    min_spacing_m : float
        Minimum centroid distance between picked parcels. If the
        target cannot be reached at this spacing, the check is
        progressively relaxed to 70%, 50%, 35%, 25% of the value,
        floor 60 m.
    start_index : int
        Numbering offset. When the caller has already evicted N
        parcels as P-VAC-01..N, pass N here so synthesised parcels
        begin at P-VAC-(N+1).
    """
    from shapely.geometry import box

    empty = gpd.GeoDataFrame(
        columns=[
            "parcel_id", "asset_id", "land_use", "area_m2",
            "geometry_source", "geometry_confidence", "geometry",
        ],
        crs=buildings_gdf.crs,
    )
    if buildings_gdf is None or buildings_gdf.empty or n <= 0:
        return empty

    proj_crs = "EPSG:32647"
    b_proj = buildings_gdf.to_crs(proj_crs)
    b_union = b_proj.geometry.union_all()

    gb_union = None
    if green_blue_gdf is not None and not green_blue_gdf.empty:
        gb_union = green_blue_gdf.to_crs(proj_crs).geometry.union_all()

    minx, miny, maxx, maxy = b_proj.total_bounds
    minx += cell_size_m / 2.0
    miny += cell_size_m / 2.0
    maxx -= cell_size_m / 2.0
    maxy -= cell_size_m / 2.0

    def _scan(cell_sz):
        cands = []
        nxx = int((maxx - minx) / cell_sz) + 1
        nyy = int((maxy - miny) / cell_sz) + 1
        for ix in range(nxx):
            for iy in range(nyy):
                x0 = minx + ix * cell_sz
                y0 = miny + iy * cell_sz
                cell = box(x0, y0, x0 + cell_sz, y0 + cell_sz)

                neighbourhood = box(
                    x0 - cell_sz, y0 - cell_sz,
                    x0 + 2 * cell_sz, y0 + 2 * cell_sz,
                )
                if not b_union.intersects(neighbourhood):
                    continue

                residual = cell.difference(b_union)
                if gb_union is not None:
                    residual = residual.difference(gb_union)
                if residual.is_empty:
                    continue
                if residual.geom_type == "MultiPolygon":
                    residual = max(residual.geoms, key=lambda g: g.area)
                if residual.geom_type != "Polygon":
                    continue
                area = residual.area
                if not (min_area_m2 <= area <= max_area_m2):
                    continue
                cands.append({"geometry": residual, "area": area})
        return cands

    candidates = _scan(cell_size_m)
    if not candidates:
        for smaller in (100.0, 80.0, 60.0):
            if smaller >= cell_size_m:
                continue
            candidates = _scan(smaller)
            if candidates:
                print(f"  [P-VAC] primary cell {cell_size_m:.0f}m empty, "
                      f"retried at {smaller:.0f}m")
                break

    if not candidates:
        return empty

    import random
    random.Random(42).shuffle(candidates)

    def _thin(cands, n_target, min_dist):
        picked_local = []
        for cand in cands:
            if len(picked_local) >= n_target:
                break
            c = cand["geometry"].centroid
            # Centroid distance check
            if not all(
                c.distance(p["geometry"].centroid) >= min_dist
                for p in picked_local
            ):
                continue
            # Geometric non-overlap check. Centroid distance alone
            # allows two large parcels 250 m apart to share a strip
            # of area at their boundaries, which shows up as a
            # double-drawn outline on the 3D map.
            area = cand["geometry"].area
            overlaps_existing = False
            for p in picked_local:
                try:
                    inter_area = cand["geometry"].intersection(
                        p["geometry"]
                    ).area
                except Exception:
                    continue
                if inter_area > area * 0.05:
                    overlaps_existing = True
                    break
            if overlaps_existing:
                continue
            picked_local.append(cand)
        return picked_local

    picked = _thin(candidates, n, min_spacing_m)
    if len(picked) < n:
        for factor in (0.7, 0.5, 0.35, 0.25):
            tighter = max(60.0, min_spacing_m * factor)
            picked = _thin(candidates, n, tighter)
            if len(picked) >= n:
                print(f"  [P-VAC] relaxed spacing to {tighter:.0f} m")
                break

    if not picked:
        return empty

    rows = []
    for i, cand in enumerate(picked):
        geom = cand["geometry"]
        # Morphological opening: erode then dilate by the same
        # amount. Removes thin connective tissue without eroding
        # the whole polygon (the previous buffer(-2.0) dropped
        # L-shaped residuals entirely).
        try:
            opened = geom.buffer(-edge_buffer_m).buffer(edge_buffer_m)
        except Exception:
            opened = geom
        if opened.is_empty:
            opened = geom
        if opened.geom_type == "MultiPolygon":
            opened = max(opened.geoms, key=lambda g: g.area)
        if opened.geom_type != "Polygon":
            opened = geom
        opened = opened.buffer(0)
        if opened.is_empty:
            continue
        if opened.geom_type == "MultiPolygon":
            opened = max(opened.geoms, key=lambda g: g.area)
        if opened.geom_type != "Polygon":
            continue

        # Phase 15e — buffer(0) can expand the geometry back over
        # neighbouring parcels and buildings. Re-subtract and light-
        # open one final time so the written geometry is guaranteed
        # not to overlap anything.
        opened = opened.difference(b_union)
        if gb_union is not None:
            opened = opened.difference(gb_union)
        if opened.is_empty:
            continue
        if opened.geom_type == "MultiPolygon":
            opened = max(opened.geoms, key=lambda g: g.area)
        if opened.geom_type != "Polygon":
            continue

        idx = start_index + i + 1
        rows.append({
            "parcel_id": f"P-VAC-{idx:02d}",
            "asset_id": f"P-VAC-{idx:02d}",
            "land_use": "undeveloped",
            "area_m2": float(opened.area),
            "geometry_source": "Derived",
            "geometry_confidence": "medium",
            "geometry": opened,
        })

    if not rows:
        return empty

    result = gpd.GeoDataFrame(rows, geometry="geometry", crs=proj_crs)
    return result.to_crs(buildings_gdf.crs)


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
    # Phase 15 — Elmina-style completion year distribution:
    # 60% of the portfolio is recent (last 8 years), 30% is mid-life
    # (9-16 years), 10% is older. A uniform 2-25 year distribution
    # would misrepresent a mid-development township.
    _age_band = seeded_uniform(f"{seed_base}-ageband", 0.0, 1.0)
    if _age_band < 0.60:
        completion_year = BASE_YEAR - seeded_int(f"{seed_base}-age", 1, 8)
    elif _age_band < 0.90:
        completion_year = BASE_YEAR - seeded_int(f"{seed_base}-age", 9, 16)
    else:
        completion_year = BASE_YEAR - seeded_int(f"{seed_base}-age", 17, 25)

    ownership_status = _OWNERSHIP_STATUS_BY_TYPE.get(atype, "public_transferred")
    authority = _AUTHORITY_BY_OWNERSHIP.get(ownership_status, "advisory")

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
        "ownership_status": ownership_status,
        "authority": authority,
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


def _convert_residential_to_shoplot(assets_df, buildings_gdf, network_gdf, n=12):
    """
    Convert a subset of residential buildings facing a main road into
    commercial shoplot.

    Planning basis (PLANMalaysia):
      For 800 residential units the standard is 15-30 shoplot
      (ratio 1:20 to 1:30). The existing amenity layer contributes
      24 commercial. Converting 12 more brings the total to 36,
      ratio 818:36 ≈ 1:23, inside the standard.

    Selection priority:
      1. Adjacent to a primary / secondary / tertiary edge.
      2. Built-form residential only (terrace / semidetached /
         detached), never apartment.
      3. Larger floor area as a tiebreaker.

    The candidate pool is drawn from the ASSETS table and joined to
    the building layer by `building_id`. Filtering on the building
    layer first and matching back to assets missed most candidates
    because the building layer contains attachments and undersized
    rows that never became assets.
    """
    if network_gdf is None or buildings_gdf is None:
        return assets_df, set()

    main_roads = network_gdf[
        network_gdf["edge_type"].isin(["primary", "secondary", "tertiary"])
    ]
    main_union = main_roads.geometry.union_all() if not main_roads.empty else None

    # Building centroids by building_id (not asset_id — asset_id on
    # the building layer is unlinked-xxx, which never matches the
    # assets table).
    b_geom = buildings_gdf[
        buildings_gdf["subtype"].isin(["terrace", "semidetached", "detached"])
    ].to_crs("EPSG:32647")
    if b_geom.empty:
        return assets_df, set()

    centroids = {
        row["building_id"]: row.geometry.centroid
        for _, row in b_geom.iterrows()
        if row.get("building_id")
    }

    # Draw candidates from assets_df.
    res_assets = assets_df[
        (assets_df["asset_type"] == "residential")
        & (assets_df["subtype"].isin(["terrace", "semidetached", "detached"]))
    ].copy()
    if res_assets.empty:
        return assets_df, set()

    # Attach a centroid if we can resolve the building.
    main_union_proj = None
    if main_union is not None:
        try:
            main_union_proj = gpd.GeoSeries(
                [main_union], crs=network_gdf.crs
            ).to_crs("EPSG:32647").iloc[0]
        except Exception:
            main_union_proj = None

    def _dist_to_main(row):
        bid = row.get("building_id")
        if not isinstance(bid, str):
            return 1e9
        c = centroids.get(bid)
        if c is None or main_union_proj is None:
            return 1e9
        return c.distance(main_union_proj)

    res_assets["_dist_to_main"] = res_assets.apply(_dist_to_main, axis=1)
    res_assets = res_assets.sort_values(
        ["_dist_to_main", "floor_area_m2"],
        ascending=[True, False],
    )

    # Pull a wider pool, then keep the first `n` that have a
    # resolvable centroid.
    pool = res_assets.head(n * 4)
    kept = []
    for _, row in pool.iterrows():
        bid = row.get("building_id")
        if isinstance(bid, str) and bid in centroids:
            kept.append(row["asset_id"])
        if len(kept) >= n:
            break

    if not kept:
        return assets_df, set()

    subtype_pattern = (
        ["convenience_retail"] * 3
        + ["f_and_b"] * 4
        + ["services"] * 3
        + ["medical_retail"] * 2
    )

    converted_ids = set()
    for i, aid in enumerate(kept):
        subtype = subtype_pattern[i % len(subtype_pattern)]
        idx = assets_df.index[assets_df["asset_id"] == aid]
        if len(idx) == 0:
            continue
        idx = idx[0]
        row = assets_df.loc[idx]

        floor_area = float(row.get("floor_area_m2") or 0.0)
        lettable = floor_area * LETTABLE_FRACTION["commercial"]
        capex = floor_area * CAPEX_PER_M2["commercial"]
        opex = capex * OPEX_FRACTION["commercial"]
        maintenance = capex * MAINTENANCE_FRACTION["commercial"]
        capacity = int(round(floor_area * CAPACITY_PER_M2.get(subtype, 1 / 60)))

        assets_df.loc[idx, "asset_type"] = "commercial"
        assets_df.loc[idx, "subtype"] = subtype
        assets_df.loc[idx, "land_use"] = "commercial"
        assets_df.loc[idx, "asset_name"] = (
            f"{subtype.replace('_', ' ').title()} {aid}"
        )
        assets_df.loc[idx, "lettable_area_m2"] = round(lettable, 2)
        assets_df.loc[idx, "capex_initial_rm"] = round(capex, 2)
        assets_df.loc[idx, "opex_annual_rm"] = round(opex, 2)
        assets_df.loc[idx, "maintenance_annual_rm"] = round(maintenance, 2)
        assets_df.loc[idx, "capacity"] = capacity
        assets_df.loc[idx, "target_demographic"] = (
            TARGET_DEMOGRAPHIC_BY_SUBTYPE.get(subtype, "all")
        )
        assets_df.loc[idx, "ownership_status"] = "developer_held"
        assets_df.loc[idx, "authority"] = "full_control"
        converted_ids.add(aid)

    print(f"  converted {len(converted_ids)} residential → shoplot")
    return assets_df, converted_ids


def _mark_unsold_inventory(
    assets_df,
    n_residential=120,
    n_commercial=10,
    exclude_ids=None,
):
    """
    Mark a realistic fraction of the portfolio as unsold or unleased
    developer-held inventory.

    Calibration: Elmina is a mid-development Sime Darby township.
    At any year roughly 15% of residential units are built but
    unsold, and roughly 40% of the shops delivered in the last
    3 years are not yet leased. This function reproduces that mix
    deterministically so the down-stream pipeline sees a realistic
    deadspace population instead of a mature fully-sold township.

    Selection strategy for residential (in priority order):
      - 40% from the newest 3 years (2023-2025)
      - 40% from the 5-8 year band (2018-2022)
      - 20% from the 10+ year band (2015 or older)
    This mirrors the way a developer accumulates slow-moving
    inventory across multiple delivery cycles — it is not just the
    latest phase that is sitting unsold.
    """
    unsold_ids = set()

    exclude = set(exclude_ids or [])

    res_pool = assets_df[
        (assets_df["asset_type"] == "residential")
        & (assets_df["ownership_status"] == "sold")
        & (~assets_df["asset_id"].isin(exclude))
    ].copy()
    if not res_pool.empty:
        res_pool = res_pool.sort_values(
            ["completion_year", "asset_id"],
            ascending=[False, True],
            na_position="last",
        )
        n_new = int(n_residential * 0.40)
        n_mid = int(n_residential * 0.40)
        n_old = n_residential - n_new - n_mid

        def _band(df, lo, hi):
            return df[
                (df["completion_year"] >= lo) & (df["completion_year"] <= hi)
            ]

        picked = []
        picked.extend(_band(res_pool, 2023, 2030).head(n_new)["asset_id"])
        picked.extend(_band(res_pool, 2018, 2022).head(n_mid)["asset_id"])
        older = res_pool[res_pool["completion_year"] < 2018]
        picked.extend(older.head(n_old)["asset_id"])

        # If any band was short, top up from the newest available.
        if len(picked) < n_residential:
            remaining = res_pool[
                ~res_pool["asset_id"].isin(picked)
            ].head(n_residential - len(picked))
            picked.extend(remaining["asset_id"])

        unsold_ids |= set(picked)
        assets_df.loc[
            assets_df["asset_id"].isin(unsold_ids),
            "ownership_status",
        ] = "developer_held"
        assets_df.loc[
            assets_df["asset_id"].isin(unsold_ids),
            "authority",
        ] = "full_control"

    com_pool = assets_df[
        (assets_df["asset_type"] == "commercial")
        & (assets_df["ownership_status"] == "developer_held")
        & (~assets_df["asset_id"].isin(exclude))
    ].sort_values(
        ["completion_year", "asset_id"],
        ascending=[False, True],
        na_position="last",
    )
    com_picked = list(com_pool.head(n_commercial)["asset_id"])
    unsold_ids |= set(com_picked)

    print(
        f"  marked unsold inventory: "
        f"{len([x for x in unsold_ids if x.startswith('BLD-')])} residential + "
        f"{len(com_picked)} commercial"
    )
    return assets_df, unsold_ids


def _mark_developer_held_facilities(assets_df, n=6):
    """
    In a mid-development township, some community facilities are
    still operated by the developer and not yet handed over to the
    local authority. These are not eligible for public_provision
    classification — they are the developer's own assets.
    """
    fac = assets_df[
        (assets_df["asset_type"] == "community_facility")
        & (assets_df["ownership_status"] == "public_transferred")
    ].sort_values(
        ["completion_year", "asset_id"],
        ascending=[False, True],
        na_position="last",
    )
    picked = set(fac.head(n)["asset_id"])
    if not picked:
        return assets_df
    assets_df.loc[
        assets_df["asset_id"].isin(picked),
        "ownership_status",
    ] = "developer_held"
    assets_df.loc[
        assets_df["asset_id"].isin(picked),
        "authority",
    ] = "full_control"
    print(f"  marked developer-held facilities: {len(picked)}")
    return assets_df


def _derive_metrics_for_unsold(asset, aid):
    """
    Metrics for unsold developer-held residential inventory.

    The defining property of an unsold unit is that nobody is living
    in it — not that the physical shell is different. So occupancy
    is 0, vacancy is the full duration since completion, and NOI is
    whatever the holding cost produces.
    """
    atype = asset["asset_type"]
    row = {
        "asset_id": aid,
        "year": BASE_YEAR,
        "occupancy_rate": 0.0,
        "vacancy_rate": 1.0,
        "vacancy_duration_months": None,
        "footfall_daily": 0,
        "utilisation_rate": None,
        "rental_income_rm": 0.0,
        "energy_kwh": None,
        "metric_source": "observed",
        "model_version": "0.4.0",
    }

    completion = asset.get("completion_year")
    if completion:
        try:
            years_vacant = max(1, BASE_YEAR - int(completion))
        except (TypeError, ValueError):
            years_vacant = 1
    else:
        years_vacant = 1

    row["vacancy_duration_months"] = years_vacant * 12
    return row


def _derive_metrics_for_shoplot(asset, aid, is_vacant):
    """
    Metrics for a converted shoplot.

    Half are vacant — the shoplot overhang state that PLANMalaysia
    reports for new townships, where shoplot sits idle 2-5 years
    before a tenant fills it. Half are leased to small businesses.
    The 50/50 split reproduces the real distribution of delivered
    shoplot in Elmina- and Bukit Jelutong-style phases.
    """
    if is_vacant:
        return {
            "asset_id": aid,
            "year": BASE_YEAR,
            "occupancy_rate": 0.0,
            "vacancy_rate": 1.0,
            "vacancy_duration_months": seeded_int(f"{aid}-vacdur", 24, 60),
            "footfall_daily": 0,
            "utilisation_rate": None,
            "rental_income_rm": 0.0,
            "energy_kwh": None,
            "metric_source": "observed",
            "model_version": "0.4.0",
        }

    occ = seeded_uniform(f"{aid}-occ", 0.55, 0.85)
    return {
        "asset_id": aid,
        "year": BASE_YEAR,
        "occupancy_rate": round(occ, 3),
        "vacancy_rate": round(1 - occ, 3),
        "vacancy_duration_months": seeded_int(f"{aid}-vacdur", 0, 6),
        "footfall_daily": seeded_int(f"{aid}-footfall", 100, 400),
        "utilisation_rate": None,
        "rental_income_rm": seeded_int(f"{aid}-rental", 200_000, 800_000),
        "energy_kwh": None,
        "metric_source": "observed",
        "model_version": "0.4.0",
    }


def derive_metrics_row(asset: dict, demo_role: str, is_unsold: bool = False) -> dict:

    if is_unsold:
        return _derive_metrics_for_unsold(asset, asset["asset_id"])

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

    Windows often holds a transient lock on the output file (QGIS
    preview, Explorer thumbnail, antivirus scan). The write is
    retried up to 5 times with a short sleep, then falls back to
    writing to a temp file and renaming.
    """
    import time as _time
    import os as _os

    path = PROCESSED_GEOM_DIR / f"{name}{SUFFIX}.geojson"
    out = gdf.to_crs(DISPLAY_CRS).copy()

    drop = [c for c in out.columns if c.startswith("_")]
    if drop:
        out = out.drop(columns=drop)
    out = out.reset_index(drop=True)

    last_err = None
    for attempt in range(5):
        try:
            out.to_file(path, driver="GeoJSON")
            print(f"  wrote {path.name}  ({len(out)} features)")
            return
        except PermissionError as e:
            last_err = e
            if attempt < 4:
                print(f"  [retry {attempt + 1}/4] {path.name} locked, "
                      f"retrying in 2s...")
                _time.sleep(2.0)
            continue

    try:
        tmp_path = path.with_suffix(".tmp.geojson")
        out.to_file(tmp_path, driver="GeoJSON")
        if path.exists():
            try:
                _os.remove(path)
            except PermissionError:
                pass
        _os.replace(tmp_path, path)
        print(f"  wrote {path.name} via temp rename  "
              f"({len(out)} features)")
        return
    except Exception:
        pass

    raise PermissionError(
        f"Cannot write {path}: file is locked by another process. "
        f"Close any QGIS / Explorer windows that show this file, "
        f"then retry. Last error: {last_err}"
    )


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

    # Phase 15d — evict buildings from 3 parcels to produce
    # naturally-shaped undeveloped plots. Runs BEFORE population
    # generation so the population layer excludes the evicted
    # households.
    buildings_p, parcels, n_evicted = _evict_buildings_from_parcels(
        buildings_p, parcels, n=3, min_area_m2=4500.0,
    )

    amenities_p = process_amenities_geometry(amenities, buildings_p)
    population_p = generate_population(buildings_p)

    # Phase 15 — Elmina-style mid-development township. A dozen
    # undeveloped parcels under various stages of planning.
    # Phase 15 — Elmina-style mid-development township. A dozen
    # undeveloped parcels under various stages of planning.
    #
    # These are synthesised from *building gaps* rather than copied
    # from existing parcels. Copying produced overlapping geometries
    # on the 3D map and put "undeveloped" outlines under real
    # buildings.
    undeveloped_mocks = _synthesize_vacant_parcels(
        buildings_p, green_blue,
        n=9,
        start_index=n_evicted,
    )
    if not undeveloped_mocks.empty:
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

    # Phase 15b — convert a row of residential buildings facing a main
    # road into shoplot. Planning basis: PLANMalaysia 1:20-1:30 ratio;
    # current commercial = 24 amenity-derived + 12 converted = 36,
    # ratio 818:36 ≈ 1:23, inside the standard.
    assets_df, shoplot_ids = _convert_residential_to_shoplot(
        assets_df, buildings_p, network, n=12,
    )

    # Phase 15b — mark a small subset of remaining residential as
    # unsold inventory. Down from 120 to 30 to avoid dominating the
    # deadspace list. The shoplot conversion now provides the primary
    # commercial deadspace narrative.
    assets_df, unsold_ids = _mark_unsold_inventory(
        assets_df,
        n_residential=30,
        n_commercial=4,
        exclude_ids=shoplot_ids,
    )

    assets_df = _mark_developer_held_facilities(assets_df, n=6)

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
        aid = asset["asset_id"]

        if aid in shoplot_ids:
            # Deterministic: ~half the converted shoplot are vacant.
            # This reproduces the overhang state of newly delivered
            # shoplot in a mid-development township.
            is_vacant = seeded_uniform(f"{aid}-shoplot-vac", 0.0, 1.0) < 0.5
            metric_rows.append(
                _derive_metrics_for_shoplot(asset.to_dict(), aid, is_vacant)
            )
            continue

        role = "healthy"
        if aid == anchor_deadspace:
            role = "deadspace"
        elif aid == anchor_facility:
            role = "underperforming"
        is_unsold = aid in unsold_ids
        metric_rows.append(
            derive_metrics_row(asset.to_dict(), role, is_unsold=is_unsold)
        )

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
    # Phase 15 — Elmina-style phased delivery. Undeveloped parcels
    # are assigned to delivery phases spread across 2026-2035.
    project_rows = []
    _phase_schedule = [
        (2027, 2029), (2027, 2030), (2028, 2030),
        (2028, 2031), (2029, 2032), (2030, 2033),
        (2031, 2034), (2032, 2035),
    ]
    for i, (_, asset) in enumerate(undeveloped.iterrows()):
        if i >= len(_phase_schedule):
            break
        start_y, delivery_y = _phase_schedule[i]
        project_rows.append({
            "project_id": f"PRJ-{i + 1:02d}",
            "parcel_id": asset["parcel_id"],
            "asset_id": None,
            "project_name": f"Phase {i + 3} on {asset['asset_id']}",
            "project_status": "proposed",
            "planned_start_year": start_y,
            "planned_delivery_year": delivery_y,
            "gfa_m2": 8000 + i * 500,
            "units": 60 + i * 5,
            "land_use": "residential",
            "capex_rm": 2_500_000 + i * 200_000,
            "scenario_dependency": "current_plan",
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