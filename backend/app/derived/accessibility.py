"""Canopy-adjusted walkability with Gaussian falloff.

The canopy adjustment (Fix 1+4) is applied at graph construction time:
edges store `effective_length_m = length_m * (1 - gamma * canopy)`. All
distance queries in this module therefore use the effective weight directly.
"""

import math
from typing import List, Tuple, Optional
import networkx as nx


def effective_distance(G: nx.Graph, source: str, target: str) -> Optional[float]:
    """
    Single-pair shortest path length using the effective (canopy-adjusted)
    edge weight.

    NOTE: for batch queries, prefer a precomputed distance_matrix
    (see derived.engine._compute_distance_matrix) to avoid recomputation.
    """
    if source not in G or target not in G:
        return None
    try:
        return nx.shortest_path_length(
            G, source=source, target=target, weight="effective_length_m"
        )
    except nx.NetworkXNoPath:
        return None


def gaussian_falloff(d_effective: Optional[float], d_threshold: float) -> float:
    """Smooth decay: f(d) = exp(-0.5 * (d / d_threshold)^2)."""
    if d_effective is None:
        return 0.0
    return math.exp(-0.5 * (d_effective / d_threshold) ** 2)


def asset_accessibility(
    distance_matrix: dict,
    asset_node: str,
    demand_nodes: List[Tuple[str, float]],
    d_threshold: float = 800.0,
) -> float:
    """
    Weighted accessibility score in [0, 100].

    distance_matrix : { node: { node: effective_distance } }
                      precomputed via nx.all_pairs_dijkstra_path_length
    asset_node      : the asset's nearest walk node
    demand_nodes    : list of (node_id, weight), weight = population
    """
    if asset_node not in distance_matrix:
        return 0.0

    total_weight = sum(w for _, w in demand_nodes)
    if total_weight <= 0:
        return 0.0

    row = distance_matrix[asset_node]
    score = 0.0
    for node, w in demand_nodes:
        d_eff = row.get(node)
        f = gaussian_falloff(d_eff, d_threshold)
        score += w * f

    return 100.0 * score / total_weight