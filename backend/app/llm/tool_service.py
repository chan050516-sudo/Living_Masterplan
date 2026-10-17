"""Deterministic tool service for LLM tool calling.

Every data access the LLM performs goes through this module. The LLM
never reads files directly. Tools return plain dicts / lists that are
JSON-serialisable.

Design notes:
  - All tools are read-only. Mutation happens via the orchestrator
    when a validated plan is turned into interventions.csv rows.
  - Data is loaded once and cached per TownshipDataSource instance.
  - Nearby-asset queries use centroid distance in EPSG:32647 (metres).
"""

import json
import logging
import math
from pathlib import Path
from typing import Optional

import geopandas as gpd
import pandas as pd

from ..config import load_paths, load_assumptions
from ..taxonomy import get_taxonomy, get_subtypes_for_class

log = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Data source
# ------------------------------------------------------------------


class TownshipDataSource:
    """
    Cached access to every file the LLM tools need. Instantiated once
    per orchestration run.

    All attributes are plain pandas DataFrames / dicts so tools can be
    pure functions over them.
    """

    def __init__(self, repo_root: Path, year: int = 2026):
        self.repo_root = Path(repo_root)
        self.year = year
        self.paths = load_paths()
        self.assumptions = load_assumptions()
        self.taxonomy = get_taxonomy()
        self.subtypes_config = self.taxonomy.get("subtypes", {})

        base = self.repo_root / self.paths["base"]

        self.assets = pd.read_csv(base / "business" / "assets.csv")
        self.metrics = self._read_optional(base / "business" / "asset_metrics_enriched.csv")
        self.projects = self._read_optional(base / "business" / "development_projects.csv")
        self.candidates = self._read_optional(base / "business" / "development_candidates.csv")
        self.interventions = self._read_optional(base / "business" / "interventions.csv")
        self.deadspace = self._load_deadspace(base / "business" / f"deadspace_{year}.json")
        # Phase E — lease schedule. Loaded once. Empty DataFrame when
        # the file is absent.
        lease_path = base / "business" / "asset_leases.csv"
        self.leases = (
            pd.read_csv(lease_path)
            if lease_path.exists() and lease_path.stat().st_size > 0
            else pd.DataFrame()
        )

        # Lazy-loaded spatial caches.
        self._parcels_gdf = None
        self._centroids = None

    # --------------------------------------------------------------
    # Internal helpers
    # --------------------------------------------------------------

    def _read_optional(self, path: Path) -> pd.DataFrame:
        if not path.exists() or path.stat().st_size == 0:
            return pd.DataFrame()
        try:
            return pd.read_csv(path)
        except Exception as e:
            log.warning("Could not read %s: %s", path, e)
            return pd.DataFrame()

    def _load_deadspace(self, path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                records = json.load(f)
            return {r["asset_id"]: r for r in records}
        except Exception as e:
            log.warning("Could not read %s: %s", path, e)
            return {}

    def _asset_row(self, asset_id: str) -> Optional[dict]:
        m = self.assets[self.assets["asset_id"] == asset_id]
        if m.empty:
            return None
        return m.iloc[0].to_dict()

    def _metric_row(self, asset_id: str, year: int) -> Optional[dict]:
        if self.metrics.empty:
            return None
        m = self.metrics[
            (self.metrics["asset_id"] == asset_id) & (self.metrics["year"] == year)
        ]
        if m.empty:
            return None
        return m.iloc[0].to_dict()

    def _load_parcels(self) -> gpd.GeoDataFrame:
        if self._parcels_gdf is not None:
            return self._parcels_gdf
        base = self.repo_root / self.paths["base"]
        path = base / self.paths["geometry"]["parcels"]
        if not path.exists():
            self._parcels_gdf = gpd.GeoDataFrame()
            return self._parcels_gdf
        gdf = gpd.read_file(path)
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326")
        self._parcels_gdf = gdf.to_crs("EPSG:32647")
        return self._parcels_gdf

    def _load_centroids(self) -> dict:
        if self._centroids is not None:
            return self._centroids
        parcels = self._load_parcels()
        centroids = {}
        if not parcels.empty and "asset_id" in parcels.columns:
            for _, row in parcels.iterrows():
                aid = row.get("asset_id")
                if aid is None or (isinstance(aid, float) and math.isnan(aid)):
                    continue
                if row.geometry is None or row.geometry.is_empty:
                    continue
                c = row.geometry.centroid
                centroids[aid] = (c.x, c.y)
        self._centroids = centroids
        return centroids


# ------------------------------------------------------------------
# Tool implementations
# ------------------------------------------------------------------


def get_asset_state(ds: TownshipDataSource, asset_id: str, year: int = None) -> dict:
    """
    Return the asset's static properties plus the metrics recorded for
    the given year. The response deliberately separates observed from
    derived fields so the LLM knows what is measured vs. computed.
    """
    year = year or ds.year
    asset = ds._asset_row(asset_id)
    if asset is None:
        return {"error": f"asset_id {asset_id} not found"}

    metrics = ds._metric_row(asset_id, year) or {}

    # Clean NaN -> None so the LLM never sees the string "nan".
    metrics_clean = {k: _nan_to_none(v) for k, v in metrics.items()}
    asset_clean = {k: _nan_to_none(v) for k, v in asset.items()}

    return {
        "asset_id": asset_id,
        "year": year,
        "identity": {
            "asset_type": asset_clean.get("asset_type"),
            "subtype": asset_clean.get("subtype"),
            "asset_name": asset_clean.get("asset_name"),
            "land_use": asset_clean.get("land_use"),
            "completion_year": asset_clean.get("completion_year"),
        },
        "physical": {
            "floor_area_m2": asset_clean.get("floor_area_m2"),
            "lettable_area_m2": asset_clean.get("lettable_area_m2"),
            "land_area_m2": asset_clean.get("land_area_m2"),
            "capacity": asset_clean.get("capacity"),
        },
        "financial_static": {
            "capex_initial_rm": asset_clean.get("capex_initial_rm"),
            "opex_annual_rm": asset_clean.get("opex_annual_rm"),
            "maintenance_annual_rm": asset_clean.get("maintenance_annual_rm"),
        },
        "observed_metrics": {
            k: metrics_clean.get(k) for k in (
                "occupancy_rate", "vacancy_rate", "vacancy_duration_months",
                "footfall_daily", "utilisation_rate", "rental_income_rm",
                "energy_kwh",
            ) if k in metrics_clean
        },
        "derived_metrics": {
            k: metrics_clean.get(k) for k in (
                "noi_rm", "noi_yield", "maintenance_surge_rm",
                "effective_demand_m2", "dsr",
                "coverage_ratio_5min_walk", "coverage_ratio_10min_walk",
                "coverage_ratio_10min_drive",
                "reachable_population_walk",
                "demographic_mismatch", "neighborhood_diversity",
                "carbon_operational_tco2e",
                "service_coverage", "cost_per_user_rm",
                "green_coverage", "canopy_coverage", "green_per_capita_m2",
                "demand_supply_gap", "potential_gfa_m2",
            ) if k in metrics_clean
        },
    }


def get_asset_evidence(ds: TownshipDataSource, asset_id: str) -> list:
    """Return the human-readable evidence lines from B6."""
    record = ds.deadspace.get(asset_id)
    if not record:
        return []
    return record.get("evidence", [])


def get_deadspace_status(ds: TownshipDataSource, asset_id: str) -> dict:
    """Return the B6 status, flags, urgency, contributing factors."""
    record = ds.deadspace.get(asset_id)
    if not record:
        return {
            "asset_id": asset_id,
            "status": "unknown",
            "flags": [],
            "urgency_index": None,
            "contributing_factors": [],
            "note": "No deadspace record for this asset in the current year.",
        }
    return {
        "asset_id": asset_id,
        "status": record.get("status"),
        "flags": record.get("flags", []),
        "urgency_index": record.get("urgency_index"),
        "contributing_factors": record.get("contributing_factors", []),
    }


def get_catchment_profile(ds: TownshipDataSource, asset_id: str,
                          mode: str = "walk") -> dict:
    """
    Return the catchment profile for the asset. mode is "walk" or
    "drive". Population is returned per threshold, plus aggregate
    reachable population and distance statistics.
    """
    metrics = ds._metric_row(asset_id, ds.year)
    if not metrics:
        return {"error": f"no metrics for {asset_id} in {ds.year}"}

    suffix = "_walk" if mode == "walk" else "_drive"
    return {
        "asset_id": asset_id,
        "mode": mode,
        "catchment_population_5min": _nan_to_none(metrics.get(f"catchment_population_5min{suffix}")),
        "catchment_population_10min": _nan_to_none(metrics.get(f"catchment_population_10min{suffix}")),
        "catchment_population_15min": _nan_to_none(metrics.get(f"catchment_population_15min{suffix}")),
        "coverage_ratio_5min": _nan_to_none(metrics.get(f"coverage_ratio_5min{suffix}")),
        "coverage_ratio_10min": _nan_to_none(metrics.get(f"coverage_ratio_10min{suffix}")),
        "coverage_ratio_15min": _nan_to_none(metrics.get(f"coverage_ratio_15min{suffix}")),
        "mean_distance_m": _nan_to_none(metrics.get(f"mean_{mode}_distance_m")),
        "median_distance_m": _nan_to_none(metrics.get(f"median_{mode}_distance_m")),
        "reachable_population": _nan_to_none(metrics.get(f"reachable_population{suffix}")),
    }


def get_population_profile(ds: TownshipDataSource, asset_id: str) -> dict:
    """
    Return the age structure of the asset's walking catchment, if the
    underlying population layers expose it. Falls back to the raw
    population file when the catchment aggregate is unavailable.
    """
    # The enriched metrics do not carry age bands directly. Derive
    # from the population GeoJSON clipped to the asset's walking
    # catchment (approximated by the whole township for now).
    base = ds.repo_root / ds.paths["base"]
    pop_path = base / ds.paths["geometry"]["population"]
    if not pop_path.exists():
        return {"asset_id": asset_id, "note": "population layer unavailable"}

    try:
        gdf = gpd.read_file(pop_path)
    except Exception as e:
        return {"asset_id": asset_id, "error": str(e)}

    if gdf.empty:
        return {"asset_id": asset_id, "note": "population layer empty"}

    totals = {
        "total": float(gdf.get("total_population", pd.Series(dtype=float)).fillna(0).sum()),
        "age_0_14": float(gdf.get("age_0_14", pd.Series(dtype=float)).fillna(0).sum()),
        "age_15_64": float(gdf.get("age_15_64", pd.Series(dtype=float)).fillna(0).sum()),
        "age_65_plus": float(gdf.get("age_65_plus", pd.Series(dtype=float)).fillna(0).sum()),
    }
    if totals["total"] > 0:
        totals["ratio_0_14"] = round(totals["age_0_14"] / totals["total"], 4)
        totals["ratio_15_64"] = round(totals["age_15_64"] / totals["total"], 4)
        totals["ratio_65_plus"] = round(totals["age_65_plus"] / totals["total"], 4)

    return {"asset_id": asset_id, **totals}


def get_nearby_assets(ds: TownshipDataSource, asset_id: str,
                      radius_m: float = 800.0,
                      asset_type: str = None) -> list:
    """
    Return assets within radius_m of the given asset (centroid distance
    in EPSG:32647). Optionally filter by asset_type.
    """
    centroids = ds._load_centroids()
    origin = centroids.get(asset_id)
    if origin is None:
        return []

    ox, oy = origin
    results = []
    for _, row in ds.assets.iterrows():
        other = row["asset_id"]
        if other == asset_id:
            continue
        if asset_type and row["asset_type"] != asset_type:
            continue
        c = centroids.get(other)
        if c is None:
            continue
        d = math.hypot(c[0] - ox, c[1] - oy)
        if d <= radius_m:
            results.append({
                "asset_id": other,
                "asset_type": row["asset_type"],
                "subtype": _nan_to_none(row.get("subtype")),
                "distance_m": round(d, 1),
            })
    results.sort(key=lambda x: x["distance_m"])
    return results


def get_available_subtypes(ds: TownshipDataSource, asset_class: str) -> list:
    """
    Return subtypes available for the given asset class, with the
    metadata the LLM needs to reason about the choice.
    """
    names = get_subtypes_for_class(asset_class)
    result = []
    for name in names:
        defn = ds.subtypes_config.get(name, {})
        result.append({
            "subtype": name,
            "display_name": defn.get("display_name"),
            "target_demographics": defn.get("target_demographics", []),
            "is_core_amenity": defn.get("is_core_amenity", False),
            "target_area_m2": defn.get("target_area_m2"),
            "competition_radius_m": defn.get("competition_radius_m"),
        })
    return result


def get_development_candidates(ds: TownshipDataSource, parcel_id: str) -> list:
    """Return candidate developments for a parcel."""
    if ds.candidates.empty:
        return []
    m = ds.candidates[ds.candidates["parcel_id"] == parcel_id]
    return [
        {k: _nan_to_none(v) for k, v in row.items()}
        for _, row in m.iterrows()
    ]


def get_taxonomy_entry(ds: TownshipDataSource, subtype: str) -> dict:
    """Return the full taxonomy definition for a subtype."""
    defn = ds.subtypes_config.get(subtype)
    if defn is None:
        return {"error": f"subtype {subtype} not in taxonomy"}
    return {"subtype": subtype, **_nan_to_none_dict(defn)}


def get_assumptions_slice(ds: TownshipDataSource, keys: list) -> dict:
    """
    Return specific top-level sections of assumptions.yml. Used when
    the LLM needs to reason about model parameters (e.g. huff alpha).
    """
    out = {}
    for k in keys:
        if k in ds.assumptions:
            out[k] = ds.assumptions[k]
    return out


def get_interventions_history(ds: TownshipDataSource, asset_id: str) -> list:
    """Return interventions that have targeted this asset in any scenario."""
    if ds.interventions.empty:
        return []
    m = ds.interventions[ds.interventions["target_asset_id"] == asset_id]
    return [
        {k: _nan_to_none(v) for k, v in row.items()}
        for _, row in m.iterrows()
    ]


def get_action_space(ds: TownshipDataSource, asset_type: str) -> list:
    """
    Return the intervention types applicable to an asset type. Mirrors
    deadspace.layer3.ACTION_SPACE but is exposed as a tool so the LLM
    can query it directly.
    """
    from ..deadspace.layer3 import ACTION_SPACE
    return list(ACTION_SPACE.get(asset_type, []))


def get_lease_schedule(ds: TownshipDataSource, asset_id: str) -> dict:
    """
    Return the asset's lease schedule.

    Only meaningful for commercial assets with a unit_mix. Returns
    `{total_leases, next_expiry_year, anchor_lease, expiry_calendar}`,
    or `{note}` when the asset has no leases.
    """
    if ds.leases is None or ds.leases.empty:
        return {"asset_id": asset_id, "note": "no lease records"}
    m = ds.leases[ds.leases["asset_id"] == asset_id]
    if m.empty:
        return {"asset_id": asset_id, "note": "no lease records for asset"}

    active = m[m["lease_status"] == "active"]
    ends = active["lease_end_year"].dropna()
    next_end = None
    if not ends.empty:
        try:
            next_end = int(ends.min())
        except (TypeError, ValueError):
            pass

    anchor = active[active["tenant_type"] == "anchor"]
    anchor_block = None
    if not anchor.empty:
        a = anchor.iloc[0]
        anchor_block = {
            "floor_area_m2": _nan_to_none(a.get("floor_area_m2")),
            "end_year": _nan_to_none(a.get("lease_end_year")),
        }

    calendar = {}
    for _, lease in active.iterrows():
        yr = lease.get("lease_end_year")
        if yr is None:
            continue
        try:
            yr_int = int(yr)
        except (TypeError, ValueError):
            continue
        calendar[str(yr_int)] = calendar.get(str(yr_int), 0) + 1

    return {
        "asset_id": asset_id,
        "total_leases": int(len(m)),
        "next_expiry_year": next_end,
        "anchor_lease": anchor_block,
        "expiry_calendar": calendar,
    }


def get_asset_trajectory(ds: TownshipDataSource, asset_id: str) -> dict:
    """
    Return the asset's five-year trajectory features.

    Empty dict when the trajectory is unknown (non-time-series types).
    """
    m = ds._metric_row(asset_id, ds.year) or {}
    tclass = m.get("trajectory_class")
    if not tclass or tclass == "unknown":
        return {"asset_id": asset_id, "trajectory_class": "unknown"}

    def _f(v):
        return _nan_to_none(v)

    return {
        "asset_id": asset_id,
        "trajectory_class": tclass,
        "peak_occupancy": _f(m.get("peak_occupancy")),
        "years_since_peak": _f(m.get("years_since_peak")),
        "occupancy_trend_3yr": _f(m.get("occupancy_trend_3yr")),
        "years_below_benchmark": _f(m.get("years_below_benchmark")),
        "vacancy_streak_months": _f(m.get("vacancy_streak_months")),
    }


# ------------------------------------------------------------------
# Dispatch table
# ------------------------------------------------------------------
# Maps tool name -> (callable, argument extraction). The orchestrator
# looks up tool calls here. Keeping this as data (not if/else) makes
# it easy to keep in sync with tools_schema.json.

TOOL_DISPATCH = {
    "get_asset_state":           lambda ds, a: get_asset_state(ds, a["asset_id"], a.get("year")),
    "get_asset_evidence":        lambda ds, a: get_asset_evidence(ds, a["asset_id"]),
    "get_deadspace_status":      lambda ds, a: get_deadspace_status(ds, a["asset_id"]),
    "get_catchment_profile":     lambda ds, a: get_catchment_profile(ds, a["asset_id"], a.get("mode", "walk")),
    "get_population_profile":    lambda ds, a: get_population_profile(ds, a["asset_id"]),
    "get_nearby_assets":         lambda ds, a: get_nearby_assets(ds, a["asset_id"], a.get("radius_m", 800.0), a.get("asset_type")),
    "get_available_subtypes":    lambda ds, a: get_available_subtypes(ds, a["asset_class"]),
    "get_development_candidates":lambda ds, a: get_development_candidates(ds, a["parcel_id"]),
    "get_taxonomy_entry":        lambda ds, a: get_taxonomy_entry(ds, a["subtype"]),
    "get_assumptions_slice":     lambda ds, a: get_assumptions_slice(ds, a.get("keys", [])),
    "get_interventions_history": lambda ds, a: get_interventions_history(ds, a["asset_id"]),
    "get_action_space":          lambda ds, a: get_action_space(ds, a["asset_type"]),
    "get_lease_schedule":        lambda ds, a: get_lease_schedule(ds, a["asset_id"]),
    "get_asset_trajectory":      lambda ds, a: get_asset_trajectory(ds, a["asset_id"]),
}


def dispatch(ds: TownshipDataSource, tool_name: str, arguments: dict):
    """Execute a tool call. Returns {"ok": bool, "result": any, "error": str}."""
    handler = TOOL_DISPATCH.get(tool_name)
    if handler is None:
        return {"ok": False, "error": f"unknown tool: {tool_name}"}
    try:
        return {"ok": True, "result": handler(ds, arguments or {})}
    except Exception as e:
        log.exception("Tool %s failed", tool_name)
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


# ------------------------------------------------------------------
# Small utilities
# ------------------------------------------------------------------


def _nan_to_none(v):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, (int, float)):
        return v
    if hasattr(v, "item"):
        try:
            return v.item()
        except Exception:
            return v
    return v


def _nan_to_none_dict(d: dict) -> dict:
    return {k: _nan_to_none(v) for k, v in d.items()}