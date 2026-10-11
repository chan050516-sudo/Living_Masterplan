"""Accessibility: door-to-door, per-mode, profile-based.

Phase 1 replaces the previous single-number accessibility_score with a
per-mode catchment profile plus door-to-door distances.

Key concepts:
  - Entry point: the projection of a geometry onto the nearest network edge.
  - Off-network distance: the gap between the geometry and its entry point.
  - Door-to-door distance: off_origin + on_network + off_destination.
  - Catchment profile: population / coverage / distance stats per threshold.
"""

import math
from typing import Optional

import networkx as nx


# ---------------------------------------------------------------
# Low-level distance
# ---------------------------------------------------------------

def effective_distance(G: nx.Graph, source: str, target: str) -> Optional[float]:
    """
    Single-pair shortest path using the graph's routing weight
    (effective_length_m for walking, length_m for driving).
    """
    if source not in G or target not in G:
        return None
    weight_col = "effective_length_m" if G.is_multigraph() or True else "length_m"
    try:
        return nx.shortest_path_length(G, source=source, target=target, weight=weight_col)
    except nx.NetworkXNoPath:
        return None


def compute_distance_matrix(G: nx.Graph) -> dict:
    """
    All-pairs shortest path using the graph's routing weight.
    Weight column is chosen from edge attributes: effective_length_m for
    walking graphs, length_m for driving graphs.
    """
    # Peek at any edge to determine which weight is present.
    weight_col = "effective_length_m"
    for _, _, data in G.edges(data=True):
        if "mode" in data and data["mode"] == "driving":
            weight_col = "length_m"
        break
    return dict(nx.all_pairs_dijkstra_path_length(G, weight=weight_col))


# ---------------------------------------------------------------
# Door-to-door distance
# ---------------------------------------------------------------

def door_to_door_distance(
    distance_matrix: dict,
    origin_vn: str,
    origin_off: float,
    dest_vn: str,
    dest_off: float,
) -> Optional[float]:
    """
    Returns origin_off + network_distance + dest_off (all metres).
    None if the two virtual nodes are unreachable from each other.
    """
    if origin_vn not in distance_matrix:
        return None
    row = distance_matrix[origin_vn]
    d_network = row.get(dest_vn)
    if d_network is None:
        return None
    return origin_off + d_network + dest_off


# ---------------------------------------------------------------
# Catchment profile
# ---------------------------------------------------------------

def catchment_profile(
    distance_matrix: dict,
    asset_entry: dict,
    demand_entries: list,
    thresholds_min: list,
    speed_m_per_min: float,
) -> dict:
    """
    Compute a full catchment profile for one asset.

    asset_entry  : {"virtual_node": vn_id, "off_distance": metres}
    demand_entries: list of dicts:
        {
          "demand_id": id,
          "virtual_node": vn_id,
          "off_distance": metres,
          "population": weight (e.g. number of residents),
        }

    Returns a dict with per-threshold counts, coverage ratios, and
    distance statistics (mean / median / p90) in metres.
    """
    empty = _empty_profile(thresholds_min)
    if asset_entry is None:
        return empty

    asset_vn = asset_entry["virtual_node"]
    asset_off = asset_entry["off_distance"]

    if asset_vn not in distance_matrix:
        return empty

    row = distance_matrix[asset_vn]

    total_pop = sum(d.get("population", 0.0) for d in demand_entries)
    if total_pop <= 0:
        return empty

    covered = {t: 0.0 for t in thresholds_min}
    reachable_pop = 0.0
    distances_weighted = []

    for d in demand_entries:
        d_vn = d["virtual_node"]
        d_off = d["off_distance"]
        pop = d.get("population", 0.0)
        if pop <= 0:
            continue

        d_network = row.get(d_vn)
        if d_network is None:
            continue

        d_total = asset_off + d_network + d_off
        reachable_pop += pop
        distances_weighted.append((d_total, pop))

        walk_time = d_total / speed_m_per_min
        for t in thresholds_min:
            if walk_time <= t:
                covered[t] += pop

    if not distances_weighted:
        return empty

    distances_weighted.sort(key=lambda x: x[0])
    mean_d = _weighted_mean(distances_weighted)
    median_d = _weighted_percentile(distances_weighted, 0.50)
    p90_d = _weighted_percentile(distances_weighted, 0.90)

    profile = {
        "total_catchment_population": total_pop,
        "reachable_population": reachable_pop,
        "mean_distance_m": mean_d,
        "median_distance_m": median_d,
        "p90_distance_m": p90_d,
    }
    for t in thresholds_min:
        profile[f"catchment_population_{t}min"] = covered[t]
        profile[f"coverage_ratio_{t}min"] = covered[t] / total_pop
    return profile


def _empty_profile(thresholds_min: list) -> dict:
    base = {
        "total_catchment_population": 0.0,
        "reachable_population": 0.0,
        "mean_distance_m": None,
        "median_distance_m": None,
        "p90_distance_m": None,
    }
    for t in thresholds_min:
        base[f"catchment_population_{t}min"] = 0.0
        base[f"coverage_ratio_{t}min"] = 0.0
    return base


def _weighted_mean(sorted_distances) -> float:
    total_w = sum(w for _, w in sorted_distances)
    if total_w <= 0:
        return 0.0
    return sum(d * w for d, w in sorted_distances) / total_w


def _weighted_percentile(sorted_distances, q: float) -> float:
    total_w = sum(w for _, w in sorted_distances)
    if total_w <= 0:
        return 0.0
    target = total_w * q
    cumulative = 0.0
    for d, w in sorted_distances:
        cumulative += w
        if cumulative >= target:
            return d
    return sorted_distances[-1][0]


# ---------------------------------------------------------------
# Compatibility helpers
# ---------------------------------------------------------------

def derive_score_from_profile(profile: dict, primary_threshold: int = 10) -> Optional[float]:
    """
    Temporary bridging function.

    Derive a single 0-100 score from the coverage ratio at a chosen
    threshold. This exists ONLY to keep the current derivers working
    during Phase 1-2 migration. It will be removed once derivers switch
    to reading the full profile.
    """
    key = f"coverage_ratio_{primary_threshold}min"
    val = profile.get(key)
    if val is None:
        return None
    return round(100.0 * val, 2)