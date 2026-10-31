"""B3 unified entry point: compute_derived_metrics.

Phase 2 changes:
  - Per-subtype Huff pools.
  - Per-subtype energy intensity.
  - Demographic mismatch from catchment population.
  - Neighborhood diversity via Shannon entropy.
"""

import json
import logging
import pickle
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd

from ..config import load_paths, load_assumptions
from ..taxonomy import get_taxonomy, default_subtype_for
from ..loaders.geometry_loader import load_geometry
from ..loaders.business_loader import load_business
from .context import DerivationContext
from .network_graph import (
    build_graph_by_mode,
    find_entry_point,
    insert_all_entries,
    extract_nodes,
)
from .accessibility import (
    compute_distance_matrix,
    catchment_profile,
    derive_score_from_profile,
)
from .huff import huff_gravity_by_subtype, huff_by_subtype_per_asset
from .demand_mismatch import aggregate_catchment_profile
from .diversity import neighborhood_diversity
from .commercial import derive_commercial
from .facility import derive_facility
from .green import derive_green
from .parcel import derive_parcel
from .residential import derive_residential
from .thermal import empty_thermal_metrics, load_thermal_observations

log = logging.getLogger(__name__)


DERIVERS = {
    "commercial": derive_commercial,
    "community_facility": derive_facility,
    "green_space": derive_green,
    "undeveloped_parcel": derive_parcel,
    "residential": derive_residential,
}

# Fixed radius used for neighborhood diversity. Independent of the
# subtype competition radius because it measures "business mix around
# the asset", not "who competes with whom".
DIVERSITY_RADIUS_M = 800.0


