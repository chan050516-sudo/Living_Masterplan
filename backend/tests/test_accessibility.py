"""Tests for canopy-adjusted walkability."""

import networkx as nx
from app.derived.accessibility import (
    effective_distance, gaussian_falloff, asset_accessibility,
)
from app.derived.network_graph import build_walk_graph


def _make_graph_via_builder():
    """Build using the real edge weight logic."""
    import geopandas as gpd
    from shapely.geometry import LineString

    rows = [
        {"edge_id": "E1", "from_node": "A", "to_node": "B",
         "length_m": 100, "canopy_coverage_ratio": 0.0},
        {"edge_id": "E2", "from_node": "B", "to_node": "C",
         "length_m": 100, "canopy_coverage_ratio": 1.0},
    ]
    gdf = gpd.GeoDataFrame(
        rows,
        geometry=[LineString([(0, 0), (1, 0)]), LineString([(1, 0), (1, 1)])],
        crs="EPSG:4326",
    )
    return build_walk_graph(gdf, gamma=0.3)


def test_effective_distance_no_canopy():
    G = _make_graph_via_builder()
    d = effective_distance(G, "A", "B")
    assert d == 100.0


def test_effective_distance_full_canopy():
    G = _make_graph_via_builder()
    # B->C length 100, canopy 1.0 -> effective = 100 * 0.7 = 70
    d = effective_distance(G, "B", "C")
    assert abs(d - 70.0) < 0.01


def test_effective_distance_prefers_shaded_route():
    """
    Fix 1+4 semantic test: a shaded longer path should be preferred over
    an unshaded shorter path when the effective cost is lower.
    """
    G = nx.Graph()
    # Route 1: unshaded, total 100 m
    G.add_edge("A", "X", effective_length_m=50, length_m=50, canopy=0.0)
    G.add_edge("X", "B", effective_length_m=50, length_m=50, canopy=0.0)
    # Route 2: shaded, physical 160 m but effective = 160 * 0.7 = 112 m
    # (still longer than Route 1 at 100 m)
    # Modify to make shaded path shorter in effective terms:
    G.clear()
    # Route 1: unshaded, 200 m effective
    G.add_edge("A", "X", effective_length_m=200, length_m=200, canopy=0.0)
    G.add_edge("X", "B", effective_length_m=0, length_m=0, canopy=0.0)
    # Route 2: shaded, physical 150 m -> effective 105 m
    G.add_edge("A", "Y", effective_length_m=52.5, length_m=75, canopy=1.0)
    G.add_edge("Y", "B", effective_length_m=52.5, length_m=75, canopy=1.0)

    d = effective_distance(G, "A", "B")
    # Should pick Route 2 because effective is smaller
    assert abs(d - 105.0) < 0.01


def test_effective_distance_unreachable():
    G = nx.Graph()
    G.add_node("X")
    G.add_node("Y")
    assert effective_distance(G, "X", "Y") is None


def test_gaussian_falloff():
    assert gaussian_falloff(0, 800) == 1.0
    f = gaussian_falloff(800, 800)
    assert abs(f - 0.6065) < 0.001
    assert gaussian_falloff(None, 800) == 0.0


def test_asset_accessibility():
    G = _make_graph_via_builder()
    distance_matrix = dict(
        nx.all_pairs_dijkstra_path_length(G, weight="effective_length_m")
    )
    demands = [("B", 1000.0)]
    score = asset_accessibility(
        distance_matrix, "A", demands, d_threshold=800,
    )
    assert 99.0 < score < 100.0