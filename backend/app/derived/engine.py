"""B3 unified entry point: compute_derived_metrics."""

import logging
from pathlib import Path

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

    # --- Assign nearest node to each asset ---
    asset_nodes = {}
    for _, asset in business["assets"].iterrows():
        parcels = geometry["parcels"]["analysis"]
        match = parcels[parcels["asset_id"] == asset["asset_id"]]
        if match.empty:
            log.warning("No parcel for asset %s", asset["asset_id"])
            continue
        node = find_nearest_node(match.iloc[0].geometry, nodes_gdf)
        asset_nodes[asset["asset_id"]] = node

    # --- Assign nearest node to each population cluster ---
    pop_analysis = geometry["population"]["analysis"]
    pop_nodes = []
    for idx, pop in pop_analysis.iterrows():
        node = find_nearest_node(pop.geometry, nodes_gdf)
        pop_nodes.append((idx, node))

    # Write nearest node back into the DataFrame (used by facility coverage)
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

    huff_results = huff_gravity(G, demand_nodes, supply_nodes, alpha=alpha, beta=beta, gamma=gamma)

    # --- Accessibility per asset ---
    d_threshold = assumptions.get("accessibility", {}).get("falloff_threshold_m", 800.0)
    demand_weighted = [(d["node"], d["population"]) for d in demand_nodes if d["node"]]
    accessibility_scores = {}
    for asset_id, node in asset_nodes.items():
        accessibility_scores[asset_id] = asset_accessibility(
            G, node, demand_weighted, d_threshold=d_threshold, gamma=gamma
        )

    # --- Maintenance surge pre-computed for commercial ---
    # (handled inside derive_commercial)

    # --- Derive metrics per asset ---
    rows = []
    for _, asset in business["assets"].iterrows():
        atype = asset["asset_type"]
        deriver = DERIVERS.get(atype)
        if deriver is None:
            log.warning("No deriver for asset_type=%s (asset %s)", atype, asset["asset_id"])
            continue

        # Attach computed walk node to the asset Series for downstream use
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
            maintenance_surge_rm=None,  # computed inside derive_commercial
            graph=G,
            year=year,
        )
        rows.append(deriver(ctx))

    return pd.DataFrame(rows)


def merge_into_asset_metrics(
    derived_df: pd.DataFrame,
    existing_df: pd.DataFrame,
    year: int,
) -> pd.DataFrame:
    """
    Overlay derived columns onto the existing asset_metrics table.
    Creates new rows if a (asset_id, year) pair does not exist.
    """
    # Columns produced by B3
    derived_cols = [c for c in derived_df.columns if c not in ("asset_id", "year")]

    # Ensure year column matches
    if "year" not in existing_df.columns:
        raise ValueError("existing asset_metrics has no 'year' column")

    # Build a lookup from existing
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