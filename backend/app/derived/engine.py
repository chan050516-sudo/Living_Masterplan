"""B3 unified entry point: compute_derived_metrics."""

import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd

from ..config import load_paths, load_benchmarks, load_assumptions
from ..loaders.geometry_loader import load_geometry
from ..loaders.business_loader import load_business
from .context import DerivationContext
from .network_graph import build_walk_graph, extract_nodes, find_nearest_node
from .accessibility import asset_accessibility
from .huff import huff_gravity
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


def _compute_canopy_coverage(
    asset_id: str,
    asset_geom,
    green_blue_gdf: gpd.GeoDataFrame,
    land_area_m2,
) -> float:
    """
    Compute the canopy coverage ratio [0, 1] for a single asset.

    Strategy:
      1. If green_blue has features explicitly tagged with this asset_id,
         use them. (Typical for green space assets which own their polygon.)
      2. Otherwise, spatially clip green_blue features to the asset's geometry.
         (Typical for commercial/facility assets with trees in the same plot.)

    Returns None when inputs are missing or land_area is invalid.

    Note: The strategy is data-driven. When the input dataset changes,
    the same logic applies; no asset-specific hardcoding.
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

    canopy_m2 = 0.0
    has_data = False

    # Strategy 1: explicit asset_id match in green_blue
    if "asset_id" in green_blue_gdf.columns:
        by_id = green_blue_gdf[green_blue_gdf["asset_id"] == asset_id]
        if not by_id.empty:
            canopy_m2 = float(by_id["canopy_m2"].fillna(0).sum())
            has_data = True

    # Strategy 2: spatial overlay against the asset's polygon
    if not has_data and asset_geom is not None:
        try:
            clipped = gpd.clip(green_blue_gdf, asset_geom)
            if not clipped.empty:
                canopy_m2 = float(clipped["canopy_m2"].fillna(0).sum())
                has_data = True
        except Exception as e:
            log.warning("Canopy overlay failed for %s: %s", asset_id, e)

    if not has_data:
        return None

    return min(1.0, canopy_m2 / land_area_f)


def compute_derived_metrics(repo_root: Path = None, year: int = 2026) -> pd.DataFrame:
    """
    Load all data, compute derived metrics for every asset, return a DataFrame
    ready to merge back into asset_metrics.csv.
    """
    repo_root = repo_root or Path(__file__).resolve().parents[3]
    paths = load_paths()
    benchmarks = load_benchmarks()
    assumptions = load_assumptions()

    geometry = load_geometry(repo_root, paths)
    business = load_business(repo_root, paths)

    # --- Walk graph ---
    network_analysis = geometry["network"]["analysis"]
    G = build_walk_graph(network_analysis)
    nodes_gdf = extract_nodes(network_analysis)

    # --- Green/blue layer for canopy computation ---
    green_blue_analysis = geometry.get("green_blue", {}).get("analysis")

    # --- Assign nearest node to each asset + compute canopy ---
    asset_nodes = {}
    asset_canopy = {}
    for _, asset in business["assets"].iterrows():
        aid = asset["asset_id"]

        parcels = geometry["parcels"]["analysis"]
        match = parcels[parcels["asset_id"] == aid]
        if match.empty:
            log.warning("No parcel for asset %s", aid)
            continue

        asset_geom = match.iloc[0].geometry

        # Nearest walk node
        asset_nodes[aid] = find_nearest_node(asset_geom, nodes_gdf)

        # Canopy coverage (P0.4)
        asset_canopy[aid] = _compute_canopy_coverage(
            asset_id=aid,
            asset_geom=asset_geom,
            green_blue_gdf=green_blue_analysis,
            land_area_m2=asset.get("land_area_m2"),
        )

    # --- Assign nearest node to each population cluster ---
    pop_analysis = geometry["population"]["analysis"]
    pop_nodes = []
    for idx, pop in pop_analysis.iterrows():
        node = find_nearest_node(pop.geometry, nodes_gdf)
        pop_nodes.append((idx, node))

    for idx, node in pop_nodes:
        pop_analysis.at[idx, "_nearest_node"] = node

    # --- Demand nodes for Huff / accessibility ---
    demand_nodes = []
    for _, pop in pop_analysis.iterrows():
        demand_nodes.append({
            "population_id": pop["population_id"],
            "node": pop["_nearest_node"],
            "population": float(pop["total_population"]),
        })

    # --- Supply nodes for Huff ---
    supply_nodes = []
    for _, asset in business["assets"].iterrows():
        if asset["asset_type"] != "commercial":
            continue
        supply_nodes.append({
            "asset_id": asset["asset_id"],
            "node": asset_nodes.get(asset["asset_id"]),
            "attractiveness": float(asset.get("lettable_area_m2") or 0.0),
        })

    # --- Huff gravity ---
    gamma = assumptions.get("accessibility", {}).get("canopy_impedance_gamma", 0.3)
    alpha = assumptions.get("huff", {}).get("alpha", 1.0)
    beta = assumptions.get("huff", {}).get("beta", 2.0)

    huff_results = huff_gravity(
        G, demand_nodes, supply_nodes, alpha=alpha, beta=beta, gamma=gamma,
    )

    # --- Accessibility per asset ---
    d_threshold = assumptions.get("accessibility", {}).get("falloff_threshold_m", 800.0)
    demand_weighted = [(d["node"], d["population"]) for d in demand_nodes if d["node"]]
    accessibility_scores = {}
    for asset_id, node in asset_nodes.items():
        accessibility_scores[asset_id] = asset_accessibility(
            G, node, demand_weighted, d_threshold=d_threshold, gamma=gamma,
        )

    # --- Derive metrics per asset ---
    rows = []
    for _, asset in business["assets"].iterrows():
        atype = asset["asset_type"]
        deriver = DERIVERS.get(atype)
        if deriver is None:
            log.warning("No deriver for asset_type=%s (asset %s)", atype, asset["asset_id"])
            continue

        asset = asset.copy()
        asset["_walk_node"] = asset_nodes.get(asset["asset_id"])

        ctx = DerivationContext(
            asset=asset,
            business=business,
            geometry=geometry,
            benchmarks=benchmarks,
            assumptions=assumptions,
            accessibility_score=accessibility_scores.get(asset["asset_id"]),
            huff_effective_demand=huff_results.get(asset["asset_id"]),
            maintenance_surge_rm=None,
            graph=G,
            year=year,
            canopy_coverage=asset_canopy.get(asset["asset_id"]),
        )
        rows.append(deriver(ctx))

    return pd.DataFrame(rows)


def merge_into_asset_metrics(
    derived_df: pd.DataFrame,
    existing_df: pd.DataFrame,
    year: int,
) -> pd.DataFrame:
    """Overlay derived columns onto the existing asset_metrics table."""
    derived_cols = [c for c in derived_df.columns if c not in ("asset_id", "year")]

    if "year" not in existing_df.columns:
        raise ValueError("existing asset_metrics has no 'year' column")

    existing = existing_df.copy()
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
                if col in new_row:
                    new_row[col] = row[col]
            existing.loc[key, list(new_row.keys())] = list(new_row.values())

    return existing.reset_index()