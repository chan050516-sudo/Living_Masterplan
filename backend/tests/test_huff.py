"""Tests for Huff gravity model."""

import networkx as nx
from app.derived.huff import huff_gravity


def _graph_two_suppliers():
    G = nx.Graph()
    # demand node D at start
    # supplier A close (100m), supplier B far (400m)
    G.add_edge("D", "A", length_m=100, canopy=0.0)
    G.add_edge("D", "B", length_m=400, canopy=0.0)
    return G


def test_huff_two_suppliers():
    G = _graph_two_suppliers()
    demand = [{"population_id": "POP-1", "node": "D", "population": 1000}]
    supply = [
        {"asset_id": "A-close", "node": "A", "attractiveness": 100},
        {"asset_id": "B-far", "node": "B", "attractiveness": 100},
    ]
    result = huff_gravity(G, demand, supply, alpha=1.0, beta=2.0, gamma=0.3)
    # A is closer → should get more
    assert result["A-close"] > result["B-far"]
    # Total should equal population
    assert abs(result["A-close"] + result["B-far"] - 1000) < 1.0


def test_huff_no_demand():
    G = _graph_two_suppliers()
    demand = []
    supply = [{"asset_id": "A", "node": "A", "attractiveness": 100}]
    result = huff_gravity(G, demand, supply)
    assert result["A"] == 0.0


def test_huff_zero_attractiveness():
    G = _graph_two_suppliers()
    demand = [{"population_id": "POP-1", "node": "D", "population": 1000}]
    supply = [
        {"asset_id": "A", "node": "A", "attractiveness": 0},
        {"asset_id": "B", "node": "B", "attractiveness": 100},
    ]
    result = huff_gravity(G, demand, supply)
    assert result["A"] == 0.0
    assert result["B"] > 0