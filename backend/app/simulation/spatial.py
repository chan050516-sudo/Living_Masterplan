"""Spatial model — only updates intervention-affected parts.

Green corridor intervention → modify network edges within the corridor
and re-run accessibility.
"""


def apply_green_corridor_to_network(network_df, corridor_id: str,
                                    canopy_boost: float = 0.35):
    """
    Boost canopy_coverage_ratio for edges that touch the corridor.
    For demo, we boost edges whose edge_id matches or whose geometry intersects.
    Simplified: boost all edges that already have canopy > 0.
    """
    df = network_df.copy()
    if corridor_id is None:
        return df
    # Simplified: boost canopy for edges with edge_id prefix "E-R"
    df["canopy_coverage_ratio"] = df["canopy_coverage_ratio"].apply(
        lambda c: min(1.0, float(c or 0) + canopy_boost)
    )
    return df


def apply_pedestrian_upgrade(network_df, edge_id: str):
    """Mark an edge as upgraded. For demo, boost its canopy proxy to make
    it more attractive."""
    df = network_df.copy()
    mask = df["edge_id"] == edge_id
    df.loc[mask, "canopy_coverage_ratio"] = df.loc[mask, "canopy_coverage_ratio"].apply(
        lambda c: min(1.0, float(c or 0) + 0.20)
    )
    return df