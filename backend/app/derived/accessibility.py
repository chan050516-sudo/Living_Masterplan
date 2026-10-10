"""Canopy-adjusted walkability with Gaussian falloff."""

import math
from typing import List, Tuple, Optional
import networkx as nx


def effective_distance(G: nx.Graph, source: str, target: str, gamma: float = 0.3) -> Optional[float]:
    """
    Shortest path where each edge contributes:
        d_eff = length_m * (1 - gamma * canopy_coverage_ratio)
    Returns None if unreachable.
    """
    if source not in G or target not in G:
        return None
    try:
        path = nx.shortest_path(G, source=source, target=target, weight="length_m")
    except nx.NetworkXNoPath:
        return None

    total = 0.0
    for u, v in zip(path[:-1], path[1:]):
        edge = G.edges[u, v]
        d_phys = edge["length_m"]
        canopy = edge.get("canopy", 0.0)
        total += d_phys * (1.0 - gamma * canopy)
    return total


def gaussian_falloff(d_effective: Optional[float], d_threshold: float) -> float:
    """Smooth decay: f(d) = exp(-0.5 * (d / d_threshold)^2)."""
    if d_effective is None:
        return 0.0
    return math.exp(-0.5 * (d_effective / d_threshold) ** 2)


def asset_accessibility(
    G: nx.Graph,
    asset_node: str,
    demand_nodes: List[Tuple[str, float]],
    d_threshold: float = 800.0,
    gamma: float = 0.3,
) -> float:
    """
    Weighted accessibility score 0-100.
    demand_nodes: list of (node_id, weight). Weight = population.
    """
    total_weight = sum(w for _, w in demand_nodes)
    if total_weight <= 0:
        return 0.0

    score = 0.0
    for node, w in demand_nodes:
        d_eff = effective_distance(G, asset_node, node, gamma=gamma)
        f = gaussian_falloff(d_eff, d_threshold)
        score += w * f

    return 100.0 * score / total_weight