def compute_derived_metrics(
    repo_root: Path = None,
    year: int = 2026,
    years: list = None,
    network_override=None,
    _shared_cache: dict = None,
    _cache_key: str = None,
) -> pd.DataFrame:
    """
    Compute derived metrics for every asset at every requested year.

    Parameters
    ----------
    year : int
        Base year (used when `years` is None).
    years : list[int] | None
        Years to compute. When provided, the returned DataFrame has
        one row per (asset, year). When None, defaults to `[year]`.
    network_override : gpd.GeoDataFrame, optional
        Modified network layer. When provided, it is used for the
        walking pipeline. The driving pipeline always uses the
        original network.

    The Huff gravity is computed ONCE for the whole history, because
    supply (lettable area) and demand (population) do not vary by
    year in this model. Only the per-year environmental split and the
    trajectory features are year-varying.
    """
    repo_root = repo_root or Path(__file__).resolve().parents[3]
    if years is None:
        years = [year]

    paths = load_paths()
    assumptions = load_assumptions()
    taxonomy = get_taxonomy()
    subtypes_config = taxonomy.get("subtypes", {})

    geometry = load_geometry(repo_root, paths)
    business = load_business(repo_root, paths)
    thermal_path = (
        repo_root
        / paths["base"]
        / paths.get("thermal", {}).get(
            "observations", "business/thermal_observations.csv"
        )
    )
    thermal_observations = load_thermal_observations(thermal_path)

    # Load WRI Canopy Observation Data
    wri_canopy_lookup = {}
    wri_path = repo_root / paths["base"] / "business" / "wri_canopy_observations.csv"
    if wri_path.exists():
        wri_df = pd.read_csv(wri_path)
        wri_canopy_lookup = dict(zip(wri_df["asset_id"], wri_df["wri_treecover_fraction"]))

    green_blue_analysis = geometry.get("green_blue", {}).get("analysis")

    # --- Canopy coverage per asset ---
    asset_canopy = {}
    for _, asset in business["assets"].iterrows():
        aid = asset["asset_id"]
        
        # Priortise WRI Data
        wri_val = wri_canopy_lookup.get(aid)
        if wri_val is not None and not pd.isna(wri_val):
            asset_canopy[aid] = float(wri_val)
            continue
            
        # Fallback: Only if WRI null，use OSM algorithm
        parcels = geometry["parcels"]["analysis"]
        match = parcels[parcels["asset_id"] == aid]
        if match.empty:
            continue
        asset_canopy[aid] = _compute_canopy_coverage(
            asset_id=aid,
            asset_geom=match.iloc[0].geometry,
            green_blue_gdf=green_blue_analysis,
            land_area_m2=asset.get("land_area_m2"),
        )

    pop_analysis = geometry["population"]["analysis"]

    # --- Per-mode pipelines ---
    mode_configs = assumptions.get("mode_networks", {})
    walking_cfg = mode_configs.get("walking", {})
    driving_cfg = mode_configs.get("driving", {})

    base_network = geometry["network"]["analysis"]
    walking_network = network_override if network_override is not None else base_network

    # Phase A: Pipeline caching.
    # B3 computes the full walking graph + all-pairs Dijkstra once per
    # network version. B4 reads this cache directly, eliminating the
    # 10-15s duplicate graph build / Dijkstra run.
    walk_key = f"{_cache_key or 'base'}_walking"
    drv_key = "base_driving"  # Driving network never changes.

    pipelines = (
        _shared_cache.setdefault("pipelines", {})
        if _shared_cache is not None else {}
    )

    # Fast path: load baked pickle from disk if available.
    cache_dir = repo_root / paths["base"] / "cache"
    walk_pkl = cache_dir / "walking_pipeline_base.pkl"
    drive_pkl = cache_dir / "driving_pipeline_base.pkl"

    if walk_key in pipelines:
        log.info("B3: Reusing in-memory pipeline for %s", walk_key)
        walking_pipeline = pipelines[walk_key]
        supply_nodes_huff = walking_pipeline["supply_nodes"]
        demand_nodes_huff = walking_pipeline["demand_nodes"]
    elif walk_key == "base_walking" and walk_pkl.exists():
        log.info("B3: Loading baked walking pipeline from %s", walk_pkl)
        with open(walk_pkl, "rb") as f:
            walking_pipeline = pickle.load(f)
        supply_nodes_huff = _build_huff_supply_nodes(business["assets"], walking_pipeline)
        demand_nodes_huff = _build_huff_demand_nodes(walking_pipeline)
        walking_pipeline["supply_nodes"] = supply_nodes_huff
        walking_pipeline["demand_nodes"] = demand_nodes_huff
        if _shared_cache is not None:
            pipelines[walk_key] = walking_pipeline
    else:
        log.info("B3: Building walking pipeline for %s (first run)", walk_key)
        walking_pipeline = _prepare_mode_pipeline(
            mode="walking",
            network_gdf=walking_network,
            assets_df=business["assets"],
            parcels_gdf=geometry["parcels"]["analysis"],
            pop_gdf=pop_analysis,
            gamma=assumptions.get("accessibility", {}).get("canopy_impedance_gamma", 0.3),
            cfg=walking_cfg,
        )
        supply_nodes_huff = _build_huff_supply_nodes(business["assets"], walking_pipeline)
        demand_nodes_huff = _build_huff_demand_nodes(walking_pipeline)
        
        # Enrich the pipeline with fields B4 expects.
        walking_pipeline["supply_nodes"] = supply_nodes_huff
        walking_pipeline["demand_nodes"] = demand_nodes_huff
        walking_pipeline["nodes_gdf"] = extract_nodes(walking_network)
        
        if _shared_cache is not None:
            pipelines[walk_key] = walking_pipeline

    if drv_key in pipelines:
        driving_pipeline = pipelines[drv_key]
    elif drive_pkl.exists():
        log.info("B3: Loading baked driving pipeline from %s", drive_pkl)
        with open(drive_pkl, "rb") as f:
            driving_pipeline = pickle.load(f)
        if _shared_cache is not None:
            pipelines[drv_key] = driving_pipeline
    else:
        log.info("B3: Building driving pipeline (first run)")
        driving_pipeline = _prepare_mode_pipeline(
            mode="driving",
            network_gdf=base_network,
            assets_df=business["assets"],
            parcels_gdf=geometry["parcels"]["analysis"],
            pop_gdf=pop_analysis,
            gamma=0.0,
            cfg=driving_cfg,
        )
        if _shared_cache is not None:
            pipelines[drv_key] = driving_pipeline

    # --- Huff per subtype (computed once, reused across all years) ---
    huff_by_asset_subtype = huff_by_subtype_per_asset(
        walking_pipeline["distance_matrix"],
        demand_nodes_huff,
        supply_nodes_huff,
        subtypes_config=subtypes_config,
        alpha=assumptions.get("huff", {}).get("alpha", 1.0),
        beta=assumptions.get("huff", {}).get("beta", 2.0),
    )

    # --- Derive metrics per asset per year ---
    rows = []
    for _, asset in business["assets"].iterrows():
        atype = asset["asset_type"]
        deriver = DERIVERS.get(atype)
        if deriver is None:
            continue

        aid = asset["asset_id"]

        # M7a — resolve subtype BEFORE computing the demographic
        # catchment, so that catchment can use the subtype's own
        # competition_radius_m instead of a fixed 1200 m.
        #
        # Rationale: a café's demographic catchment is a 400 m walk;
        # a supermarket's is a 3 km drive. Using the same 1200 m
        # for both aggregated the whole township into every
        # catchment, which made `demographic_mismatch` permanently
        # zero because every asset's catchment looked like the
        # township average.
        subtype = asset.get("subtype") or default_subtype_for(atype)
        subtype_cfg = subtypes_config.get(subtype, {})

        _demographic_radius = subtype_cfg.get("competition_radius_m")
        try:
            _demographic_radius = float(_demographic_radius)
        except (TypeError, ValueError):
            _demographic_radius = 800.0  # township-typical fallback

        walking_profile = _compute_asset_profile(
            asset_entry=walking_pipeline["asset_entries"].get(aid),
            demand_entries=walking_pipeline["demand_entries"],
            distance_matrix=walking_pipeline["distance_matrix"],
            cfg=walking_cfg,
            mode="walking",
        )
        driving_profile = _compute_asset_profile(
            asset_entry=driving_pipeline["asset_entries"].get(aid),
            demand_entries=driving_pipeline["demand_entries"],
            distance_matrix=driving_pipeline["distance_matrix"],
            cfg=driving_cfg,
            mode="driving",
        )

        accessibility_score = derive_score_from_profile(
            walking_profile, primary_threshold=10,
        )

        pop_profile = aggregate_catchment_profile(
            demand_entries=walking_pipeline["demand_entries_with_age"],
            distance_matrix=walking_pipeline["distance_matrix"],
            asset_entry=walking_pipeline["asset_entries"].get(aid),
            max_distance_m=_demographic_radius,   # M7a
        )

        asset_vn = walking_pipeline["asset_entries"].get(aid, {}).get("virtual_node")
        diversity_val = neighborhood_diversity(
            asset_id=aid,
            supply_nodes=supply_nodes_huff,
            distance_matrix=walking_pipeline["distance_matrix"],
            asset_vn=asset_vn,
            radius_m=DIVERSITY_RADIUS_M,
        )

        coeff = subtype_cfg.get("demand_coefficient_m2_per_person", 0.05) or 0.05

        # Per-subtype Huff demand for this asset.
        huff_by_subtype = huff_by_asset_subtype.get(aid, {})
        total_demand_m2 = (
            sum(huff_by_subtype.values()) if huff_by_subtype else None
        )
        effective_demand_persons = (
            total_demand_m2 / coeff
            if total_demand_m2 is not None and coeff > 0
            else None
        )

        for y in years:
            # Pull this year's observed metrics for this asset.
            year_metrics_row = business["asset_metrics"]
            year_metrics_row = year_metrics_row[
                (year_metrics_row["asset_id"] == aid)
                & (year_metrics_row["year"] == y)
            ]
            if year_metrics_row.empty:
                continue

            ctx = DerivationContext(
                asset=asset,
                business=business,
                geometry=geometry,
                assumptions=assumptions,
                accessibility_score=accessibility_score,
                huff_effective_demand=effective_demand_persons,
                huff_effective_demand_m2=total_demand_m2,
                huff_by_subtype=huff_by_subtype,
                graph=walking_pipeline["graph"],
                year=y,
                canopy_coverage=asset_canopy.get(aid),
                distance_matrix=walking_pipeline["distance_matrix"],
                walking_profile=walking_profile,
                driving_profile=driving_profile,
                catchment_population_profile=pop_profile,
                neighborhood_diversity=diversity_val,
            )

            base_row = deriver(ctx)
            # Temperature comes only from the audited Landsat observation
            # table. Missing or uncovered parcels stay null; the canopy
            # calculation is retained only as a separate shade indicator.
            thermal_metrics = (
                thermal_observations.get(str(aid), empty_thermal_metrics())
                if y == year
                else empty_thermal_metrics()
            )
            base_row.update(thermal_metrics)
            base_row = _flatten_profiles(
                base_row, walking_profile, driving_profile,
            )
            rows.append(base_row)

    df = pd.DataFrame(rows)

    # Phase B.1 — trajectory features, computed once from the full
    # 5-year history. B6 will consume these on the 2026 row.
    df = _add_trajectory_features(df, years)

    return df


