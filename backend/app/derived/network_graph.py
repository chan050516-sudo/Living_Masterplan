"""Build walk graph from network.geojson and find nearest nodes."""

import networkx as nx
import geopandas as gpd
from shapely.geometry import Point


def build_walk_graph(network_gdf: gpd.GeoDataFrame) -> nx.Graph:
    """
    Build undirected weighted graph.
    Node ID = from_node / to_node.
    Edge attributes: length_m, canopy_coverage_ratio, edge_id.
    """
    G = nx.Graph()
    for _, row in network_gdf.iterrows():
        u = row["from_node"]
        v = row["to_node"]
        length = float(row["length_m"])
        canopy = float(row.get("canopy_coverage_ratio", 0.0) or 0.0)
        G.add_edge(
            u, v,
            length_m=length,
            canopy=canopy,
            edge_id=row.get("edge_id"),
        )
    return G


def extract_nodes(network_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Extract unique nodes with coordinates from network edge endpoints.
    Returns GeoDataFrame in the same CRS as input.
    """
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
    Given a geometry (already in analysis CRS), return the node_id of the
    nearest node.
    """
    centroid = geom.centroid if geom.geom_type != "Point" else geom
    distances = nodes_gdf.geometry.distance(centroid)
    return nodes_gdf.loc[distances.idxmin(), "node_id"]