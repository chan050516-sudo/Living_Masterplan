"""Tests for Huff gravity model."""

import networkx as nx
from app.derived.huff import huff_gravity


def _distance_matrix_from_graph(G):
    return dict(nx.all_pairs_dijkstra_path_length(G, weight="effective_length_m"))


def _graph_two_suppliers():
    G = nx.Graph()
    G.add_edge("D", "A", effective_length_m=100, length_m=100, canopy=0.0)
    G.add_edge("D", "B", effective_length_m=400, length_m=400, canopy=0.0)
    return G


def test_huff_two_suppliers():
    G = _graph_two_suppliers()
    m = _distance_matrix_from_graph(G)
    demand = [{"population_id": "POP-1", "node": "D", "population": 1000}]
    supply = [
        {"asset_id": "A-close", "node": "A", "attractiveness": 100},
        {"asset_id": "B-far", "node": "B", "attractiveness": 100},
    ]
    result = huff_gravity(m, demand, supply, alpha=1.0, beta=2.0)
    assert result["A-close"] > result["B-far"]
    assert abs(result["A-close"] + result["B-far"] - 1000) < 1.0


def test_huff_no_demand():
    G = _graph_two_suppliers()
    m = _distance_matrix_from_graph(G)
    result = huff_gravity(m, [], [{"asset_id": "A", "node": "A", "attractiveness": 100}])
    assert result["A"] == 0.0


def test_huff_zero_attractiveness():
    G = _graph_two_suppliers()
    m = _distance_matrix_from_graph(G)
    demand = [{"population_id": "POP-1", "node": "D", "population": 1000}]
    supply = [
        {"asset_id": "A", "node": "A", "attractiveness": 0},
        {"asset_id": "B", "node": "B", "attractiveness": 100},
    ]
    result = huff_gravity(m, demand, supply)
    assert result["A"] == 0.0
    assert result["B"] > 0


def test_huff_unreachable_supplier_skipped():
    """Suppliers not reachable from a demand node should be skipped, not crash."""
    G = nx.Graph()
    G.add_edge("D", "A", effective_length_m=100, length_m=100, canopy=0.0)
    G.add_node("B")  # Isolated
    m = _distance_matrix_from_graph(G)
    demand = [{"population_id": "POP-1", "node": "D", "population": 1000}]
    supply = [
        {"asset_id": "A", "node": "A", "attractiveness": 100},
        {"asset_id": "B", "node": "B", "attractiveness": 100},  # Unreachable
    ]
    result = huff_gravity(m, demand, supply, alpha=1.0, beta=2.0)
    # All demand should go to A
    assert abs(result["A"] - 1000.0) < 0.01
    assert result["B"] == 0.0