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

Phase 11 changes (2026-10-15):
  - FALLBACK_DISTANCE_M: when the walking graph cannot find a path
    between a demand node and a supply node (component fragmentation
    that survived bridge_components, or a virtual node whose segment
    ended up on a stranded branch), use a township-typical distance
    instead of dropping the supply from the competition pool.
    See the constant comment for the rationale.
  - NaN-safe attractiveness handling: `max(NaN, 0.0)` returns NaN in
    CPython, and `NaN <= 0` is False, so a single NaN attractiveness
    would poison total_u and turn every share in the pool into NaN.
"""

import math
from collections import defaultdict
from typing import Dict, List


# Fallback walking distance (metres) used when NetworkX cannot find
# a path between a demand node and a supply node.
#
# The OSM network is clipped at the township boundary, which splits
# it into several connected components. bridge_components() in
# network_graph.py connects most of them, but a few residual gaps
# may remain (virtual nodes whose segment lands on a short stranded
# branch, or a fragment farther than MAX_BRIDGE_DISTANCE_M from the
# main body). Dropping those supply nodes from the Huff pool would
# zero out the DSR for every asset that happens to sit in a
# fragment.
#
# 1500 m is roughly the average door-to-door distance across the
# Bukit Jelutong study area. It keeps the asset in the competition
# pool at a conservative cost rather than excluding it entirely.
FALLBACK_DISTANCE_M = 1500.0


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

                # NaN-safe attractiveness. `max(NaN, 0.0)` returns
                # NaN in CPython, and `NaN <= 0` is False, so a NaN
                # would slip through and poison the entire subtype
                # pool via total_u.
                raw_a = s.get("attractiveness", 0.0)
                try:
                    attractiveness = (
                        float(raw_a) if raw_a is not None else 0.0
                    )
                except (TypeError, ValueError):
                    attractiveness = 0.0
                if math.isnan(attractiveness):
                    attractiveness = 0.0
                if attractiveness <= 0:
                    continue

                d_eff = d_row.get(s_node)
                if d_eff is None:
                    # Fragmentation fallback. See FALLBACK_DISTANCE_M
                    # comment at the top of the module.
                    d_eff = FALLBACK_DISTANCE_M

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


def huff_by_subtype_per_asset(
    distance_matrix: Dict[str, Dict[str, float]],
    demand_nodes: List[Dict],
    supply_nodes: List[Dict],
    subtypes_config: Dict[str, dict],
    alpha: float = 1.0,
    beta: float = 2.0,
) -> Dict[str, Dict[str, float]]:
    """
    Huff gravity returning per-subtype demand for each asset.

    Unlike `huff_gravity_by_subtype`, which collapses the result to a
    single float per asset, this returns a nested dict:

        {asset_id: {subtype: demand_m2, ...}, ...}

    A mall with a unit_mix of {"supermarket": ..., "f_and_b": ...}
    carries one entry per subtype in the inner dict. A single-subtype
    shop carries one entry keyed by its own subtype.

    The demand pool for each subtype is independent, matching
    `huff_gravity_by_subtype`. Only the shape of the return value
    differs.
    """
    supply_by_subtype = defaultdict(list)
    for s in supply_nodes:
        st = s.get("subtype")
        if st is None:
            continue
        supply_by_subtype[st].append(s)

    result: Dict[str, Dict[str, float]] = {}

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

                raw_a = s.get("attractiveness", 0.0)
                try:
                    attractiveness = (
                        float(raw_a) if raw_a is not None else 0.0
                    )
                except (TypeError, ValueError):
                    attractiveness = 0.0
                if math.isnan(attractiveness):
                    attractiveness = 0.0
                if attractiveness <= 0:
                    continue

                d_eff = d_row.get(s_node)
                if d_eff is None:
                    d_eff = FALLBACK_DISTANCE_M

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
                result.setdefault(asset_id, {})
                result[asset_id][subtype] = (
                    result[asset_id].get(subtype, 0.0)
                    + share * subtype_demand_m2
                )

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

    Deprecated: use huff_gravity_by_subtype instead.
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

            # NaN-safe attractiveness (see huff_gravity_by_subtype).
            raw_a = s.get("attractiveness", 0.0)
            try:
                attractiveness = (
                    float(raw_a) if raw_a is not None else 0.0
                )
            except (TypeError, ValueError):
                attractiveness = 0.0
            if math.isnan(attractiveness):
                attractiveness = 0.0
            if attractiveness <= 0:
                continue

            d_eff = d_row.get(s_node)
            if d_eff is None:
                d_eff = FALLBACK_DISTANCE_M
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