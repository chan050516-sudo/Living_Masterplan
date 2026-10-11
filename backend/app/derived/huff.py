"""Huff gravity model for commercial demand allocation.

Uses a precomputed all-pairs distance matrix (Fix 1+4) so the gravity
computation is O(D × S) lookups instead of O(D × S) Dijkstra runs.
"""

from typing import List, Dict


def huff_gravity(
    distance_matrix: Dict[str, Dict[str, float]],
    demand_nodes: List[Dict],
    supply_nodes: List[Dict],
    alpha: float = 1.0,
    beta: float = 2.0,
) -> Dict[str, float]:
    """
    demand_nodes    : [{ 'population_id', 'node', 'population' }, ...]
    supply_nodes    : [{ 'asset_id', 'node', 'attractiveness' }, ...]
    distance_matrix : { node: { node: effective_distance } }

    Returns: { asset_id: effective_demand (persons) }
    """
    effective_demand = {s["asset_id"]: 0.0 for s in supply_nodes}

    for d in demand_nodes:
        d_node = d["node"]
        pop = d.get("population", 0.0)
        if pop <= 0:
            continue

        row = distance_matrix.get(d_node)
        if row is None:
            # Demand node is not in the walk graph; skip.
            continue

        utilities = []
        for s in supply_nodes:
            s_node = s["node"]
            if s_node is None or s_node == "":
                continue

            attractiveness = max(s.get("attractiveness", 0.0), 0.0)
            if attractiveness <= 0:
                continue

            d_eff = row.get(s_node)
            if d_eff is None:
                # Unreachable from this demand node; skip.
                continue
            if d_eff <= 0:
                # Co-located: treat as minimum positive distance.
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