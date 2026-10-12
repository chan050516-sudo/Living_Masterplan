"""Build walk / drive graphs from network.geojson and find entry points.

Phase 1 changes:
  - build_graph_by_mode(): produces a mode-specific graph with the
    correct edge filter and weight column.
  - find_entry_point(): projects a geometry onto the nearest allowed edge
    and returns the projected point plus the off-network distance.
  - insert_all_entries(): batch insertion with correct edge-splitting
    order when multiple entries fall on the same edge.
"""

import logging
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
    "footway", "pedestrian", "path", "residential", "service",
    "living_street", "steps", "track",
}

DRIVING_EDGE_TYPES = {
    "secondary", "tertiary", "residential", "service",
    "living_street", "primary", "unclassified",
}


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
            # Accept if ANY of the types is allowed
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

        # Skip self-loops: they never appear in shortest paths, but
        # removing them keeps node extraction clean.
        if u == v:
            continue

        # ------------------------------------------------------
        # Parallel-edge policy
        # ------------------------------------------------------
        # OSM commonly maps a pedestrian path and a residential road
        # between the same two endpoints. They are distinct GeoJSON
        # features but they connect the same graph nodes. nx.Graph is
        # a simple graph, so only one edge can exist per node pair;
        # without a policy the last-seen edge silently wins and its
        # attributes overwrite the earlier one.
        #
        # We keep the lowest-cost edge. The routing weight already
        # reflects the mode's cost metric (canopy-adjusted length for
        # walking, plain length for driving), so minimising it is the
        # correct survivor for both modes.
        existing = G.get_edge_data(u, v)
        if existing is not None:
            existing_eff = existing.get("effective_length_m")
            if existing_eff is not None and effective >= existing_eff:
                # Existing edge is at least as good; keep it.
                continue

        G.add_edge(
            u, v,
            length_m=length,
            effective_length_m=effective,
            canopy=canopy,
            edge_id=row.get("edge_id"),
            mode=mode,
        )
    return G


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
# Node extraction (unchanged from before)
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
) -> tuple[Optional[Point], Optional[float], Optional[str]]:
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

    Grouping key is (from_node, to_node), NOT edge_id, because multiple
    edges (e.g. a pedestrian edge and a residential edge) may share the
    same node pair. Grouping by edge_id would cause the second group to
    find no edge (the first group already split it) and silently skip
    every entry in the second group.

    Within a group, entries are sorted by their position along the edge
    so that splitting is deterministic.
    """
    # ------------------------------------------------------------------
    # Step 1: resolve (u, v) for each entry and group by node pair
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Step 2: process each node pair
    # ------------------------------------------------------------------
    for (u, v), group in by_pair.items():
        if u not in G or v not in G:
            continue
        if not G.has_edge(u, v):
            continue

        # Use any edge geometry connecting this pair. All edges that
        # share (u, v) have the same geometry in practice; if they
        # differ, take the first one.
        matching = network_gdf[
            (network_gdf["from_node"] == u) & (network_gdf["to_node"] == v)
        ]
        if matching.empty:
            continue
        edge_geom = matching.iloc[0].geometry
        edge_len_geom = edge_geom.length

        # Read edge attributes from the augmented graph
        edge_data = G.edges[u, v]
        length_phys = edge_data["length_m"]
        effective_len = edge_data["effective_length_m"]
        canopy = edge_data["canopy"]
        mode = edge_data.get("mode", "walking")
        edge_id = edge_data.get("edge_id", f"{u}-{v}")

        effective_ratio = effective_len / length_phys if length_phys > 0 else 1.0

        # Sort entries by their position ratio along the edge
        def _proj_ratio(item, _geom=edge_geom, _len=edge_len_geom):
            _, point, _ = item
            if _len <= 0:
                return 0.0
            return _geom.project(point) / _len

        group.sort(key=_proj_ratio)

        # Remove the original edge and split progressively
        G.remove_edge(u, v)

        current_anchor = u
        cumulative_ratio = 0.0

        for idx, (entry_id, point, off_d) in enumerate(group):
            ratio = _proj_ratio((entry_id, point, off_d))
            # Guard against out-of-order ratios
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

        # Final segment back to v
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