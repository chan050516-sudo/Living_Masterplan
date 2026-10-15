"""Build walk / drive graphs from network.geojson and find entry points.

Phase 1 changes:
  - build_graph_by_mode(): produces a mode-specific graph with the
    correct edge filter and weight column.
  - find_entry_point(): projects a geometry onto the nearest allowed edge
    and returns the projected point plus the off-network distance.
  - insert_all_entries(): batch insertion with correct edge-splitting
    order when multiple entries fall on the same edge.

Phase 11 changes (2026-10-15):
  - bridge_components(): connects disconnected walking-graph components
    with detour-adjusted edges, so Dijkstra can reach every node.
    OSM network clips split the graph into ~12 pieces; without this
    step, any asset in a minor component is unreachable from the
    demand nodes and its Huff demand / catchment metrics collapse
    to NaN.
  - build_graph_by_mode() calls bridge_components() for the walking
    mode only. Driving has a naturally well-connected main road
    network, and B4's Huff uses the walking graph exclusively.
"""

import logging
import math
from typing import Optional

import geopandas as gpd
import networkx as nx
from shapely.geometry import Point
from shapely.ops import nearest_points

log = logging.getLogger(__name__)


# ---------------------------------------------------------------
# Constants
# ---------------------------------------------------------------

WALKING_EDGE_TYPES = {
    # Explicit pedestrian infrastructure
    "footway", "pedestrian", "path", "steps", "track", "bridleway",
    "cycleway", "living_street", "service", "residential",
    "corridor", "sidewalk", "crossing", "platform",
    # Local and collector roads (pedestrians share the roadway)
    "unclassified", "road",
    "tertiary", "tertiary_link",
    "secondary", "secondary_link",
    "primary", "primary_link",
    "trunk", "trunk_link",
}

DRIVING_EDGE_TYPES = {
    "secondary", "tertiary", "residential", "service",
    "living_street", "primary", "unclassified",
}

# Detour factor applied to the straight-line distance when bridging
# two disconnected components. Pedestrians cannot walk through walls:
# 100 m straight-line normally corresponds to ~135 m of actual
# walking. 1.35 is a standard urban-planning detour ratio.
DETOUR_FACTOR = 1.35

# Maximum straight-line distance between two components that we are
# willing to bridge. Anything larger is almost certainly a real
# physical separation (motorway, river, hillside) and bridging would
# distort every downstream distance.
MAX_BRIDGE_DISTANCE_M = 500.0

# Iteration cap for the bridging loop. 20 is well above the number
# of components any township-scale graph produces.
_MAX_BRIDGE_ITER = 20


# ---------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------

def build_graph_by_mode(
    network_gdf: gpd.GeoDataFrame,
    mode: str,
    gamma: float = 0.3,
) -> nx.Graph:
    """
    Build an undirected weighted graph filtered for the given mode.

    mode = "walking": canopy-adjusted effective length as routing weight.
    mode = "driving": raw physical length as routing weight.

    Edge attributes stored on every edge:
      length_m             : physical length (m)
      effective_length_m   : walking cost = length_m * (1 - gamma * canopy)
      canopy               : canopy coverage ratio [0, 1]
      edge_id              : original edge identifier
      mode                 : "walking" or "driving"
    """
    allowed = _allowed_types_for_mode(mode)
    use_canopy = (mode == "walking")

    G = nx.Graph()
    for _, row in network_gdf.iterrows():
        etype = row.get("edge_type")

        # edge_type may be a string or a list (OSM sometimes emits lists)
        if isinstance(etype, list):
            if not any(t in allowed for t in etype):
                continue
        else:
            if etype not in allowed:
                continue

        u = row["from_node"]
        v = row["to_node"]
        length = float(row["length_m"])
        canopy = float(row.get("canopy_coverage_ratio", 0.0) or 0.0)

        if use_canopy:
            effective = length * (1.0 - gamma * canopy)
        else:
            effective = length

        # Skip self-loops: they never appear in shortest paths.
        if u == v:
            continue

        # Parallel-edge policy: keep the lowest-cost edge for the pair.
        existing = G.get_edge_data(u, v)
        if existing is not None:
            existing_eff = existing.get("effective_length_m")
            if existing_eff is not None and effective >= existing_eff:
                continue

        G.add_edge(
            u, v,
            length_m=length,
            effective_length_m=effective,
            canopy=canopy,
            edge_id=row.get("edge_id"),
            mode=mode,
        )

    # Phase 11 — bridge disconnected walking components so that every
    # node is reachable from every other node. Driving skips this.
    if mode == "walking":
        G, bridges = bridge_components(G, network_gdf)
        if bridges:
            total_eff = sum(b["effective_m"] for b in bridges)
            log.info(
                "Bridged %d disconnected walking components "
                "(total effective distance added: %.0f m)",
                len(bridges), total_eff,
            )

    return G