# ---------------------------------------------------------------
# Pipeline helpers (same shape as Phase 1, added demand_with_age)
# ---------------------------------------------------------------

def _prepare_mode_pipeline(
    mode, network_gdf, assets_df, parcels_gdf, pop_gdf, gamma, cfg,
):
    """
    Build a mode-specific pipeline.

    All entries (assets + demands) MUST be inserted in a single call
    to insert_all_entries, because each insertion splits the target
    edge. A second call would not find the original edge and would
    silently skip every entry it tries to insert.
    """
    G = build_graph_by_mode(network_gdf, mode=mode, gamma=gamma)

    # --- Project all entries first (no graph modification yet) ---
    all_entries = {}

    for _, asset in assets_df.iterrows():
        aid = asset["asset_id"]
        geom = None

        # Primary: resolve through parcels.asset_id, the 1:1 map
        # written by build_mock_data.
        match = parcels_gdf[parcels_gdf["asset_id"] == aid]
        if not match.empty:
            geom = match.iloc[0].geometry
        else:
            # Fallback: resolve through the asset's own parcel_id.
            # Handles shared parcels and any asset whose parcel was
            # not assigned a 1:1 asset_id back-reference.
            pid = asset.get("parcel_id")
            if pid is not None and not (
                isinstance(pid, float) and pd.isna(pid)
            ):
                pmatch = parcels_gdf[parcels_gdf["parcel_id"] == pid]
                if not pmatch.empty:
                    geom = pmatch.iloc[0].geometry

        if geom is None or geom.is_empty:
            continue
        p, off_d, eid = find_entry_point(geom, network_gdf, mode)
        if p is None:
            continue
        all_entries[f"A::{aid}"] = (p, off_d, eid)

    for _, pop in pop_gdf.iterrows():
        pid = pop["population_id"]
        p, off_d, eid = find_entry_point(pop.geometry, network_gdf, mode)
        if p is None:
            continue
        all_entries[f"D::{pid}"] = (p, off_d, eid)

    # --- Single insertion pass over the augmented graph ---
    G_aug = G.copy()
    inserted = insert_all_entries(G_aug, network_gdf, all_entries)

    # --- Split the result by prefix ---
    asset_entries = {}
    demand_entries_map = {}
    for key, val in inserted.items():
        if key.startswith("A::"):
            asset_entries[key[3:]] = val
        elif key.startswith("D::"):
            demand_entries_map[key[3:]] = val

    # --- Distance matrix (one Dijkstra pass over the augmented graph) ---
    distance_matrix = compute_distance_matrix(G_aug)

    # --- Demand entries with population and age structure ---
    demand_entries = []
    demand_entries_with_age = []

    for _, pop in pop_gdf.iterrows():
        pid = pop["population_id"]
        info = demand_entries_map.get(pid)
        if info is None:
            continue

        total = float(pop.get("total_population", 0.0))
        entry = {
            "demand_id": pid,
            "virtual_node": info["virtual_node"],
            "off_distance": info["off_distance"],
            "population": total,
        }
        demand_entries.append(entry)

        extended = dict(entry)
        extended["total_population"] = total
        extended["age_0_14"] = float(pop.get("age_0_14", 0.0) or 0.0)
        extended["age_15_64"] = float(pop.get("age_15_64", 0.0) or 0.0)
        extended["age_65_plus"] = float(pop.get("age_65_plus", 0.0) or 0.0)
        demand_entries_with_age.append(extended)

    return {
        "graph": G_aug,
        "distance_matrix": distance_matrix,
        "asset_entries": asset_entries,
        "demand_entries": demand_entries,
        "demand_entries_with_age": demand_entries_with_age,
    }


