"""Huff gravity model with per-subtype competition pools.

Phase 2 change: supply nodes are grouped by their business subtype.
Each subtype pool competes independently for its own demand pool.
This prevents a convenience store and a supermarket from competing
for the same trips, and stops a restaurant from competing with a
clinic.

Demand for each subtype comes from:
    subtype_demand_m2 = population * demand_coefficient_m2_per_person

The subtype's competition radius filters out supplies that are too far
to realistically compete.
"""

from collections import defaultdict
from typing import Dict, List


def huff_gravity_by_subtype(
    distance_matrix: Dict[str, Dict[str, float]],
    demand_nodes: List[Dict],
    supply_nodes: List[Dict],
    subtypes_config: Dict[str, dict],
    alpha: float = 1.0,
    beta: float = 2.0,
) -> Dict[str, float]:
    """
    Run Huff gravity independently per subtype pool.

    demand_nodes : [{"population_id", "node", "population"}, ...]
    supply_nodes : [{"asset_id", "node", "attractiveness", "subtype"}, ...]
    subtypes_config : taxonomy["subtypes"], provides per-subtype
                      demand_coefficient_m2_per_person and competition_radius_m.

    Returns: { asset_id: effective_demand_m2 }
    """
    # Group supplies by subtype
    supply_by_subtype = defaultdict(list)
    for s in supply_nodes:
        st = s.get("subtype")
        if st is None:
            continue
        supply_by_subtype[st].append(s)

    result: Dict[str, float] = {}

    for subtype, supplies in supply_by_subtype.items():
        cfg = subtypes_config.get(subtype, {})
        coefficient = cfg.get("demand_coefficient_m2_per_person", 0.05)
        radius = cfg.get("competition_radius_m")

        for d in demand_nodes:
            d_node = d["node"]
            d_pop = d.get("population", 0.0)
            if d_pop <= 0:
                continue

            d_row = distance_matrix.get(d_node)
            if d_row is None:
                continue

            subtype_demand_m2 = d_pop * coefficient

            utilities = []
            for s in supplies:
                s_node = s["node"]
                if s_node is None or s_node == "":
                    continue
                attractiveness = max(s.get("attractiveness", 0.0), 0.0)
                if attractiveness <= 0:
                    continue

                d_eff = d_row.get(s_node)
                if d_eff is None:
                    continue

                # Competition radius filter (per subtype)
                if radius is not None and d_eff > radius:
                    continue

                if d_eff <= 0:
                    d_eff = 1.0

                u = (attractiveness ** alpha) / (d_eff ** beta)
                utilities.append((s["asset_id"], u))

            total_u = sum(u for _, u in utilities)
            if total_u <= 0:
                continue

            for asset_id, u in utilities:
                share = u / total_u
                result[asset_id] = result.get(asset_id, 0.0) + share * subtype_demand_m2

    return result


def huff_gravity(
    distance_matrix: Dict[str, Dict[str, float]],
    demand_nodes: List[Dict],
    supply_nodes: List[Dict],
    alpha: float = 1.0,
    beta: float = 2.0,
) -> Dict[str, float]:
    """
    Legacy entry point kept for backward compatibility.

    Deprecated: use huff_gravity_by_subtype instead. This version treats
    all supplies as one homogeneous pool and is only kept so that any
    remaining callers continue to work during the Phase 2-3 migration.
    """
    effective_demand = {s["asset_id"]: 0.0 for s in supply_nodes}

    for d in demand_nodes:
        d_node = d["node"]
        pop = d.get("population", 0.0)
        if pop <= 0:
            continue

        d_row = distance_matrix.get(d_node)
        if d_row is None:
            continue

        utilities = []
        for s in supply_nodes:
            s_node = s["node"]
            if s_node is None or s_node == "":
                continue
            attractiveness = max(s.get("attractiveness", 0.0), 0.0)
            if attractiveness <= 0:
                continue
            d_eff = d_row.get(s_node)
            if d_eff is None:
                continue
            if d_eff <= 0:
                d_eff = 1.0
            u = (attractiveness ** alpha) / (d_eff ** beta)
            utilities.append((s["asset_id"], u))

        total_u = sum(u for _, u in utilities)
        if total_u <= 0:
            continue

        for asset_id, u in utilities:
            effective_demand[asset_id] += (u / total_u) * pop

    return effective_demand