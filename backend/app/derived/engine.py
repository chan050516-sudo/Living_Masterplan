"""B3 unified entry point: compute_derived_metrics.

Phase 2 changes:
  - Per-subtype Huff pools.
  - Per-subtype energy intensity.
  - Demographic mismatch from catchment population.
  - Neighborhood diversity via Shannon entropy.
"""

import logging
from pathlib import Path

import geopandas as gpd
import networkx as nx
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
)
from .accessibility import (
    compute_distance_matrix,
    catchment_profile,
    derive_score_from_profile,
)
from .huff import huff_gravity_by_subtype
from .demand_mismatch import aggregate_catchment_profile
from .diversity import neighborhood_diversity
from .commercial import derive_commercial
from .facility import derive_facility
from .green import derive_green
from .parcel import derive_parcel
from .residential import derive_residential

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
    network_override=None,
) -> pd.DataFrame:
    """
    Compute derived metrics for every asset at the given year.

    Parameters
    ----------
    network_override : gpd.GeoDataFrame, optional
        A modified network layer. When provided, it is used for the
        walking pipeline (canopy-adjusted cost). The driving pipeline
        always uses the original network because canopy has no physical
        effect on vehicle routing.

        B4 uses this parameter to simulate a scenario's post-
        intervention network state without duplicating B3's spatial
        pipeline.
    """
    repo_root = repo_root or Path(__file__).resolve().parents[3]
    paths = load_paths()
    assumptions = load_assumptions()
    taxonomy = get_taxonomy()
    subtypes_config = taxonomy.get("subtypes", {})

    geometry = load_geometry(repo_root, paths)
    business = load_business(repo_root, paths)

    green_blue_analysis = geometry.get("green_blue", {}).get("analysis")

    # --- Canopy coverage per asset ---
    asset_canopy = {}
    for _, asset in business["assets"].iterrows():
        aid = asset["asset_id"]
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

    # Walking may use an override network (e.g. after a spatial
    # intervention). Driving always uses the original layer.
    base_network = geometry["network"]["analysis"]
    walking_network = network_override if network_override is not None else base_network

    walking_pipeline = _prepare_mode_pipeline(
        mode="walking",
        network_gdf=walking_network,
        assets_df=business["assets"],
        parcels_gdf=geometry["parcels"]["analysis"],
        pop_gdf=pop_analysis,
        gamma=assumptions.get("accessibility", {}).get("canopy_impedance_gamma", 0.3),
        cfg=walking_cfg,
    )
    driving_pipeline = _prepare_mode_pipeline(
        mode="driving",
        network_gdf=base_network,
        assets_df=business["assets"],
        parcels_gdf=geometry["parcels"]["analysis"],
        pop_gdf=pop_analysis,
        gamma=0.0,
        cfg=driving_cfg,
    )

    # --- Huff per subtype ---
    demand_nodes_huff = _build_huff_demand_nodes(walking_pipeline)
    supply_nodes_huff = _build_huff_supply_nodes(business["assets"], walking_pipeline)
    huff_m2 = huff_gravity_by_subtype(
        walking_pipeline["distance_matrix"],
        demand_nodes_huff,
        supply_nodes_huff,
        subtypes_config=subtypes_config,
        alpha=assumptions.get("huff", {}).get("alpha", 1.0),
        beta=assumptions.get("huff", {}).get("beta", 2.0),
    )

    # --- Derive metrics per asset ---
    rows = []
    for _, asset in business["assets"].iterrows():
        atype = asset["asset_type"]
        deriver = DERIVERS.get(atype)
        if deriver is None:
            continue

        aid = asset["asset_id"]

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

        accessibility_score = derive_score_from_profile(walking_profile, primary_threshold=10)

        # Catchment population profile (age structure)
        pop_profile = aggregate_catchment_profile(
            demand_entries=walking_pipeline["demand_entries_with_age"],
            distance_matrix=walking_pipeline["distance_matrix"],
            asset_entry=walking_pipeline["asset_entries"].get(aid),
            max_distance_m=1200.0,  # 15-min walk
        )

        # Neighborhood diversity (fixed 800m radius on walking graph)
        asset_vn = walking_pipeline["asset_entries"].get(aid, {}).get("virtual_node")
        diversity_val = neighborhood_diversity(
            asset_id=aid,
            supply_nodes=supply_nodes_huff,
            distance_matrix=walking_pipeline["distance_matrix"],
            asset_vn=asset_vn,
            radius_m=DIVERSITY_RADIUS_M,
        )

        subtype = asset.get("subtype") or default_subtype_for(atype)

        # Convert m² demand back to a persons-equivalent for the
        # deprecated bridge field. Uses the subtype coefficient so that
        # the magnitude stays comparable to pre-Phase-2 numbers.
        subtype_cfg = subtypes_config.get(subtype, {})
        coeff = subtype_cfg.get("demand_coefficient_m2_per_person", 0.05) or 0.05
        effective_demand_m2 = huff_m2.get(aid)
        effective_demand_persons = (
            effective_demand_m2 / coeff
            if effective_demand_m2 is not None and coeff > 0
            else None
        )

        ctx = DerivationContext(
            asset=asset,
            business=business,
            geometry=geometry,
            assumptions=assumptions,
            accessibility_score=accessibility_score,
            huff_effective_demand=effective_demand_persons,
            huff_effective_demand_m2=effective_demand_m2,
            graph=walking_pipeline["graph"],
            year=year,
            canopy_coverage=asset_canopy.get(aid),
            distance_matrix=walking_pipeline["distance_matrix"],
            walking_profile=walking_profile,
            driving_profile=driving_profile,
            catchment_population_profile=pop_profile,
            neighborhood_diversity=diversity_val,
        )

        base_row = deriver(ctx)
        base_row = _flatten_profiles(base_row, walking_profile, driving_profile)
        rows.append(base_row)

    return pd.DataFrame(rows)


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
    """Supply nodes now carry subtype so Huff can split pools."""
    nodes = []
    for _, asset in assets_df.iterrows():
        if asset["asset_type"] != "commercial":
            continue
        aid = asset["asset_id"]
        entry = walking_pipeline["asset_entries"].get(aid)
        if entry is None:
            continue
        subtype = asset.get("subtype") or default_subtype_for(asset.get("asset_type"))
        nodes.append({
            "asset_id": aid,
            "node": entry["virtual_node"],
            "attractiveness": float(asset.get("lettable_area_m2") or 0.0),
            "subtype": subtype,
        })
    return nodes


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

    Previous implementation summed `canopy_m2` for rows whose
    asset_id matched exactly. That collapsed to 0 or 1 because OSM
    rarely tags canopy as a standalone polygon and the raw pipeline
    does not populate canopy_m2 for most rows.

    New implementation overlays the asset's geometry onto the
    green/blue layer and sums the CLIPPED intersection area, weighted
    by green_type. This yields a continuous 0-1 signal proportional
    to how much vegetation actually overlaps the parcel. It does not
    depend on asset_id matching, so it survives the "unlinked-G-xxxx"
    id mismatch problem the previous version suffered from.
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

        total_weighted = 0.0
        for _, row in candidates.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
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


