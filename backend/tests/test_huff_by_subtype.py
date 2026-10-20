"""Tests for per-subtype Huff pools."""

import networkx as nx
from app.derived.huff import huff_gravity_by_subtype


def _dm():
    G = nx.Graph()
    G.add_edge("D", "A", length_m=100, effective_length_m=100, canopy=0.0)
    G.add_edge("D", "B", length_m=100, effective_length_m=100, canopy=0.0)
    G.add_edge("D", "C", length_m=100, effective_length_m=100, canopy=0.0)
    return dict(nx.all_pairs_dijkstra_path_length(G, weight="effective_length_m"))


def test_subtypes_compete_only_within_pool():
    dm = _dm()
    demand = [{"population_id": "P1", "node": "D", "population": 1000}]
    supply = [
        {"asset_id": "A", "node": "A", "attractiveness": 100, "subtype": "convenience_retail"},
        {"asset_id": "B", "node": "B", "attractiveness": 100, "subtype": "convenience_retail"},
        {"asset_id": "C", "node": "C", "attractiveness": 100, "subtype": "supermarket"},
    ]
    subtypes_config = {
        "convenience_retail": {"demand_coefficient_m2_per_person": 0.05},
        "supermarket": {"demand_coefficient_m2_per_person": 0.08},
    }
    result = huff_gravity_by_subtype(dm, demand, supply, subtypes_config)

    # A and B share the 50 m² pool (1000 * 0.05 / 2 each)
    assert abs(result["A"] - 25.0) < 0.01
    assert abs(result["B"] - 25.0) < 0.01
    # C alone gets the 80 m² pool
    assert abs(result["C"] - 80.0) < 0.01