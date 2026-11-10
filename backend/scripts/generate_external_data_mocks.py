"""Generate schema-faithful Google Places and Kido/LBS mock feeds.

The generated values are synthetic and deterministic. On the initial upgrade,
pass the pre-gate asset_metrics.csv with --occupancy-reference so external
signals reflect the same trajectory before sold-asset occupancy is withheld.
On later runs, the latest Google snapshots provide a public-safe occupancy
reference for advisory assets.

Run from the repository root or backend folder:
    python backend/scripts/generate_external_data_mocks.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import geopandas as gpd
import pandas as pd
import yaml
from shapely.geometry import Point, box

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.derived.traffic import estimate_osm_traffic_vpd  # noqa: E402

with (BACKEND_DIR / "configs" / "paths.yml").open(encoding="utf-8") as f:
    PATHS = yaml.safe_load(f)
with (BACKEND_DIR / "configs" / "taxonomy.yml").open(encoding="utf-8") as f:
    TAXONOMY = yaml.safe_load(f)
with (BACKEND_DIR / "configs" / "google_places_type_mapping.yml").open(encoding="utf-8") as f:
    TYPE_MAPPING = yaml.safe_load(f)

BASE = REPO_ROOT / PATHS["base"]
GRID_SIZE_M = 100
GRID_CRS = "EPSG:32647"
DISPLAY_CRS = "EPSG:4326"
SNAPSHOT_DATES = [date(2026, month, day) for month, day in ((1, 15), (4, 15), (7, 15), (10, 15))]
WEEK_DATES = [date(2026, 1, 7) + timedelta(days=7 * i) for i in range(52)]


CONSUMER_FACING_SUBTYPES = frozenset({
    "restaurant", "cafe", "kopitiam", "f_and_b", "convenience_retail",
    "supermarket", "medical_retail", "services", "showroom", "entertainment",
})

GOOGLE_PLACES_SUBTYPE_TEMPLATES: dict[str, dict] = {
    "restaurant": {
        "types": ["restaurant", "food", "point_of_interest"], "hours_open": 11, "hours_close": 22,
        "rating_range": (3.5, 4.6), "rating_count_range": (100, 800), "name_suffix": "Restoran",
    },
    "cafe": {
        "types": ["cafe", "food", "point_of_interest"], "hours_open": 7, "hours_close": 19,
        "rating_range": (3.8, 4.7), "rating_count_range": (20, 300), "name_suffix": "Coffee",
    },
    "kopitiam": {
        "types": ["cafe", "coffee_shop", "point_of_interest"], "hours_open": 6, "hours_close": 15,
        "rating_range": (3.5, 4.3), "rating_count_range": (10, 150), "name_suffix": "Kedai Kopi",
    },
    "f_and_b": {
        "types": ["meal_takeaway", "food", "point_of_interest"], "hours_open": 10, "hours_close": 22,
        "rating_range": (3.4, 4.4), "rating_count_range": (30, 400), "name_suffix": "Kitchen",
    },
    "convenience_retail": {
        "types": ["convenience_store", "food", "store"], "hours_open": 7, "hours_close": 23,
        "rating_range": (3.6, 4.4), "rating_count_range": (20, 200), "name_suffix": "Speedmart",
    },
    "supermarket": {
        "types": ["supermarket", "grocery_store", "food"], "hours_open": 8, "hours_close": 22,
        "rating_range": (3.7, 4.5), "rating_count_range": (500, 3000), "name_suffix": "Supermarket",
    },
    "medical_retail": {
        "types": ["pharmacy", "health", "point_of_interest"], "hours_open": 9, "hours_close": 21,
        "rating_range": (3.8, 4.6), "rating_count_range": (30, 200), "name_suffix": "Farmasi",
    },
    "services": {
        "types": ["store", "business", "point_of_interest"], "hours_open": 9, "hours_close": 18,
        "rating_range": (3.5, 4.3), "rating_count_range": (20, 200), "name_suffix": "Services",
    },
    "showroom": {
        "types": ["car_dealer", "store", "point_of_interest"], "hours_open": 10, "hours_close": 19,
        "rating_range": (3.8, 4.5), "rating_count_range": (30, 250), "name_suffix": "Auto",
    },
    "entertainment": {
        "types": ["movie_theater", "point_of_interest"], "hours_open": 12, "hours_close": 23,
        "rating_range": (3.5, 4.4), "rating_count_range": (100, 800), "name_suffix": "Entertainment",
    },
}

SUBTYPE_HOUR_TEMPLATES: dict[str, list[float]] = {
    "office":             [0, 0, 0, 0, 0, 0, 1, 4, 8, 7, 6, 6, 7, 6, 6, 6, 6, 8, 4, 2, 1, 0, 0, 0],
    "f_and_b":            [0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 2, 5, 8, 6, 3, 2, 3, 6, 9, 7, 5, 2, 1, 0],
    "restaurant":         [0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 4, 7, 5, 3, 2, 3, 5, 9, 8, 5, 2, 1, 0],
    "cafe":               [0, 0, 0, 0, 0, 0, 1, 3, 6, 7, 6, 4, 3, 2, 3, 3, 3, 2, 1, 1, 0, 0, 0, 0],
    "kopitiam":           [0, 0, 0, 0, 0, 1, 4, 8, 9, 6, 4, 3, 3, 2, 2, 2, 2, 2, 1, 0, 0, 0, 0, 0],
    "supermarket":        [0, 0, 0, 0, 0, 0, 0, 1, 2, 4, 5, 4, 3, 2, 2, 2, 3, 5, 7, 6, 4, 2, 1, 0],
    "convenience_retail": [0, 0, 0, 0, 0, 0, 1, 3, 4, 4, 3, 3, 2, 2, 2, 2, 2, 3, 4, 3, 2, 1, 0, 0],
    "medical_retail":     [0, 0, 0, 0, 0, 0, 0, 1, 2, 4, 5, 4, 3, 2, 2, 3, 4, 3, 2, 1, 0, 0, 0, 0],
    "residential":        [8, 7, 5, 4, 3, 4, 5, 7, 6, 4, 3, 3, 3, 3, 4, 5, 7, 9, 9, 8, 7, 7, 7, 8],
}

SUBTYPE_DWELL_MINUTES: dict[str, tuple[float, float]] = {
    "office":             (360, 540),
    "supermarket":        (15, 30),
    "cafe":               (25, 60),
    "restaurant":         (45, 90),
    "kopitiam":           (15, 35),
    "convenience_retail": (5, 15),
    "f_and_b":            (20, 50),
    "medical_retail":     (15, 45),
    "services":           (10, 30),
    "showroom":           (20, 60),
    "entertainment":      (90, 180),
    "residential":        (480, 720),
}

GOOGLE_COLUMNS = [
    "snapshot_date", "place_id", "asset_id", "display_name", "business_status",
    "rating", "user_rating_count", "types_json", "regular_opening_hours_json",
    "location_lat", "location_lng", "match_confidence",
]
KIDO_COLUMNS = [
    "grid_id", "grid_lat", "grid_lng", "date", "unique_users", "total_visits",
    "avg_dwell_time_minutes", "hourly_visitors_json", "age_0_14_ratio",
    "age_15_64_ratio", "age_65_plus_ratio", "socioeconomic_class_a_ratio",
    "socioeconomic_class_bc_ratio", "socioeconomic_class_de_ratio",
    "od_inbound_trips", "od_outbound_trips", "vehicle_flow_vpd",
]

KIDO_POI_COLUMNS = [
    "poi_id", "asset_id", "grid_id", "date", "unique_visitors", "total_visits",
    "avg_dwell_time_minutes",
]

# D-19: Kido-style POI analytics (visitors per shop polygon). Typical
# visit length (minutes) and daily opening hours per subtype; shared with
# ingest_external_data.py so its LBS occupancy proxy uses the same scale.
POI_DWELL_MINUTES = {
    "kopitiam": 45, "cafe": 50, "restaurant": 70, "f_and_b": 50,
    "convenience_retail": 12, "supermarket": 30, "medical_retail": 15,
    "services": 35, "office": 420,
}
POI_OPEN_HOURS = {"office": 9}
DEFAULT_POI_DWELL = 30
DEFAULT_POI_OPEN_HOURS = 12
# Average share of an occupied shop's seats / floor capacity in use over
# its opening hours (peaks at lunch/dinner, near-empty mid-afternoon).
POI_AVG_UTILISATION = 0.35

# Different subtypes have different resilience against overall vacancy.
# Higher stress = more likely to close when the asset struggles.
_SUBTYPE_VACANCY_STRESS = {
    "office": 1.5,          # Offices empty out fastest
    "showroom": 1.4,
    "services": 1.2,
    "retail": 1.1,
    "entertainment": 1.1,
    "f_and_b": 0.9,
    "restaurant": 0.9,
    "medical_retail": 0.6,  # Medical/dental survives longer
    "kopitiam": 0.4,        # Local coffee shops almost never die
    "supermarket": 0.2,     # Anchors stay open
}


def poi_capacity(asset) -> float:
    """People an asset can hold at once (assets.csv capacity, else area/15)."""
    cap = getattr(asset, "capacity", None) if not isinstance(asset, dict) else asset.get("capacity")
    try:
        cap = float(cap)
    except (TypeError, ValueError):
        cap = float("nan")
    if not math.isfinite(cap) or cap <= 0:
        area = getattr(asset, "lettable_area_m2", None) if not isinstance(asset, dict) else asset.get("lettable_area_m2")
        try:
            cap = float(area) / 15.0
        except (TypeError, ValueError):
            cap = 1.0
    return max(1.0, cap)


def poi_profile(subtype) -> tuple[float, float]:
    """(typical dwell minutes, open hours per day) for a subtype."""
    st = str(subtype or "")
    return (
        float(POI_DWELL_MINUTES.get(st, DEFAULT_POI_DWELL)),
        float(POI_OPEN_HOURS.get(st, DEFAULT_POI_OPEN_HOURS)),
    )


def poi_expected_visitors(asset, occupancy: float) -> float:
    """Expected daily visitors = people inside on average x turnovers/day."""
    dwell, hours = poi_profile(getattr(asset, "subtype", None))
    occupancy = max(0.0, min(1.0, float(occupancy)))
    return poi_capacity(asset) * occupancy * POI_AVG_UTILISATION * hours * 60.0 / dwell


def _build_kido_poi(assets: pd.DataFrame, occ: dict[str, float], asset_grid: dict) -> list[dict]:
    """Weekly visitor counts per sold / shared commercial asset.

    Visitors follow the asset's own occupancy (busy shop -> many visitors)
    with realistic noise: a fixed per-asset bias (catchment, frontage),
    week-to-week variation, and a small GPS-noise floor so an empty shop
    still records a handful of passers-by.
    """
    rows = []
    target = assets[
        assets["asset_type"].eq("commercial")
        & assets["authority"].isin(["advisory", "shared"])
    ]
    for asset in target.itertuples(index=False):
        aid = str(asset.asset_id)
        expected = poi_expected_visitors(asset, occ.get(aid, 0.5))
        dwell_base, _ = poi_profile(getattr(asset, "subtype", None))
        # Per-asset bias: phone-panel sampling, staff and delivery riders
        # counted as visitors, polygon spillover from the shop next door.
        bias = _uniform(f"{aid}-poi-bias", 0.70, 1.35)
        # Spillover from a busy shared corridor / car park (in visitors/day).
        spill = poi_capacity(asset) * _uniform(f"{aid}-poi-spill", 0.0, 0.8)
        for sample_day in WEEK_DATES:
            weekly = _uniform(f"{aid}-{sample_day}-poi-week", 0.85, 1.15)
            floor = spill + _uniform(f"{aid}-{sample_day}-poi-floor", 2.0, 6.0)
            visitors = max(1, int(round(expected * bias * weekly + floor)))
            repeat = _uniform(f"{aid}-{sample_day}-poi-repeat", 1.05, 1.25)
            dwell = dwell_base * _uniform(f"{aid}-{sample_day}-poi-dwell", 0.90, 1.10)
            rows.append({
                "poi_id": f"POI-{aid}",
                "asset_id": aid,
                "grid_id": asset_grid.get(aid),
                "date": sample_day.isoformat(),
                "unique_visitors": visitors,
                "total_visits": max(visitors, int(round(visitors * repeat))),
                "avg_dwell_time_minutes": round(dwell, 1),
            })
    return rows


def _unit_uniform(key: str) -> float:
    raw = hashlib.sha256(key.encode("utf-8")).digest()[:8]
    return int.from_bytes(raw, "big") / (2**64 - 1)


def _uniform(key: str, low: float, high: float) -> float:
    return low + (high - low) * _unit_uniform(key)


def _integer(key: str, low: int, high: int) -> int:
    return low + int(_unit_uniform(key) * (high - low + 1))


def _place_id(key: str) -> str:
    # Google documents Place IDs as opaque strings; this recognizable
    # synthetic prefix is not a real or resolvable Place ID.
    return "ChIJ" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:24]


def _read_layer(relative_path: str) -> gpd.GeoDataFrame:
    path = BASE / relative_path
    if not path.exists():
        return gpd.GeoDataFrame(geometry=[], crs=DISPLAY_CRS)
    layer = gpd.read_file(path)
    if layer.crs is None:
        layer = layer.set_crs(DISPLAY_CRS)
    return layer


def _parse_unit_mix(raw, unit_count) -> list[tuple[str, int]]:
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and parsed:
                values = []
                for subtype, info in parsed.items():
                    count = info.get("count", 1) if isinstance(info, dict) else 1
                    values.append((str(subtype), max(1, int(float(count)))))
                return values
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    subtype = str(unit_count[0]) if isinstance(unit_count, tuple) else "other_commercial"
    count_value = unit_count[1] if isinstance(unit_count, tuple) else unit_count
    try:
        count = max(1, int(float(count_value)))
    except (TypeError, ValueError):
        count = 1
    return [(subtype, count)]


def _unit_mix_for_asset(row) -> list[tuple[str, int]]:
    return _parse_unit_mix(row.get("unit_mix_json"), (row.get("subtype"), row.get("unit_count", 1)))


def _unit_total(row) -> int:
    return sum(count for _, count in _unit_mix_for_asset(row))


def _load_existing_google(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=GOOGLE_COLUMNS)
    try:
        return pd.read_csv(path)
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame(columns=GOOGLE_COLUMNS)


def _occupancy_reference(assets: pd.DataFrame, metrics_path: Path, google_path: Path) -> dict[str, float]:
    values: dict[str, float] = {}
    if metrics_path.exists():
        try:
            metrics = pd.read_csv(metrics_path)
            if {"asset_id", "occupancy_rate"}.issubset(metrics.columns):
                metrics["occupancy_rate"] = pd.to_numeric(metrics["occupancy_rate"], errors="coerce")
                metrics = metrics.dropna(subset=["occupancy_rate"])
                if not metrics.empty:
                    metrics = metrics.sort_values("year").drop_duplicates("asset_id", keep="last")
                    values.update({str(r.asset_id): float(r.occupancy_rate) for r in metrics.itertuples()})
        except (pd.errors.EmptyDataError, pd.errors.ParserError, KeyError):
            pass

    google = _load_existing_google(google_path)
    if not google.empty and {"asset_id", "business_status"}.issubset(google.columns):
        latest_date = google["snapshot_date"].max()
        latest = google[google["snapshot_date"] == latest_date]
        presence = latest.groupby("asset_id")["business_status"].apply(
            lambda col: float((col == "OPERATIONAL").mean())
        )
        for aid, ratio in presence.items():
            values.setdefault(str(aid), float(ratio))

    for row in assets.itertuples(index=False):
        aid = str(getattr(row, "asset_id"))
        if aid not in values:
            subtype = str(getattr(row, "subtype", "other_commercial"))
            benchmark = float(TAXONOMY.get("subtypes", {}).get(subtype, {}).get("occupancy_benchmark", 0.70))
            values[aid] = max(0.0, min(1.0, benchmark + _uniform(f"{aid}-fallback-occ", -0.18, 0.12)))
    return values


def _asset_geometry_points(assets: pd.DataFrame, buildings: gpd.GeoDataFrame, parcels: gpd.GeoDataFrame):
    buildings_by_id = {}
    if not buildings.empty and "building_id" in buildings.columns:
        buildings_by_id = {
            str(r.get("building_id")): r.geometry
            for _, r in buildings.iterrows()
            if r.get("building_id") is not None and r.geometry is not None and not r.geometry.is_empty
        }
    parcels_by_id = {}
    if not parcels.empty and "parcel_id" in parcels.columns:
        parcels_by_id = {
            str(r.get("parcel_id")): r.geometry
            for _, r in parcels.iterrows()
            if r.get("parcel_id") is not None and r.geometry is not None and not r.geometry.is_empty
        }

    points = {}
    match_quality = {}
    for _, row in assets.iterrows():
        aid = str(row["asset_id"])
        geom = buildings_by_id.get(str(row.get("building_id"))) if pd.notna(row.get("building_id")) else None
        quality = "exact_containment"
        if geom is None:
            geom = parcels_by_id.get(str(row.get("parcel_id"))) if pd.notna(row.get("parcel_id")) else None
            quality = "nearest_parcel" if geom is not None else "no_match"
        if geom is not None and not geom.is_empty:
            point = geom.representative_point() if geom.geom_type in {"Polygon", "MultiPolygon"} else geom
            points[aid] = point
            match_quality[aid] = quality
        else:
            points[aid] = None
            match_quality[aid] = "no_match"
    return points, match_quality


def _grid_id(x: float, y: float) -> str:
    ix = math.floor(x / GRID_SIZE_M)
    iy = math.floor(y / GRID_SIZE_M)
    return f"G-{ix:04d}-{iy:04d}"


def _get_subtype_types(subtype: str) -> list[str]:
    choices = {
        "convenience_retail": ["convenience_store", "store", "point_of_interest"],
        "supermarket": ["supermarket", "grocery_store", "food"],
        "restaurant": ["restaurant", "food", "point_of_interest"],
        "f_and_b": ["cafe", "food", "point_of_interest"],
        "kopitiam": ["restaurant", "food", "point_of_interest"],
        "cafe": ["cafe", "food", "point_of_interest"],
        "medical_retail": ["pharmacy", "health", "point_of_interest"],
        "office": ["corporate_office", "business_center", "point_of_interest"],
        "services": ["store", "business", "point_of_interest"],
        "showroom": ["car_dealer", "store", "point_of_interest"],
        "entertainment": ["movie_theater", "point_of_interest"],
        "other_commercial": ["store", "point_of_interest"],
    }
    result = choices.get(subtype, choices["other_commercial"])
    # Keep only names recognized by the configured type map, preserving the
    # generic Places response tags used in the published response schema.
    known = set(TYPE_MAPPING.get("direct_match", {})) | set(TYPE_MAPPING.get("category_fallback", {}))
    return [name for name in result if name in known] or ["point_of_interest"]


def _opening_hours(subtype: str) -> str:
    if subtype == "office":
        open_hour, close_hour = 9, 18
    elif subtype in {"restaurant", "f_and_b", "kopitiam", "cafe", "entertainment"}:
        open_hour, close_hour = 10, 22
    else:
        open_hour, close_hour = 9, 21
    periods = [
        {"open": {"day": day, "hour": open_hour}, "close": {"day": day, "hour": close_hour}}
        for day in range(7)
    ]
    return json.dumps({"periods": periods}, separators=(",", ":"))


def _build_google_rows(assets: pd.DataFrame, occ: dict[str, float],
                       points: dict, match_quality: dict) -> list[dict]:
    rows = []
    target = assets[
        assets["asset_type"].eq("commercial")
        & assets["authority"].isin(["advisory", "shared"])
    ]
    for _, asset in target.iterrows():
        aid = str(asset["asset_id"])
        occupancy = max(0.0, min(1.0, occ.get(aid, 0.5)))
        unit_mix = _unit_mix_for_asset(asset)
        unit_specs = []
        global_unit_idx = 1
        for subtype, count in unit_mix:
            for _ in range(count):
                unit_specs.append((subtype, global_unit_idx))
                global_unit_idx += 1
        if not unit_specs:
            continue

        point = points.get(aid)
        projected_point = None
        if point is not None:
            projected_point = gpd.GeoSeries([point], crs=DISPLAY_CRS).to_crs(GRID_CRS).iloc[0]

        for quarter, snapshot_day in enumerate(SNAPSHOT_DATES):
            for subtype, unit_no in unit_specs:
                template = GOOGLE_PLACES_SUBTYPE_TEMPLATES.get(subtype, {})
                if not template:
                    continue

                chance = _unit_uniform(f"{aid}-{unit_no}-{snapshot_day}-status")
                stress = _SUBTYPE_VACANCY_STRESS.get(subtype, 1.0)
                adjusted_occ = max(0.0, min(1.0, occupancy / stress))
                adjusted_occ += _uniform(f"{aid}-{unit_no}-{subtype}-occ-noise", -0.1, 0.1)
                adjusted_occ = max(0.0, min(1.0, adjusted_occ))

                if adjusted_occ > 0.70:
                    status = "OPERATIONAL"
                elif adjusted_occ >= 0.30:
                    status = "OPERATIONAL" if chance < 0.60 else "CLOSED_TEMPORARILY"
                else:
                    status = "OPERATIONAL" if chance < 0.20 else "CLOSED_PERMANENTLY"

                turnover_prob = min(0.45, 0.02 + 0.40 * (1.0 - occupancy))
                place_key = f"{aid}-{unit_no}"
                if quarter > 0 and _unit_uniform(f"{place_key}-turnover-{quarter}") < turnover_prob:
                    place_key += f"-replacement-{quarter}"
                pid = _place_id(place_key)

                r_lo, r_hi = template["rating_range"]
                c_lo, c_hi = template["rating_count_range"]

                if adjusted_occ > 0.70:
                    rating = _uniform(f"{pid}-{snapshot_day}-rating", r_lo, r_hi)
                    rating_count = _integer(f"{pid}-{snapshot_day}-reviews", c_lo, c_hi)
                elif adjusted_occ >= 0.30:
                    mid = r_lo + (r_hi - r_lo) * 0.3
                    rating = _uniform(f"{pid}-{snapshot_day}-rating", r_lo, mid + 0.4)
                    count_lo = max(1, int(c_lo * 0.4))
                    count_hi = max(count_lo + 1, int(c_hi * 0.5))
                    rating_count = _integer(f"{pid}-{snapshot_day}-reviews", count_lo, count_hi)
                else:
                    low_hi = r_lo + (r_hi - r_lo) * 0.3
                    rating = _uniform(f"{pid}-{snapshot_day}-rating", max(1.0, r_lo - 0.5), low_hi)
                    count_lo = 1
                    count_hi = max(5, int(c_lo * 0.5))
                    rating_count = _integer(f"{pid}-{snapshot_day}-reviews", count_lo, count_hi)

                suffix = template.get("name_suffix", "Business")
                display_name = f"{suffix} {aid} #{unit_no}"

                loc = projected_point
                if loc is not None:
                    loc = Point(loc.x + _uniform(f"{pid}-dx", -3.0, 3.0), loc.y + _uniform(f"{pid}-dy", -3.0, 3.0))
                    latlng = gpd.GeoSeries([loc], crs=GRID_CRS).to_crs(DISPLAY_CRS).iloc[0]
                    lat, lng = float(latlng.y), float(latlng.x)
                else:
                    lat, lng = None, None

                rows.append({
                    "snapshot_date": snapshot_day.isoformat(),
                    "place_id": pid,
                    "asset_id": aid,
                    "display_name": display_name,
                    "business_status": status,
                    "rating": round(rating, 1),
                    "user_rating_count": rating_count,
                    "types_json": json.dumps(_get_subtype_types(subtype), separators=(",", ":")),
                    "regular_opening_hours_json": _opening_hours(subtype),
                    "location_lat": lat,
                    "location_lng": lng,
                    "match_confidence": match_quality.get(aid, "no_match"),
                })
    return rows


def _normalized_ratios(vals: list[float], fallback: list[float]) -> list[float]:
    total = sum(max(0.0, v) for v in vals)
    if total <= 0:
        vals = fallback
        total = sum(vals)
    rounded = [round(max(0.0, v) / total, 4) for v in vals]
    rounded[-1] = round(1.0 - sum(rounded[:-1]), 4)
    return rounded


def _hourly_counts(total: int, key: str, composition: dict[str, float]) -> list[int]:
    normalized: dict[str, list[float]] = {}
    for subtype, template in SUBTYPE_HOUR_TEMPLATES.items():
        s = sum(template)
        if s <= 0:
            continue
        normalized[subtype] = [v / s * 24 for v in template]

    weights = [0.0] * 24
    total_share = sum(composition.values()) if composition else 0.0
    if total_share <= 0:
        fallback = normalized.get("residential") or normalized.get("convenience_retail")
        if fallback is not None:
            weights = list(fallback)
    else:
        for subtype, share in composition.items():
            template = normalized.get(subtype)
            if template is None:
                continue
            w = share / total_share
            for h in range(24):
                weights[h] += w * template[h]

    for h in range(24):
        weights[h] *= _uniform(f"{key}-hour-{h}", 0.9, 1.1)

    total_weight = sum(weights)
    if total_weight <= 0:
        return [0] * 24
    scale = total / total_weight
    values = [int(math.floor(w * scale)) for w in weights]
    for i in range(total - sum(values)):
        values[i % 24] += 1
    return values


def _build_grid_and_kido(assets: pd.DataFrame, occ: dict[str, float], population: gpd.GeoDataFrame,
                         asset_points: dict, network: gpd.GeoDataFrame):
    population_proj = population.to_crs(GRID_CRS) if not population.empty else population
    network_proj = network.to_crs(GRID_CRS) if not network.empty else network
    asset_grid: dict[str, str] = {}
    cells: dict[str, dict] = {}

    for aid, point in asset_points.items():
        if point is None:
            continue
        p = gpd.GeoSeries([point], crs=DISPLAY_CRS).to_crs(GRID_CRS).iloc[0]
        gid = _grid_id(p.x, p.y)
        asset_grid[aid] = gid
        cells.setdefault(gid, {"assets": [], "population": []})["assets"].append(aid)

    if not population_proj.empty:
        for _, row in population_proj.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            gid = _grid_id(geom.x, geom.y)
            cells.setdefault(gid, {"assets": [], "population": []})["population"].append(row)

    asset_by_id = {str(row.asset_id): row for row in assets.itertuples(index=False)}
    for gid, cell in cells.items():
        ix, iy = [int(part) for part in gid.split("-")[1:]]
        geom = box(ix * GRID_SIZE_M, iy * GRID_SIZE_M, (ix + 1) * GRID_SIZE_M, (iy + 1) * GRID_SIZE_M)
        center = geom.centroid
        center_ll = gpd.GeoSeries([center], crs=GRID_CRS).to_crs(DISPLAY_CRS).iloc[0]

        total_pop = sum(float(r.get("total_population", 0) or 0) for r in cell["population"])
        ages = [
            sum(float(r.get(c, 0) or 0) for r in cell["population"])
            for c in ("age_0_14", "age_15_64", "age_65_plus")
        ]
        age_ratios = _normalized_ratios(ages, [0.20, 0.70, 0.10])

        cell_assets = [asset_by_id[aid] for aid in cell["assets"] if aid in asset_by_id]
        commercial = [a for a in cell_assets if getattr(a, "asset_type", None) == "commercial"]
        
        composition: dict[str, float] = {}
        for asset in commercial:
            subtype = str(getattr(asset, "subtype", "other_commercial"))
            area = max(0.0, float(getattr(asset, "lettable_area_m2", 0) or 0))
            if area > 0:
                composition[subtype] = composition.get(subtype, 0.0) + area
        
        occupied_capacity = sum(
            max(1.0, float(getattr(a, "capacity", 1) or 1)) * occ.get(str(getattr(a, "asset_id")), 0.5)
            for a in commercial
        )
        density = len(commercial) / max(1, len(cell_assets))

        cell["geometry"] = geom
        cell["grid_lat"] = float(center_ll.y)
        cell["grid_lng"] = float(center_ll.x)
        cell["population"] = total_pop
        cell["adult_population"] = ages[1] if ages[1] else total_pop * 0.67
        cell["age_ratios"] = age_ratios
        cell["assets"] = cell["assets"]
        cell["commercial_assets"] = commercial
        cell["occupied_capacity"] = occupied_capacity
        cell["commercial_density"] = density
        cell["composition"] = composition
        cell["population_users"] = max(0.0, cell["adult_population"] * _uniform(f"{gid}-penetration", 0.35, 0.45))

    # D-19: a cell's users = residents seen in the cell + the visitors of
    # the shops inside it. Shop visitors come from the same expected-visitor
    # model as the POI feed, so the grid and POI products agree.
    for gid, cell in cells.items():
        shop_visitors = sum(
            poi_expected_visitors(a, occ.get(str(getattr(a, "asset_id")), 0.5))
            for a in cell["commercial_assets"]
        )
        users = cell["population_users"] + shop_visitors
        cell["unique_users"] = max(1, int(round(users)))

    kido_rows = []
    for gid, cell in sorted(cells.items()):
        road_vpd = estimate_osm_traffic_vpd(network_proj, cell["geometry"], GRID_SIZE_M**2)
        for sample_day in WEEK_DATES:
            seasonal = _uniform(f"{gid}-{sample_day}-season", 0.90, 1.10)
            unique_users = max(1, int(round(cell["unique_users"] * seasonal)))
            visit_multiplier = (1.2 + 2.5 * cell["commercial_density"]) * _uniform(
                f"{gid}-{sample_day}-visits", 0.92, 1.08
            )
            total_visits = max(unique_users, int(round(unique_users * visit_multiplier)))

            if cell["composition"]:
                total_share = sum(cell["composition"].values())
                weighted_dwell = 0.0
                for subtype, share in cell["composition"].items():
                    lo, hi = SUBTYPE_DWELL_MINUTES.get(subtype, (10, 30))
                    weighted_dwell += (share / total_share) * ((lo + hi) / 2)
                dwell = weighted_dwell * _uniform(f"{gid}-{sample_day}-dwell", 0.9, 1.1)
            else:
                lo, hi = SUBTYPE_DWELL_MINUTES["residential"]
                dwell = _uniform(f"{gid}-{sample_day}-dwell", lo, hi)

            age = cell["age_ratios"]
            # The current generated population layer has age bands but no
            # socioeconomic field. SES bands are therefore explicit,
            # deterministic assumptions rather than inferred observations.
            ses = _normalized_ratios([
                _uniform(f"{gid}-ses-a", 0.12, 0.20),
                _uniform(f"{gid}-ses-bc", 0.50, 0.62),
                _uniform(f"{gid}-ses-de", 0.22, 0.34),
            ], [0.16, 0.56, 0.28])
            inbound_factor = 0.15 + 0.22 * cell["commercial_density"]
            outbound_factor = 0.15 + 0.22 * cell["commercial_density"]
            inbound = int(round(unique_users * inbound_factor * _uniform(f"{gid}-{sample_day}-in", 0.9, 1.1)))
            outbound = int(round(unique_users * outbound_factor * _uniform(f"{gid}-{sample_day}-out", 0.9, 1.1)))
            hourly = _hourly_counts(total_visits, f"{gid}-{sample_day}", cell["composition"])

            kido_rows.append({
                "grid_id": gid,
                "grid_lat": cell["grid_lat"],
                "grid_lng": cell["grid_lng"],
                "date": sample_day.isoformat(),
                "unique_users": unique_users,
                "total_visits": total_visits,
                "avg_dwell_time_minutes": round(dwell, 1),
                "hourly_visitors_json": json.dumps(hourly, separators=(",", ":")),
                "age_0_14_ratio": age[0],
                "age_15_64_ratio": age[1],
                "age_65_plus_ratio": age[2],
                "socioeconomic_class_a_ratio": ses[0],
                "socioeconomic_class_bc_ratio": ses[1],
                "socioeconomic_class_de_ratio": ses[2],
                "od_inbound_trips": inbound,
                "od_outbound_trips": outbound,
                "vehicle_flow_vpd": road_vpd,
            })
    return cells, asset_grid, kido_rows


def generate(occupancy_reference: Path | None = None) -> tuple[int, int]:
    assets_rel = PATHS["business"]["assets"]
    metrics_rel = PATHS["business"]["asset_metrics"]
    mock_dir = BASE / PATHS["external_data"]["mock_directory"]
    mock_dir.mkdir(parents=True, exist_ok=True)
    google_path = BASE / PATHS["external_data"]["google_places_snapshots"]
    # D-18: condition the mocks on the hidden pre-gate occupancy when it
    # exists (sold assets have none in asset_metrics.csv by design).
    truth_path = BASE / PATHS["external_data"]["mock_truth_occupancy"]
    metrics_path = occupancy_reference or (truth_path if truth_path.exists() else BASE / metrics_rel)

    assets = pd.read_csv(BASE / assets_rel)
    if "authority" not in assets.columns:
        raise ValueError("assets.csv must include the authority column")
    occupancy = _occupancy_reference(assets, metrics_path, google_path)
    buildings = _read_layer(PATHS["geometry"]["buildings"])
    parcels = _read_layer(PATHS["geometry"]["parcels"])
    population = _read_layer(PATHS["geometry"]["population"])
    network = _read_layer(PATHS["geometry"]["network"])
    points, quality = _asset_geometry_points(assets, buildings, parcels)

    google_rows = _build_google_rows(assets, occupancy, points, quality)
    pd.DataFrame(google_rows, columns=GOOGLE_COLUMNS).to_csv(google_path, index=False)

    cells, asset_grid, kido_rows = _build_grid_and_kido(
        assets, occupancy, population, points, network
    )
    kido_path = BASE / PATHS["external_data"]["kido_grid"]
    pd.DataFrame(kido_rows, columns=KIDO_COLUMNS).to_csv(kido_path, index=False)
    poi_rows = _build_kido_poi(assets, occupancy, asset_grid)
    poi_path = BASE / PATHS["external_data"]["kido_poi"]
    pd.DataFrame(poi_rows, columns=KIDO_POI_COLUMNS).to_csv(poi_path, index=False)
    print(f"Wrote {google_path} ({len(google_rows)} rows)")
    print(f"Wrote {kido_path} ({len(kido_rows)} rows, {len(cells)} {GRID_SIZE_M}m cells)")
    print(f"Wrote {poi_path} ({len(poi_rows)} rows)")
    return len(google_rows), len(kido_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--occupancy-reference", type=Path,
        help="Optional pre-authority-gate asset_metrics.csv used only to condition mocks.",
    )
    args = parser.parse_args()
    generate(args.occupancy_reference)


if __name__ == "__main__":
    main()