def merge_into_asset_metrics(derived_df, existing_df, year):
    """
    Merge B3-derived columns into the existing asset_metrics frame.

    The existing frame was authored with a fixed set of columns. B3
    produces additional columns (catchment population, coverage ratios,
    demographic mismatch, neighborhood diversity, demand_supply_gap,
    developable_area_m2, ...) that do not appear in the authored set.
    Without expanding the schema first, the `if col in existing.columns`
    filter silently drops every one of them, which breaks B6 (its new
    flags never fire) and every downstream consumer that reads the
    enriched CSV.

    This function grows the frame's schema to include every derived
    column before writing, so no metric is lost at the boundary.
    """
    derived_cols = [c for c in derived_df.columns if c not in ("asset_id", "year")]

    if "year" not in existing_df.columns:
        raise ValueError("existing asset_metrics has no 'year' column")

    existing = existing_df.copy()

    # Grow the schema to include every derived column.
    for col in derived_cols:
        if col not in existing.columns:
            existing[col] = None

    existing = existing.set_index(["asset_id", "year"])

    for _, row in derived_df.iterrows():
        key = (row["asset_id"], year)
        if key in existing.index:
            for col in derived_cols:
                existing.at[key, col] = row[col]
        else:
            new_row = {c: None for c in existing.columns}
            new_row["asset_id"] = row["asset_id"]
            new_row["year"] = year
            for col in derived_cols:
                new_row[col] = row[col]
            existing.loc[key, list(new_row.keys())] = list(new_row.values())

    return existing.reset_index()