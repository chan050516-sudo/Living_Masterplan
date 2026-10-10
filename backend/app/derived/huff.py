"""Huff gravity model for commercial demand allocation."""

import math
from typing import List, Dict, Optional
import networkx as nx

from .accessibility import effective_distance


def huff_gravity(
    G: nx.Graph,
    demand_nodes: List[Dict],
    supply_nodes: List[Dict],
    alpha: float = 1.0,
    beta: float = 2.0,
    gamma: float = 0.3,
) -> Dict[str, float]:
    """
    demand_nodes: [{ 'population_id', 'node', 'population' }, ...]
    supply_nodes: [{ 'asset_id', 'node', 'attractiveness' }, ...]
    Returns: { asset_id: effective_demand }
    """
    effective_demand = {s["asset_id"]: 0.0 for s in supply_nodes}

    for d in demand_nodes:
        d_node = d["node"]
        pop = d.get("population", 0.0)
        if pop <= 0:
            continue

        # Compute utility for each supply
        utilities = []
        for s in supply_nodes:
            s_node = s["node"]
            if s_node is None or s_node == "":
                continue
            attractiveness = max(s.get("attractiveness", 0.0), 0.0)
            if attractiveness <= 0:
                continue

            d_eff = effective_distance(G, d_node, s_node, gamma=gamma)
            if d_eff is None or d_eff <= 0:
                # Co-located: very high utility
                d_eff = 1.0

            u = (attractiveness ** alpha) / (d_eff ** beta)
            utilities.append((s["asset_id"], u))

        total_u = sum(u for _, u in utilities)
        if total_u <= 0:
            continue

        for asset_id, u in utilities:
            share = u / total_u
            effective_demand[asset_id] += share * pop

    return effective_demand