def _compute_asset_profile(asset_entry, demand_entries, distance_matrix, cfg, mode="walking"):
    """
    Compute a catchment profile for one asset in a given mode.

    The minute→distance conversion depends on the mode:
      - walking: uses speed_m_per_min (m/min)
      - driving: uses speed_kmh (km/h), converted to m/min

    FIX: previously the driving profile reused walking's speed_m_per_min,
    which made every `coverage_ratio_*min_drive` field wrong.
    """
    if mode == "driving":
        speed_m_per_min = float(cfg.get("speed_kmh", 30.0)) * 1000.0 / 60.0
    else:
        speed_m_per_min = float(cfg.get("speed_m_per_min", 80.0))

    thresholds = cfg.get("thresholds_min", [5, 10, 15])

    return catchment_profile(
        distance_matrix=distance_matrix,
        asset_entry=asset_entry,          # catchment_profile handles None
        demand_entries=demand_entries,
        thresholds_min=thresholds,
        speed_m_per_min=speed_m_per_min,
    )


def _build_huff_demand_nodes(walking_pipeline) -> list:
    nodes = []
    for entry in walking_pipeline["demand_entries"]:
        nodes.append({
            "population_id": entry["demand_id"],
            "node": entry["virtual_node"],
            "population": entry["population"],
        })
    return nodes