def bridge_components(G: nx.Graph, network_gdf: gpd.GeoDataFrame) -> tuple:
    """
    Connect every disconnected component of the walking graph.

    Algorithm
    ---------
    1. List all connected components, sorted by size (largest first).
    2. Find the closest cross-component node pair (largest vs any
       other) using Euclidean distance on the raw network geometry.
    3. If that distance is below MAX_BRIDGE_DISTANCE_M, add a bridge
       edge whose routing weight is `distance * DETOUR_FACTOR`.
    4. Repeat until the graph is fully connected or the remaining
       gap exceeds MAX_BRIDGE_DISTANCE_M.

    Why this is needed
    ------------------
    An OSM network clipped to a township boundary splits into several
    components. Nodes in a minor component are unreachable from the
    demand nodes, so Dijkstra returns None for every path between
    them. That silently kills catchment metrics, Huff demand, and
    service coverage for any asset that lands in a fragment.

    Parameters
    ----------
    G : nx.Graph
        The walking graph produced by build_graph_by_mode.
    network_gdf : gpd.GeoDataFrame
        The raw network layer, used to read node coordinates from
        edge endpoint geometries.

    Returns
    -------
    (G, bridges_added)
        G is modified in place. bridges_added is a list of dicts:
        {"from", "to", "euclidean_m", "effective_m"}.
    """
    # Extract node coordinates from edge geometries. from_node maps
    # to the first coordinate, to_node to the last.
    coords = {}
    for _, row in network_gdf.iterrows():
        try:
            geom_coords = list(row.geometry.coords)
        except (AttributeError, TypeError):
            continue
        if len(geom_coords) < 2:
            continue
        u = row.get("from_node")
        v = row.get("to_node")
        if u is not None:
            coords[u] = geom_coords[0]
        if v is not None:
            coords[v] = geom_coords[-1]

    bridges_added = []

    for _ in range(_MAX_BRIDGE_ITER):
        components = list(nx.connected_components(G))
        if len(components) <= 1:
            break

        # Sort by size descending so components[0] is the main body.
        components.sort(key=len, reverse=True)

        # Only nodes we have coordinates for can participate.
        main_nodes = [n for n in components[0] if n in coords]
        if not main_nodes:
            break

        best_pair = None
        best_dist = float("inf")

        for comp in components[1:]:
            comp_nodes = [n for n in comp if n in coords]
            for n1 in main_nodes:
                x1, y1 = coords[n1]
                for n2 in comp_nodes:
                    x2, y2 = coords[n2]
                    d = math.hypot(x1 - x2, y1 - y2)
                    if d < best_dist:
                        best_dist = d
                        best_pair = (n1, n2)

        if best_pair is None:
            break
        if best_dist > MAX_BRIDGE_DISTANCE_M:
            # Remaining gap is too large to be a walkability issue;
            # treat it as a real physical separation and stop.
            break

        n1, n2 = best_pair
        eff_dist = best_dist * DETOUR_FACTOR

        # Safety: if the pair already has an edge, skip this iteration
        # to avoid an infinite loop.
        if G.has_edge(n1, n2):
            break

        G.add_edge(
            n1, n2,
            length_m=best_dist,
            effective_length_m=eff_dist,
            canopy=0.0,
            edge_id=f"BRIDGE-{len(bridges_added):03d}",
            mode="walking",
            is_bridge=True,
        )
        bridges_added.append({
            "from": n1,
            "to": n2,
            "euclidean_m": round(best_dist, 1),
            "effective_m": round(eff_dist, 1),
        })

    return G, bridges_added


def _allowed_types_for_mode(mode: str) -> set:
    if mode == "walking":
        return WALKING_EDGE_TYPES
    if mode == "driving":
        return DRIVING_EDGE_TYPES
    raise ValueError(f"Unknown mode: {mode}")


# Backwards-compat wrapper for existing code paths
def build_walk_graph(network_gdf: gpd.GeoDataFrame, gamma: float = 0.3) -> nx.Graph:
    return build_graph_by_mode(network_gdf, mode="walking", gamma=gamma)


# ---------------------------------------------------------------
# Node extraction
# ---------------------------------------------------------------

