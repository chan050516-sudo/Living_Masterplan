"""Tests for door-to-door catchment profile."""

import networkx as nx
from app.derived.accessibility import (
    compute_distance_matrix,
    door_to_door_distance,
    catchment_profile,
)


def _simple_graph():
    """
    Build a simple line graph:
        A --- B --- C
    All edges 100m, no canopy.
    """
    G = nx.Graph()
    G.add_edge("A", "B",
               length_m=100, effective_length_m=100, canopy=0.0, mode="walking")
    G.add_edge("B", "C",
               length_m=100, effective_length_m=100, canopy=0.0, mode="walking")
    return G


def test_door_to_door_no_off_distance():
    G = _simple_graph()
    dm = compute_distance_matrix(G)
    d = door_to_door_distance(dm, "A", 0.0, "C", 0.0)
    assert d == 200.0


def test_door_to_door_with_off_distance():
    G = _simple_graph()
    dm = compute_distance_matrix(G)
    d = door_to_door_distance(dm, "A", 15.0, "C", 20.0)
    assert d == 235.0


def test_door_to_door_unreachable():
    G = _simple_graph()
    G.add_node("X")
    dm = compute_distance_matrix(G)
    d = door_to_door_distance(dm, "A", 0.0, "X", 0.0)
    assert d is None


def test_catchment_profile_basic():
    G = _simple_graph()
    dm = compute_distance_matrix(G)

    asset_entry = {"virtual_node": "A", "off_distance": 0.0}
    demand_entries = [
        {"demand_id": "D1", "virtual_node": "B", "off_distance": 0.0, "population": 100},
        {"demand_id": "D2", "virtual_node": "C", "off_distance": 0.0, "population": 200},
    ]

    profile = catchment_profile(
        distance_matrix=dm,
        asset_entry=asset_entry,
        demand_entries=demand_entries,
        thresholds_min=[5, 10, 15],
        speed_m_per_min=80.0,  # 400m / 800m / 1200m
    )

    # D1 (100m → 1.25 min) in 5-min
    # D2 (200m → 2.5 min) in 5-min
    assert profile["catchment_population_5min"] == 300.0
    assert profile["coverage_ratio_5min"] == 1.0
    assert profile["total_catchment_population"] == 300.0


def test_catchment_profile_partial():
    G = _simple_graph()
    dm = compute_distance_matrix(G)

    asset_entry = {"virtual_node": "A", "off_distance": 0.0}
    demand_entries = [
        {"demand_id": "D1", "virtual_node": "B", "off_distance": 0.0, "population": 100},
        {"demand_id": "D2", "virtual_node": "C", "off_distance": 0.0, "population": 200},
    ]

    # Very tight thresholds: 1 min = 80m; only B is within
    profile = catchment_profile(
        distance_matrix=dm,
        asset_entry=asset_entry,
        demand_entries=demand_entries,
        thresholds_min=[1],
        speed_m_per_min=80.0,
    )

    assert profile["catchment_population_1min"] == 100.0
    assert abs(profile["coverage_ratio_1min"] - (100.0 / 300.0)) < 0.001