def _build_huff_supply_nodes(assets_df, walking_pipeline) -> list:
    """
    Supply nodes expand per-subtype for mixed-use commercial assets.

    A mall with a unit_mix {"supermarket": ..., "f_and_b": ...}
    enters each subtype's Huff pool with that subtype's own area as
    attractiveness. A single-subtype shop enters one pool with its
    whole lettable area.

    Phase B.2 fix — previously every commercial asset entered
    exactly one pool keyed by its primary subtype. A mall's F&B
    floor competed as if it were medical_retail; its supermarket as
    if it were the primary subtype. The per-subtype DSR and per-
    subtype demand that B.2 emits could therefore only ever show
    one subtype. Fixing the supply-node builder makes the whole
    per-subtype pipeline coherent.
    """
    nodes = []
    for _, asset in assets_df.iterrows():
        if asset["asset_type"] != "commercial":
            continue
        aid = asset["asset_id"]
        entry = walking_pipeline["asset_entries"].get(aid)
        if entry is None:
            continue

        mix = _parse_unit_mix_engine(asset.get("unit_mix_json"))
        if mix:
            for st, info in mix.items():
                area = float(info.get("area_m2") or 0)
                if area <= 0:
                    continue
                nodes.append({
                    "asset_id": aid,
                    "node": entry["virtual_node"],
                    "attractiveness": area,
                    "subtype": st,
                })
        else:
            subtype = asset.get("subtype") or default_subtype_for(
                asset.get("asset_type"),
            )
            nodes.append({
                "asset_id": aid,
                "node": entry["virtual_node"],
                "attractiveness": float(asset.get("lettable_area_m2") or 0.0),
                "subtype": subtype,
            })
    return nodes