def extract_nodes(network_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Extract unique nodes from edge endpoints."""
    nodes = {}
    for _, row in network_gdf.iterrows():
        coords = list(row.geometry.coords)
        for node_id, xy in [(row["from_node"], coords[0]),
                            (row["to_node"], coords[-1])]:
            if node_id not in nodes:
                nodes[node_id] = xy

    records = [{"node_id": nid, "geometry": Point(xy)} for nid, xy in nodes.items()]
    gdf = gpd.GeoDataFrame(records, crs=network_gdf.crs)
    return gdf


def find_nearest_node(geom, nodes_gdf: gpd.GeoDataFrame) -> str:
    """
    Given a geometry in analysis CRS, return the nearest node_id.
    Kept for backward compatibility. New code should use find_entry_point.
    """
    centroid = geom.centroid if geom.geom_type != "Point" else geom
    distances = nodes_gdf.geometry.distance(centroid)
    return nodes_gdf.loc[distances.idxmin(), "node_id"]


# ---------------------------------------------------------------
# Entry-point projection (Phase 1 core)
# ---------------------------------------------------------------

def find_entry_point(
    geom,
    network_gdf: gpd.GeoDataFrame,
    mode: str,
) -> tuple:
    """
    Project a geometry onto the nearest allowed edge.

    Returns:
        entry_point  : shapely Point in analysis CRS (or None if no edge)
        off_distance : float, distance from the geometry to the entry point (m)
        edge_id      : str, the edge that was projected onto
    """
    allowed = _allowed_types_for_mode(mode)
    walkable = network_gdf[
        network_gdf["edge_type"].apply(
            lambda t: any(x in allowed for x in t) if isinstance(t, list) else t in allowed
        )
    ]
    if walkable.empty:
        return None, None, None

    rep_point = geom.centroid if geom.geom_type != "Point" else geom

    distances = walkable.geometry.distance(rep_point)
    nearest_idx = distances.idxmin()
    nearest_edge = walkable.loc[nearest_idx]

    p_on_edge, p_on_geom = nearest_points(nearest_edge.geometry, rep_point)
    off_distance = float(p_on_geom.distance(p_on_edge))

    return p_on_edge, off_distance, nearest_edge["edge_id"]


# ---------------------------------------------------------------
# Virtual node insertion
# ---------------------------------------------------------------

def insert_all_entries(
    G: nx.Graph,
    network_gdf: gpd.GeoDataFrame,
    entries: dict,
) -> dict:
    """
    Batch-insert virtual nodes for all entries.

    entries = { entry_id: (entry_point, off_distance, edge_id) }

    Returns:
        { entry_id: {"virtual_node": vn_id, "off_distance": off_distance} }

    Grouping key is (from_node, to_node), NOT edge_id, because
    multiple edges (e.g. a pedestrian edge and a residential edge)
    may share the same node pair.
    """
    by_pair: dict = {}

    for entry_id, (point, off_d, edge_id) in entries.items():
        if point is None:
            continue

        edge_row = network_gdf[network_gdf["edge_id"] == edge_id]
        if edge_row.empty:
            continue

        edge_row = edge_row.iloc[0]
        u = edge_row["from_node"]
        v = edge_row["to_node"]
        pair_key = (u, v)

        by_pair.setdefault(pair_key, []).append((entry_id, point, off_d))

    result = {}

    for (u, v), group in by_pair.items():
        if u not in G or v not in G:
            continue
        if not G.has_edge(u, v):
            continue

        matching = network_gdf[
            (network_gdf["from_node"] == u) & (network_gdf["to_node"] == v)
        ]
        if matching.empty:
            continue
        edge_geom = matching.iloc[0].geometry
        edge_len_geom = edge_geom.length

        edge_data = G.edges[u, v]
        length_phys = edge_data["length_m"]
        effective_len = edge_data["effective_length_m"]
        canopy = edge_data["canopy"]
        mode = edge_data.get("mode", "walking")
        edge_id = edge_data.get("edge_id", f"{u}-{v}")

        effective_ratio = effective_len / length_phys if length_phys > 0 else 1.0

        def _proj_ratio(item, _geom=edge_geom, _len=edge_len_geom):
            _, point, _ = item
            if _len <= 0:
                return 0.0
            return _geom.project(point) / _len

        group.sort(key=_proj_ratio)

        G.remove_edge(u, v)

        current_anchor = u
        cumulative_ratio = 0.0

        for idx, (entry_id, point, off_d) in enumerate(group):
            ratio = _proj_ratio((entry_id, point, off_d))
            if ratio < cumulative_ratio:
                ratio = cumulative_ratio

            vn_id = f"VN-{edge_id}-{idx:03d}"

            seg_ratio = ratio - cumulative_ratio
            seg_phys = length_phys * seg_ratio
            seg_eff = seg_phys * effective_ratio

            G.add_node(vn_id)
            G.add_edge(
                current_anchor, vn_id,
                length_m=seg_phys,
                effective_length_m=seg_eff,
                canopy=canopy,
                edge_id=f"{edge_id}-seg-{idx}",
                mode=mode,
            )
            result[entry_id] = {
                "virtual_node": vn_id,
                "off_distance": float(off_d),
            }

            current_anchor = vn_id
            cumulative_ratio = ratio

        seg_ratio = 1.0 - cumulative_ratio
        seg_phys = length_phys * seg_ratio
        seg_eff = seg_phys * effective_ratio
        G.add_edge(
            current_anchor, v,
            length_m=seg_phys,
            effective_length_m=seg_eff,
            canopy=canopy,
            edge_id=f"{edge_id}-tail",
            mode=mode,
        )

    return result