"""Tests for canopy-adjusted walkability."""

import networkx as nx
from app.derived.accessibility import (
    effective_distance, gaussian_falloff, asset_accessibility
)


def _make_graph():
    G = nx.Graph()
    G.add_edge("A", "B", length_m=100, canopy=0.0)
    G.add_edge("B", "C", length_m=100, canopy=1.0)
    return G


def test_effective_distance_no_canopy():
    G = _make_graph()
    d = effective_distance(G, "A", "B", gamma=0.3)
    assert d == 100.0


def test_effective_distance_full_canopy():
    G = _make_graph()
    # B→C length 100, canopy 1.0 → 100 * (1 - 0.3) = 70
    d = effective_distance(G, "B", "C", gamma=0.3)
    assert abs(d - 70.0) < 0.01


def test_effective_distance_multi_edge():
    G = _make_graph()
    # A→B (100, canopy 0) + B→C (100 * 0.7 = 70) = 170
    d = effective_distance(G, "A", "C", gamma=0.3)
    assert abs(d - 170.0) < 0.01


def test_effective_distance_unreachable():
    G = nx.Graph()
    G.add_node("X")
    G.add_node("Y")
    assert effective_distance(G, "X", "Y") is None


def test_gaussian_falloff():
    # d = 0 → 1.0
    assert gaussian_falloff(0, 800) == 1.0
    # d = 800 → exp(-0.5) ≈ 0.6065
    f = gaussian_falloff(800, 800)
    assert abs(f - 0.6065) < 0.001
    # d = None → 0
    assert gaussian_falloff(None, 800) == 0.0


def test_asset_accessibility():
    G = _make_graph()
    # Single demand at B, asset at A
    # d(A→B) = 100; f = exp(-0.5 * (100/800)^2) ≈ 0.9922
    demands = [("B", 1000.0)]
    score = asset_accessibility(G, "A", demands, d_threshold=800, gamma=0.3)
    # Score ≈ 100 * 0.9922 ≈ 99.22
    assert 99.0 < score < 100.0