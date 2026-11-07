"""Transform external mock feeds into business tables consumed by the app.

The API and model code load only the clean tables under business/; they do
not read external_data_mock/ directly.

Run after `generate_external_data_mocks.py` and `fetch_worldpop.py`:
    python backend/scripts/ingest_external_data.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import yaml
from shapely.geometry import box

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.derived.traffic import resolve_traffic_exposure  # noqa: E402
from app.config import load_paths  # noqa: E402
from scripts.generate_external_data_mocks import (  # noqa: E402
    DISPLAY_CRS,
    GRID_CRS,
    GRID_SIZE_M,
    _asset_geometry_points,
    _normalized_ratios,
    _read_layer,
    _unit_total,
)

PATHS = load_paths()
BASE = REPO_ROOT / PATHS["base"]
with (BACKEND_DIR / "configs" / "taxonomy.yml").open(encoding="utf-8") as f:
    TAXONOMY = yaml.safe_load(f)
with (BACKEND_DIR / "configs" / "google_places_type_mapping.yml").open(encoding="utf-8") as f:
    TYPE_MAPPING = yaml.safe_load(f)

# v6.1 — consumer-facing filter and subtype capacity table
CONSUMER_FACING_SUBTYPES = frozenset({
    "restaurant", "cafe", "kopitiam", "f_and_b", "convenience_retail",
    "supermarket", "medical_retail", "services", "showroom", "entertainment",
})


CAPACITY_M2_PER_PERSON = {
    "office":             10.0,
    "supermarket":         5.0,
    "convenience_retail": 12.0,
    "cafe":                3.0,
    "restaurant":          2.5,
    "kopitiam":            2.0,
    "f_and_b":             5.0,
    "medical_retail":     20.0,
    "services":           15.0,
    "showroom":           30.0,
    "entertainment":       2.0,
    "residential":        30.0,
    "_default":           15.0,
}


def _consumer_facing_unit_count(asset_row) -> int:
    """Count consumer-facing units. Excludes office."""
    def _get(key):
        if isinstance(asset_row, dict):
            return asset_row.get(key)
        return getattr(asset_row, key, None)

    raw_mix = _get("unit_mix_json")
    if raw_mix is None or (isinstance(raw_mix, float) and pd.isna(raw_mix)):
        subtype = _get("subtype")
        return 1 if subtype in CONSUMER_FACING_SUBTYPES else 0

    try:
        mix = json.loads(raw_mix) if isinstance(raw_mix, str) else raw_mix
    except (json.JSONDecodeError, TypeError):
        return 0
    if not isinstance(mix, dict):
        return 0

    total = 0
    for subtype, info in mix.items():
        if subtype not in CONSUMER_FACING_SUBTYPES:
            continue
        count = info.get("count", 1) if isinstance(info, dict) else 1
        try:
            total += max(0, int(count))
        except (TypeError, ValueError):
            total += 1
    return total


def _capacity_users(asset_row) -> float:
    """Return the seat / occupancy capacity for an asset by subtype."""
    def _get(key, default=None):
        if isinstance(asset_row, dict):
            return asset_row.get(key, default)
        return getattr(asset_row, key, default)

    subtype = _get("subtype")
    lettable = _get("lettable_area_m2", 0) or 0
    try:
        lettable = float(lettable)
    except (TypeError, ValueError):
        return 1.0
    if lettable <= 0:
        return 1.0
    density = CAPACITY_M2_PER_PERSON.get(subtype, CAPACITY_M2_PER_PERSON["_default"])
    return max(1.0, lettable / density)


def resolve_subtype(types_list: list[str]) -> str:
    """Map a Places type array to a legal project subtype."""
    direct = TYPE_MAPPING.get("direct_match", {})
    fallback = TYPE_MAPPING.get("category_fallback", {})
    priority = {name: idx for idx, name in enumerate(TYPE_MAPPING.get("priority_order", []))}
    direct_hits = [name for name in types_list if name in direct]
    if direct_hits:
        direct_hits.sort(key=lambda name: priority.get(name, len(priority)))
        return direct[direct_hits[0]]
    fallback_hits = [name for name in types_list if name in fallback]
    if fallback_hits:
        fallback_hits.sort(key=lambda name: priority.get(name, len(priority)))
        return fallback[fallback_hits[0]]
    return TYPE_MAPPING.get("fallback_subtype", "other_commercial")


def _read_csv(path: Path, required_columns: set[str]) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path)
    missing = required_columns - set(frame.columns)
    if missing:
        raise ValueError(f"{path.name} is missing columns: {sorted(missing)}")
    return frame


def _parse_types(raw) -> list[str]:
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else []
    except json.JSONDecodeError:
        return []


def _latest_rows_by_asset(google: pd.DataFrame) -> pd.DataFrame:
    google = google.copy()
    google["snapshot_date"] = google["snapshot_date"].astype(str)
    latest_date = google["snapshot_date"].max()
    return google[google["snapshot_date"] == latest_date]


def build_business_presence(assets: pd.DataFrame, google: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "asset_id", "snapshot_date", "unit_mix_unit_count",
        "consumer_facing_unit_count", "operational_place_count",
        "business_presence_ratio", "proxied_occupancy_google",
        "business_vitality_score", "proxied_vacancy_duration",
        "business_turnover_count", "google_place_ids_json",
        "business_subtype_counts_json",
        "tier", "source", "is_mock",
    ]
    if google.empty:
        return pd.DataFrame(columns=columns)

    eligible = assets[
        assets["asset_type"].eq("commercial")
        & assets["authority"].isin(["advisory", "shared"])
    ].copy()
    assets_by_id = {str(row.asset_id): row for row in eligible.itertuples(index=False)}

    all_snapshot_dates = google["snapshot_date"].astype(str)
    current_snapshot = all_snapshot_dates.max()
    latest = google[all_snapshot_dates == current_snapshot]

    raw_vitality = {}
    for aid, rows in latest.groupby("asset_id"):
        score = []
        for row in rows.itertuples(index=False):
            if pd.notna(row.rating) and pd.notna(row.user_rating_count):
                score.append(float(row.rating) * math.log1p(max(0, int(row.user_rating_count))))
        raw_vitality[str(aid)] = sum(score) / len(score) if score else 0.0
    lo = min(raw_vitality.values(), default=0.0)
    hi = max(raw_vitality.values(), default=0.0)

    rows_out = []
    for aid, history in google.groupby("asset_id"):
        aid = str(aid)
        asset = assets_by_id.get(aid)
        if asset is None:
            continue

        asset_dict = asset._asdict()
        # v6.1 — denominator excludes office
        consumer_unit_count = _consumer_facing_unit_count(asset_dict)
        full_unit_count = max(1, _unit_total(pd.Series(asset_dict)))

        if consumer_unit_count == 0:
            # Asset has no consumer-facing units (office-only). Presence
            # ratio is undefined — skip rather than emitting a 0.0 that
            # would be read as "fully vacant".
            continue

        current = latest[latest["asset_id"].astype(str).eq(aid)]
        # Some Google Places rows may point to office (should not happen
        # after v6.1 mock fix, but the ingestion defends against it).
        operational_consumer = current[
            (current["business_status"] == "OPERATIONAL")
        ]
        # Count only one OPERATIONAL place per consumer unit (avoid double
        # counting if a placeholder ever leaked in).
        operational = min(consumer_unit_count, int(operational_consumer["place_id"].nunique()))

        presence_ratio = min(1.0, operational / consumer_unit_count)
        score = raw_vitality.get(aid, 0.0)
        vitality = (score - lo) / (hi - lo) if hi > lo else 0.5

        operational_history = history[history["business_status"] == "OPERATIONAL"]
        if operational_history.empty:
            vacancy_months = None
        else:
            last_open = pd.to_datetime(operational_history["snapshot_date"], errors="coerce").max()
            current_day = pd.to_datetime(current_snapshot)
            vacancy_months = max(0.0, (current_day - last_open).days / 30.4375)
            vacancy_months = round(vacancy_months, 1)

        operational_ids = history.loc[
            history["business_status"].eq("OPERATIONAL"), "place_id"
        ].dropna().astype(str).nunique()
        turnover = max(0, operational_ids - consumer_unit_count)

        place_ids = sorted(current["place_id"].dropna().astype(str).unique())
        subtype_counts: dict[str, int] = {}
        for place in current.itertuples(index=False):
            subtype = resolve_subtype(_parse_types(place.types_json))
            subtype_counts[subtype] = subtype_counts.get(subtype, 0) + 1

        rows_out.append({
            "asset_id": aid,
            "snapshot_date": current_snapshot,
            "unit_mix_unit_count": full_unit_count,
            "consumer_facing_unit_count": consumer_unit_count,
            "operational_place_count": operational,
            "business_presence_ratio": round(presence_ratio, 4),
            "proxied_occupancy_google": round(min(1.0, presence_ratio * 1.15), 4),
            "business_vitality_score": round(vitality, 4),
            "proxied_vacancy_duration": vacancy_months,
            "business_turnover_count": turnover,
            "google_place_ids_json": json.dumps(place_ids, separators=(",", ":")),
            "business_subtype_counts_json": json.dumps(subtype_counts, separators=(",", ":")),
            "tier": "3a",
            "source": "derived_from_google_places_mock",
            "is_mock": True,
        })
    return pd.DataFrame(rows_out, columns=columns)


def _asset_grid_lookup(assets: pd.DataFrame, points: dict) -> dict[str, str]:
    result = {}
    for aid, point in points.items():
        if point is None:
            continue
        projected = gpd.GeoSeries([point], crs=DISPLAY_CRS).to_crs(GRID_CRS).iloc[0]
        result[aid] = f"G-{int(projected.x // GRID_SIZE_M):04d}-{int(projected.y // GRID_SIZE_M):04d}"
    return result


def _parse_hourly(raw) -> list[float]:
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(value, list) and len(value) == 24:
            return [max(0.0, float(v)) for v in value]
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return [0.0] * 24


def _build_grid_network_graph(grid_geom: dict, network_proj) -> dict[str, set[str]]:
    """Estimate reachable neighbour activity through mapped road/path cells.

    A simple grid graph is formed where OSM linework crosses a shared edge
    between adjacent 400m cells. This keeps flow-island signals sensitive to
    mapped network breaks without pretending that straight-line distance is
    walking access.
    """
    adjacency = {gid: set() for gid in grid_geom}
    if network_proj is None or network_proj.empty or not grid_geom:
        return adjacency
    try:
        road_buffer = network_proj.geometry.union_all().buffer(12)
    except Exception:
        return adjacency

    indices = {
        gid: tuple(int(part) for part in gid.split("-")[1:])
        for gid in grid_geom
    }
    for gid, (ix, iy) in indices.items():
        for neighbor in (f"G-{ix + 1:04d}-{iy:04d}", f"G-{ix - 1:04d}-{iy:04d}",
                         f"G-{ix:04d}-{iy + 1:04d}", f"G-{ix:04d}-{iy - 1:04d}"):
            if neighbor not in grid_geom or neighbor <= gid:
                continue
            shared_edge = grid_geom[gid].boundary.intersection(grid_geom[neighbor].boundary)
            if not shared_edge.is_empty and road_buffer.intersects(shared_edge):
                adjacency[gid].add(neighbor)
                adjacency[neighbor].add(gid)
    return adjacency


def _network_reachable_users(grid_id: str, adjacency: dict, grid_mean: dict) -> float:
    if grid_id not in adjacency:
        return 0.0
    distances = {grid_id: 0}
    queue = [grid_id]
    for current in queue:
        hops = distances[current]
        if hops >= 3:
            continue
        for neighbor in adjacency[current]:
            if neighbor not in distances:
                distances[neighbor] = hops + 1
                queue.append(neighbor)

    return sum(
        grid_mean[neighbor]["unique"] / hops
        for neighbor, hops in distances.items()
        if neighbor != grid_id and hops > 0
    )


def build_lbs_metrics(assets: pd.DataFrame, kido: pd.DataFrame,
                      points: dict, network: gpd.GeoDataFrame,
                      business_presence: pd.DataFrame | None = None) -> pd.DataFrame:
    columns = [
        "asset_id", "grid_id", "lbs_unique_users_daily", "grid_unique_users_daily",
        "lbs_dwell_time_minutes", "capacity_users",
        "lbs_visit_frequency_monthly", "lbs_hourly_splits", "lbs_visitor_demographics",
        "proxied_occupancy_lbs", "traffic_exposure_vpd", "traffic_exposure_source",
        "flow_island_ratio", "observed_demand_ratio", "tier", "source", "is_mock",
    ]
    eligible = assets[
        assets["asset_type"].eq("commercial")
        & assets["authority"].isin(["advisory", "shared"])
    ].copy()
    if eligible.empty:
        return pd.DataFrame(columns=columns)

    google_proxy_by_asset = {}
    if business_presence is not None and not business_presence.empty:
        google_proxy_by_asset = dict(zip(
            business_presence["asset_id"].astype(str),
            pd.to_numeric(business_presence["proxied_occupancy_google"], errors="coerce").fillna(0.0),
        ))

    grid_lookup = _asset_grid_lookup(assets, points)
    commercial_area_by_grid: dict[str, float] = {}
    for asset in assets[assets["asset_type"].eq("commercial")].itertuples(index=False):
        gid = grid_lookup.get(str(asset.asset_id))
        if gid:
            try:
                area = max(0.0, float(getattr(asset, "lettable_area_m2", 0) or 0))
            except (TypeError, ValueError):
                area = 0.0
            commercial_area_by_grid[gid] = commercial_area_by_grid.get(gid, 0.0) + area
    kido = kido.copy()
    if not kido.empty:
        kido["date"] = kido["date"].astype(str)
    grid_centers = {}
    grid_mean = {}
    for gid, group in kido.groupby("grid_id"):
        grid_centers[str(gid)] = (float(group["grid_lat"].iloc[0]), float(group["grid_lng"].iloc[0]))
        grid_mean[str(gid)] = {
            "unique": float(pd.to_numeric(group["unique_users"], errors="coerce").fillna(0).mean()),
            "visits": float(pd.to_numeric(group["total_visits"], errors="coerce").fillna(0).mean()),
            "dwell": float(pd.to_numeric(group["avg_dwell_time_minutes"], errors="coerce").fillna(0).mean()),
            "vpd": float(pd.to_numeric(group["vehicle_flow_vpd"], errors="coerce").fillna(0).mean()),
            "age": [float(pd.to_numeric(group[c], errors="coerce").fillna(0).mean()) for c in (
                "age_0_14_ratio", "age_15_64_ratio", "age_65_plus_ratio")],
            "ses": [float(pd.to_numeric(group[c], errors="coerce").fillna(0).mean()) for c in (
                "socioeconomic_class_a_ratio", "socioeconomic_class_bc_ratio",
                "socioeconomic_class_de_ratio")],
            "hourly": [sum(vals) / max(1, len(group)) for vals in zip(*[_parse_hourly(x) for x in group["hourly_visitors_json"]])],
        }

    network_proj = network.to_crs(GRID_CRS) if not network.empty else network
    grid_geom = {}
    for gid in grid_mean:
        ix, iy = [int(part) for part in gid.split("-")[1:]]
        grid_geom[gid] = box(ix * GRID_SIZE_M, iy * GRID_SIZE_M,
                             (ix + 1) * GRID_SIZE_M, (iy + 1) * GRID_SIZE_M)
    grid_adjacency = _build_grid_network_graph(grid_geom, network_proj)

    rows_out = []
    for asset in eligible.itertuples(index=False):
        aid = str(asset.asset_id)
        gid = grid_lookup.get(aid)
        local = grid_mean.get(gid) if gid else None
        if local is None:
            local_users = 0.0
            dwell = 0.0
            monthly_frequency = 0.0
            hourly_split = [0.0] * 24
            ages = [0.20, 0.70, 0.10]
            ses = [0.16, 0.56, 0.28]
            visits = 0.0
            kido_vpd = None
        else:
            local_users = local["unique"]
            dwell = local["dwell"]
            visits = local["visits"]
            monthly_frequency = visits / max(1.0, local_users) * 30.4
            hourly = local["hourly"]
            total_hourly = sum(hourly)
            hourly_split = [round(v / total_hourly, 5) for v in hourly] if total_hourly > 0 else [0.0] * 24
            ages = _normalized_ratios(local["age"], [0.20, 0.70, 0.10])
            ses = _normalized_ratios(local["ses"], [0.16, 0.56, 0.28])
            kido_vpd = local["vpd"]

        capacity_users = _capacity_users(asset._asdict())
        try:
            asset_area = max(0.0, float(getattr(asset, "lettable_area_m2", 0) or 0))
        except (TypeError, ValueError):
            asset_area = 0.0
        area_share = asset_area / max(1.0, commercial_area_by_grid.get(gid, asset_area))
        # The Kido feed is cell-level. Allocate a conservative share of cell
        # users to this business by lettable area before computing an
        # asset-level occupancy proxy; otherwise every shop in a busy cell
        # would inherit the entire cell population and saturate at 100%.
        occupancy_signal = max(0.0, min(1.0, float(google_proxy_by_asset.get(aid, 0.5))))
        asset_users = (
            local_users * min(1.0, area_share)
            * (0.05 + 0.95 * occupancy_signal) ** 1.5
            * 0.25
        )
        proxied_occ = min(1.0, max(0.0, asset_users * (dwell / 60.0) / 12.0 / capacity_users))

        # Reachable neighbourhood activity excludes the local grid so an
        # isolated cell can produce a low ratio.
        neighbor_users = _network_reachable_users(gid, grid_adjacency, grid_mean)
        # v6.1 — flow_island_ratio = reachable / local.
        # < 0.3 → asset is in a cold corner of an otherwise active area
        #          (network-isolated: pedestrian_upgrade target)
        # > 1.0 → asset is a net destination (healthy anchor)
        # = None when local_users is 0 (cannot compute an island ratio for
        #        an asset with no local activity at all).
        flow_island = (
            round(neighbor_users / local_users, 4)
            if local_users > 0 else None
        )

        if gid in grid_geom:
            traffic, traffic_source = resolve_traffic_exposure(kido_vpd, network_proj, grid_geom[gid])
        else:
            traffic, traffic_source = 0, "osm_proxy"

        rows_out.append({
            "asset_id": aid,
            "grid_id": gid,
            "lbs_unique_users_daily": round(asset_users, 2),
            "grid_unique_users_daily": round(local_users, 2),
            "lbs_dwell_time_minutes": round(dwell, 2),
            "capacity_users": round(capacity_users, 2),
            "lbs_visit_frequency_monthly": round(monthly_frequency, 2),
            "lbs_hourly_splits": json.dumps(hourly_split, separators=(",", ":")),
            "lbs_visitor_demographics": json.dumps({
                "age_bands": {"0_14": ages[0], "15_64": ages[1], "65_plus": ages[2]},
                "socioeconomic_class": {"A": ses[0], "BC": ses[1], "DE": ses[2]},
            }, separators=(",", ":")),
            "proxied_occupancy_lbs": round(proxied_occ, 4),
            "traffic_exposure_vpd": int(traffic),
            "traffic_exposure_source": traffic_source,
            "flow_island_ratio": round(flow_island, 4),
            "observed_demand_ratio": round(asset_users / capacity_users, 4),
            "tier": "3a",
            "source": "derived_from_kido_dynamics_mock" if local is not None else "osm_proxy",
            "is_mock": True,
        })
    return pd.DataFrame(rows_out, columns=columns)


def ingest() -> dict[str, int]:
    business_paths = PATHS["business"]
    external_paths = PATHS["external_data"]
    assets = _read_csv(
        BASE / business_paths["assets"],
        {"asset_id", "asset_type", "subtype", "authority", "ownership_status"},
    )
    google = _read_csv(
        BASE / external_paths["google_places_snapshots"],
        {"snapshot_date", "place_id", "asset_id", "business_status", "rating",
         "user_rating_count", "types_json", "location_lat", "location_lng", "match_confidence"},
    )
    kido = _read_csv(
        BASE / external_paths["kido_grid"],
        {"grid_id", "date", "unique_users", "total_visits", "avg_dwell_time_minutes",
         "hourly_visitors_json", "vehicle_flow_vpd"},
    )
    worldpop_path = BASE / external_paths["worldpop_grid"]
    worldpop_columns = [
        "grid_id", "worldpop_raw_pop", "worldpop_effective_pop",
        "worldpop_occupancy_estimate", "residential_unit_capacity",
        "source", "dataset_year", "tier", "is_mock",
    ]
    worldpop = pd.read_csv(worldpop_path) if worldpop_path.exists() else pd.DataFrame(
        columns=worldpop_columns
    )

    allowed_statuses = {"OPERATIONAL", "CLOSED_TEMPORARILY", "CLOSED_PERMANENTLY", "FUTURE_OPENING"}
    invalid = set(google["business_status"].dropna().astype(str)) - allowed_statuses
    if invalid:
        raise ValueError(f"Google Places business_status has invalid values: {sorted(invalid)}")

    mapping_targets = set(TYPE_MAPPING.get("direct_match", {}).values()) | set(TYPE_MAPPING.get("category_fallback", {}).values())
    known_subtypes = set(TAXONOMY.get("subtypes", {}))
    invalid_targets = mapping_targets - known_subtypes
    if invalid_targets:
        raise ValueError(f"Google Places type map targets unknown taxonomy subtypes: {sorted(invalid_targets)}")

    business_presence = build_business_presence(assets, google)
    buildings = _read_layer(PATHS["geometry"]["buildings"])
    parcels = _read_layer(PATHS["geometry"]["parcels"])
    network = _read_layer(PATHS["geometry"]["network"])
    points, _ = _asset_geometry_points(assets, buildings, parcels)
    lbs_metrics = build_lbs_metrics(assets, kido, points, network, business_presence)

    if not worldpop.empty:
        worldpop["tier"] = worldpop.get("tier", "3a").fillna("3a") if isinstance(worldpop.get("tier"), pd.Series) else "3a"
        worldpop["source"] = worldpop.get("source", "worldpop_global2").fillna("worldpop_global2") if isinstance(worldpop.get("source"), pd.Series) else "worldpop_global2"
        worldpop["is_mock"] = False
        if "dataset_year" not in worldpop:
            worldpop["dataset_year"] = 2026
    else:
        worldpop = pd.DataFrame(columns=worldpop_columns)

    outputs = {
        "asset_business_presence": business_presence,
        "asset_lbs_metrics": lbs_metrics,
        "population_worldpop": worldpop,
    }
    row_counts = {}
    for name, frame in outputs.items():
        relative = business_paths[name]
        path = BASE / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)
        row_counts[name] = len(frame)
        print(f"Wrote {path} ({len(frame)} rows)")
    return row_counts


def main() -> None:
    ingest()


if __name__ == "__main__":
    main()