def _parse_unit_mix_engine(raw):
    """Parse unit_mix_json; NaN-safe. Mirrors the helper in
    commercial.py but lives here so the engine does not depend on
    the deriver module."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw or None
    try:
        if pd.isna(raw):
            return None
    except (TypeError, ValueError):
        pass
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and obj:
            return obj
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return None


def _flatten_profiles(base_row, walking, driving):
    merged = dict(base_row)
    merged["catchment_population_5min_walk"] = walking.get("catchment_population_5min")
    merged["catchment_population_10min_walk"] = walking.get("catchment_population_10min")
    merged["catchment_population_15min_walk"] = walking.get("catchment_population_15min")
    merged["coverage_ratio_5min_walk"] = walking.get("coverage_ratio_5min")
    merged["coverage_ratio_10min_walk"] = walking.get("coverage_ratio_10min")
    merged["coverage_ratio_15min_walk"] = walking.get("coverage_ratio_15min")
    merged["mean_walk_distance_m"] = walking.get("mean_distance_m")
    merged["median_walk_distance_m"] = walking.get("median_distance_m")
    merged["p90_walk_distance_m"] = walking.get("p90_distance_m")
    merged["reachable_population_walk"] = walking.get("reachable_population")
    merged["total_catchment_population"] = walking.get("total_catchment_population")

    merged["catchment_population_5min_drive"] = driving.get("catchment_population_5min")
    merged["catchment_population_10min_drive"] = driving.get("catchment_population_10min")
    merged["catchment_population_15min_drive"] = driving.get("catchment_population_15min")
    merged["coverage_ratio_5min_drive"] = driving.get("coverage_ratio_5min")
    merged["coverage_ratio_10min_drive"] = driving.get("coverage_ratio_10min")
    merged["coverage_ratio_15min_drive"] = driving.get("coverage_ratio_15min")
    merged["mean_drive_distance_m"] = driving.get("mean_distance_m")
    merged["median_drive_distance_m"] = driving.get("median_distance_m")
    merged["p90_drive_distance_m"] = driving.get("p90_distance_m")
    merged["reachable_population_drive"] = driving.get("reachable_population")
    return merged


def _compute_canopy_coverage(asset_id, asset_geom, green_blue_gdf, land_area_m2):
    """
    Compute canopy coverage for one asset.

    Overlays the asset's geometry onto the green/blue layer and sums
    the CLIPPED intersection area, weighted by green_type.

    Phase B.1 — landscape-scale exclusion
    --------------------------------------
    A natural=wood or natural=forest polygon in OSM is often 10+ ha.
    A residential parcel sitting inside it is technically covered,
    but the wood is a landscape feature, not shade on that parcel.
    Including these overlays sets canopy_coverage = 1.0 for every
    building inside the wood, which collapses UHI to a false -4.5 °C
    and makes every downstream UHI-driven flag fire on the wrong
    assets.

    The exclusion rule: skip any green polygon whose own area exceeds
    10× the asset's area. A 500 m² parcel is unaffected by a 12 ha
    wood polygon; a 500 m² parcel IS affected by a 2,000 m² park
    next to it.
    """
    if green_blue_gdf is None or green_blue_gdf.empty:
        return None
    if land_area_m2 is None:
        return None
    try:
        land_area_f = float(land_area_m2)
    except (TypeError, ValueError):
        return None
    if land_area_f <= 0:
        return None
    if asset_geom is None or asset_geom.is_empty:
        return None

    # Relative shade / evapotranspiration weight per green type.
    _weights = {
        "canopy": 1.0,
        "park": 1.0,
        "pocket_park": 1.0,
        "green_corridor": 1.0,
        "public_space": 0.6,
        "water_body": 0.5,
        "drainage": 0.3,
    }

    try:
        candidates = green_blue_gdf[
            green_blue_gdf.geometry.intersects(asset_geom)
        ]
        if candidates.empty:
            return 0.0

        # Landscape-scale filter.
        asset_area = asset_geom.area
        max_overlay_area = 10.0 * asset_area

        total_weighted = 0.0
        for _, row in candidates.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            if geom.area > max_overlay_area:
                continue
            try:
                overlap_area = geom.intersection(asset_geom).area
            except Exception:
                continue
            gtype = row.get("green_type")
            w = _weights.get(gtype, 0.4)
            total_weighted += overlap_area * w

        return min(1.0, max(0.0, total_weighted / land_area_f))
    except Exception:
        return None


# ------------------------------------------------------------------
# Phase B.1 — trajectory features
# ------------------------------------------------------------------

def _add_trajectory_features(df: pd.DataFrame, years: list) -> pd.DataFrame:
    """
    Attach trajectory features to every row.

    For each (asset_id, year) row, the trajectory features describe
    the asset's history up to that year. For the 2026 row (the year
    B6 inspects), the window is the full 5-year history.
    """
    if df.empty or len(years) < 2:
        # Single-year mode: no trajectory is defined.
        for col in (
            "occupancy_trend_3yr", "noi_trend_3yr",
            "years_below_benchmark", "peak_occupancy",
            "years_since_peak", "vacancy_streak_months",
            "trajectory_class",
        ):
            df[col] = None
        return df

    df = df.sort_values(["asset_id", "year"]).reset_index(drop=True)

    feature_rows = []
    for aid, group in df.groupby("asset_id", sort=False):
        group = group.sort_values("year").reset_index(drop=True)
        subtype = group["subtype"].iloc[0] if "subtype" in group else None

        for i, row in group.iterrows():
            year = row["year"]
            past = group[group["year"] <= year]
            feat = _trajectory_features_for_window(past, subtype)
            feature_rows.append((aid, year, feat))

    feat_df = pd.DataFrame([
        {"asset_id": aid, "year": year, **feat}
        for aid, year, feat in feature_rows
    ])

    merged = df.merge(feat_df, on=["asset_id", "year"], how="left")
    return merged


def _trajectory_features_for_window(past_df: pd.DataFrame,
                                     subtype) -> dict:
    """
    Compute trajectory features from a window of past rows.
    """
    from ..taxonomy import get_subtype_or_default

    empty = {
        "occupancy_trend_3yr": None,
        "noi_trend_3yr": None,
        "years_below_benchmark": 0,
        "peak_occupancy": None,
        "years_since_peak": 0,
        "vacancy_streak_months": None,
        "trajectory_class": "unknown",
    }

    if past_df.empty:
        return empty

    occ = past_df["occupancy_rate"].dropna().values
    if len(occ) == 0:
        return empty

    current_occ = float(occ[-1])

    benchmark = None
    if subtype:
        defn = get_subtype_or_default(subtype)
        benchmark = defn.get("occupancy_benchmark") or defn.get("utilisation_benchmark")
    if benchmark is None:
        benchmark = 0.85
    try:
        benchmark = float(benchmark)
    except (TypeError, ValueError):
        benchmark = 0.85

    peak = float(occ.max())
    peak_idx = int(occ.argmax())
    years_since_peak = len(occ) - 1 - peak_idx

    below_count = 0
    for o in reversed(occ):
        if float(o) < benchmark * 0.85:
            below_count += 1
        else:
            break

    occ_trend = None
    if len(occ) >= 2:
        n = min(3, len(occ))
        y = np.array(occ[-n:], dtype=float)
        x = np.arange(n)
        try:
            occ_trend = float(np.polyfit(x, y, 1)[0])
        except Exception:
            occ_trend = None

    noi = None
    if "noi_rm" in past_df.columns:
        noi_series = past_df["noi_rm"].dropna().values
        if len(noi_series) >= 2:
            n = min(3, len(noi_series))
            y = np.array(noi_series[-n:], dtype=float)
            x = np.arange(n)
            try:
                noi = float(np.polyfit(x, y, 1)[0])
            except Exception:
                noi = None

    vacancy_streak = None
    if "vacancy_duration_months" in past_df.columns:
        vd = past_df["vacancy_duration_months"].dropna()
        if not vd.empty:
            vacancy_streak = float(vd.iloc[-1])

    tclass = _classify_trajectory(
        occ, peak, years_since_peak, below_count, benchmark,
    )

    return {
        "occupancy_trend_3yr": occ_trend,
        "noi_trend_3yr": noi,
        "years_below_benchmark": below_count,
        "peak_occupancy": peak,
        "years_since_peak": years_since_peak,
        "vacancy_streak_months": vacancy_streak,
        "trajectory_class": tclass,
    }


def _classify_trajectory(occ, peak, years_since_peak, below_count,
                         benchmark) -> str:
    """
    Classify an asset's trajectory from its history.
    """
    if len(occ) == 0:
        return "unknown"

    current = float(occ[-1])

    if all(float(o) < 0.05 for o in occ):
        return "never_alive"

    if len(occ) >= 2:
        prev = float(occ[-2])
        if current < prev - 0.20:
            return "rapid_decline"

    if peak > 0.70 and years_since_peak >= 2 and current < peak - 0.25:
        return "declining"

    if below_count >= 3:
        return "chronic_low"

    if len(occ) >= 3 and current > float(occ[0]) + 0.15:
        return "recovering"

    if (
        current < 0.05
        and len(occ) >= 2
        and float(occ[-2]) > 0.50
    ):
        return "recent_failure"

    return "stable"


def merge_into_asset_metrics(derived_df, existing_df, years=None):
    """
    Merge B3-derived columns into the existing asset_metrics frame.

    Phase B.1 — supports multi-year data. `derived_df` has one row per
    (asset_id, year); the existing frame is replaced row-by-row on the
    same key. Rows in `existing_df` that do not appear in `derived_df`
    are preserved unchanged.

    `years` is accepted for backwards compatibility but is not used —
    the merge is keyed on (asset_id, year) regardless of which years
    were passed.

    dtype reconciliation
    --------------------
    When a derived column is object-typed (contains strings such as
    'school' or 'stable'), the corresponding existing column must
    also be object-typed. A column read from CSV that is entirely
    empty is inferred as float64, which cannot hold a string — pandas
    raises LossySetitemError on the first write. Every derived object
    column therefore promotes its existing counterpart to object
    before the merge loop starts.
    """
    derived_cols = [
        c for c in derived_df.columns
        if c not in ("asset_id", "year")
    ]

    if "year" not in existing_df.columns:
        raise ValueError("existing asset_metrics has no 'year' column")

    existing = existing_df.copy()

    # Add any derived column that is missing from the existing frame.
    for col in derived_cols:
        if col not in existing.columns:
            existing[col] = None

    # Promote existing column dtypes to match the derived frame.
    # Object-typed derived columns (strings) require object-typed
    # existing columns; numeric derived columns leave existing dtypes
    # untouched.
    for col in derived_cols:
        if derived_df[col].dtype == object:
            if existing[col].dtype != object:
                existing[col] = existing[col].astype(object)

    existing = existing.set_index(["asset_id", "year"])

    for _, row in derived_df.iterrows():
        key = (row["asset_id"], int(row["year"]))
        if key in existing.index:
            for col in derived_cols:
                existing.at[key, col] = row[col]
        else:
            new_vals = {c: None for c in existing.columns}
            for col in derived_cols:
                new_vals[col] = row[col]
            existing.loc[key] = new_vals

    return existing.reset_index()
