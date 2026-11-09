"""Spatial intervention application.

Spatial interventions (pedestrian_upgrade, green_corridor) modify the
walking network rather than any asset's own attributes. Applying them
means raising the canopy_coverage_ratio on target edges, which lowers
the canopy-adjusted walking cost on those edges and, through the
network graph, improves accessibility for any asset whose door-to-door
paths traverse them.

The output of this module is a modified network GeoDataFrame. B3's
compute_derived_metrics accepts such an override via its
`network_override` parameter; B4 uses that to simulate the
post-intervention network state for years after activation.

Target resolution
-----------------
An intervention's target may be:
  1. An explicit edge id in parameters_json (edge_id / edge_ids).
  2. An edge id passed as target_asset_id (the mock data does this).
  3. An asset id. The LLM reasoning layer knows assets, not edges, so
     this is the common case in production. The target is resolved by
     projecting the asset's parcel centroid onto the network and
     returning the nearest edge.
This chain makes a user-initiated "improve the walk to B-03" request
land on the correct edge without the LLM needing edge-level knowledge.

Design notes:
  - Interventions are cumulative. Once activated in year Y they remain
    in effect for every later year.
  - The canopy boost is additive on canopy_coverage_ratio and clipped
    at 1.0. The default boost depends on the intervention type; it can
    be overridden per-intervention through parameters_json.
"""

import json
import logging

from ..derived.network_graph import WALKING_EDGE_TYPES

log = logging.getLogger(__name__)


# Default canopy boost added on top of existing canopy. Clipped to 1.0.
DEFAULT_CANOPY_BOOST = {
    "pedestrian_upgrade": 0.20,
    "green_corridor":     0.35,
}


def spatial_interventions_for_year(scenario_interventions, year):
    """
    Return the list of spatial interventions that have activated by
    `year` (activation_year <= year).

    Interventions are cumulative: once activated they remain in effect
    for every later year. Returns a list of plain dicts.
    """
    if scenario_interventions is None or scenario_interventions.empty:
        return []

    active = []
    for _, intv in scenario_interventions.iterrows():
        itype = intv.get("intervention_type")
        if itype not in ("pedestrian_upgrade", "green_corridor"):
            continue

        activation = intv.get("activation_year")
        if activation is None:
            continue
        try:
            if int(activation) > year:
                continue
        except (TypeError, ValueError):
            continue

        active.append(intv.to_dict())
    return active


def network_version_tag(active_spatial):
    """
    Stable, order-independent tag describing the network state produced
    by a set of active spatial interventions.

    The tag MUST vary whenever the network geometry could differ. Two
    interventions with the same intervention_id but different
    parameters (e.g. pedestrian_upgrade with canopy_boost=0.20 vs
    green_corridor with canopy_boost=0.35) produce different networks,
    so the tag must distinguish them.

    Previously the tag was keyed only on intervention_id. Different
    candidates in the same B7 run renumbered their interventions from
    INT-LLM-001, so two structurally different interventions collided
    on the same tag, and the second candidate silently reused the
    first candidate's pipeline.
    """
    import json as _json
    import hashlib as _hashlib

    if not active_spatial:
        return "base"

    parts = []
    for intv in active_spatial:
        iid = intv.get("intervention_id") or intv.get("target_asset_id") or "?"
        target = intv.get("target_asset_id") or "?"
        itype = intv.get("intervention_type") or "?"
        params = intv.get("parameters_json") or "{}"
        parts.append(f"{iid}|{target}|{itype}|{params}")
    parts.sort()

    digest = _hashlib.md5("||".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"post_{digest}"


def apply_spatial_interventions(network_gdf, active_spatial, parcels_gdf=None,
                                assets_df=None):
    """
    Return a copy of `network_gdf` with `canopy_coverage_ratio` adjusted
    on the edges targeted by the given spatial interventions.

    If `active_spatial` is empty, the input is returned unchanged.

    Parameters
    ----------
    network_gdf : gpd.GeoDataFrame
        The walking network layer.
    active_spatial : list[dict]
        Interventions returned by spatial_interventions_for_year.
    parcels_gdf : gpd.GeoDataFrame, optional
        Parcels layer, used to resolve asset-id targets to their
        nearest edge. When omitted, asset-id targets fall through to
        the legacy "use the id as an edge id" behaviour.
    assets_df : pd.DataFrame, optional
        Asset table. Lets an asset that shares a parcel (terrace rows,
        shop rows) be found through its own `parcel_id`; the parcel
        layer's `asset_id` column names only one asset per parcel.

    The adjustment is additive on canopy: an edge with existing canopy
    of 0.10 receiving a +0.20 boost becomes 0.30. Values are clipped at
    1.0. The boost is resolved in this order:
      1. params["canopy_boost"]         per-intervention override
      2. DEFAULT_CANOPY_BOOST[type]     type default
      3. 0.20                           hard fallback
    """
    if not active_spatial:
        return network_gdf

    df = network_gdf.copy()
    if "canopy_coverage_ratio" not in df.columns:
        log.warning(
            "network layer missing canopy_coverage_ratio; "
            "spatial interventions will have no effect"
        )
        return df

    df["canopy_coverage_ratio"] = (
        df["canopy_coverage_ratio"].fillna(0.0).astype(float)
    )

    for intv in active_spatial:
        itype = intv.get("intervention_type")
        try:
            params = json.loads(intv.get("parameters_json") or "{}")
        except (json.JSONDecodeError, TypeError):
            params = {}

        boost = params.get("canopy_boost")
        if boost is None:
            boost = DEFAULT_CANOPY_BOOST.get(itype, 0.20)
        try:
            boost = float(boost)
        except (TypeError, ValueError):
            boost = DEFAULT_CANOPY_BOOST.get(itype, 0.20)

        target_edges = _resolve_target_edges(
            intv, params, network_gdf=df, parcels_gdf=parcels_gdf,
            assets_df=assets_df,
        )
        if not target_edges:
            log.info(
                "Spatial intervention %s has no resolvable target edges; skipped.",
                intv.get("intervention_id"),
            )
            continue

        # A flow-island asset is cut off by a highway, wall or drain.
        # Shade alone cannot fix that, so `new_link` adds one short
        # footway (a crossing or footbridge) to the nearest node that
        # is close in a straight line but far along the streets.
        if params.get("new_link"):
            df = add_access_link(
                df, intv, params, parcels_gdf=parcels_gdf,
                assets_df=assets_df,
            )

        mask = df["edge_id"].isin(target_edges)
        if not mask.any():
            log.info(
                "Spatial intervention %s targets no edge present in the "
                "network (targets=%s).",
                intv.get("intervention_id"), target_edges,
            )
            continue

        df.loc[mask, "canopy_coverage_ratio"] = (
            df.loc[mask, "canopy_coverage_ratio"] + boost
        ).clip(upper=1.0)

    return df


def _resolve_target_edges(intv, params, network_gdf=None, parcels_gdf=None,
                          assets_df=None):
    """
    Determine which network edge ids an intervention affects.

    Resolution order:
      1. params["edge_id"]        single edge id
      2. params["edge_ids"]       list of edge ids
      3. target_asset_id already present as an edge id
      4. target_asset_id is an asset id: project the asset's parcel
         centroid onto the network and use the nearest edge
      5. Legacy fallback: return the raw target unchanged
    """
    if params.get("edge_id"):
        return [str(params["edge_id"])]
    if params.get("edge_ids"):
        ids = params["edge_ids"]
        if isinstance(ids, str):
            return [ids]
        return [str(x) for x in ids]

    target = intv.get("target_asset_id")
    if not target:
        return []
    target_str = str(target)

    # The target may already be an edge id present in the network.
    if network_gdf is not None and "edge_id" in network_gdf.columns:
        edge_ids = set(network_gdf["edge_id"].astype(str))
        if target_str in edge_ids:
            return [target_str]

    # The target is an asset id (the LLM's natural vocabulary). Resolve
    # it to the nearest edge via the asset's parcel.
    if network_gdf is not None and parcels_gdf is not None:
        nearest = _find_edges_near_asset(
            target_str, network_gdf, parcels_gdf, assets_df=assets_df,
        )
        if nearest:
            log.info(
                "Spatial intervention %s: asset %s resolved to nearest "
                "edge(s) %s.",
                intv.get("intervention_id"), target_str, nearest,
            )
            return nearest

    # Legacy best-effort: treat the raw target as an edge id.
    return [target_str]


# Shortest straight-line gap a new link may close, and how much longer
# the existing street route must be for the gap to count as a barrier.
DEFAULT_LINK_MAX_M = 150.0
DETOUR_RATIO_MIN = 3.0


def add_access_link(df, intv, params, parcels_gdf=None, assets_df=None):
    """
    Return `df` with one new footway edge that reconnects an asset to
    nearby footfall it is cut off from.

    The edge starts at the walking node nearest the asset and ends at
    the node, within `link_max_m` (default 150 m) in a straight line,
    whose current walking route is the longest relative to that
    straight line (at least DETOUR_RATIO_MIN times longer). If no node
    qualifies, the network is returned unchanged: there is no barrier
    a short link could fix.
    """
    import geopandas as gpd
    import networkx as nx
    import pandas as pd
    from shapely.geometry import LineString, Point

    if df.crs is None or not df.crs.is_projected:
        log.warning("add_access_link needs a projected network; skipped.")
        return df
    geom = asset_geometry(intv.get("target_asset_id"), parcels_gdf, assets_df)
    if geom is None:
        return df
    try:
        max_m = float(params.get("link_max_m") or DEFAULT_LINK_MAX_M)
    except (TypeError, ValueError):
        max_m = DEFAULT_LINK_MAX_M

    walk = df[df["edge_type"].isin(WALKING_EDGE_TYPES)]
    coords = {}
    G = nx.Graph()
    for _, row in walk.iterrows():
        g = row.geometry
        if g is None or g.is_empty:
            continue
        cs = list(g.coords)
        coords.setdefault(row["from_node"], cs[0])
        coords.setdefault(row["to_node"], cs[-1])
        if row["from_node"] != row["to_node"]:
            G.add_edge(row["from_node"], row["to_node"],
                       w=float(row["length_m"]))
    if not coords:
        return df

    centre = geom.centroid
    start = min(coords, key=lambda n: Point(coords[n]).distance(centre))
    sp = Point(coords[start])
    reach = nx.single_source_dijkstra_path_length(
        G, start, cutoff=max_m * 20, weight="w",
    ) if start in G else {}

    # Pick the gap whose closure saves the most walking: the largest
    # (street route - straight line), among nodes the streets reach
    # only by a detour of at least DETOUR_RATIO_MIN. A node the
    # streets never reach (another network component) counts as a
    # saving of the full search radius.
    unreachable_saving = max_m * 20
    best, best_ratio, best_saving = None, None, 0.0
    for node, xy in coords.items():
        if node == start:
            continue
        d = sp.distance(Point(xy))
        if d < 10.0 or d > max_m:
            continue
        net = reach.get(node)
        ratio = float("inf") if net is None else net / d
        if ratio < DETOUR_RATIO_MIN:
            continue
        saving = unreachable_saving if net is None else net - d
        if saving > best_saving:
            best, best_ratio, best_saving = node, ratio, saving
    if best is None:
        log.info("Spatial intervention %s: no cut-off node within %.0f m; "
                 "no link added.", intv.get("intervention_id"), max_m)
        return df

    line = LineString([coords[start], coords[best]])
    eid = f"E-LINK-{intv.get('intervention_id') or intv.get('target_asset_id')}"
    new = {c: None for c in df.columns}
    new.update({
        "id": eid, "edge_id": eid, "edge_type": "footway",
        "highway_raw": "footway", "walk_ok": True, "drive_ok": False,
        "from_node": start, "to_node": best, "length_m": line.length,
        "walk_speed_kmh": 4.5, "access_type": "public",
        "canopy_coverage_ratio": 0.0, "geometry": line,
    })
    log.info("Spatial intervention %s: added %.0f m link %s -> %s "
             "(street route was %s).", intv.get("intervention_id"),
             line.length, start, best,
             "none" if best_ratio == float("inf") else f"{best_ratio:.1f}x longer")
    out = pd.concat([df, gpd.GeoDataFrame([new], geometry="geometry", crs=df.crs)],
                    ignore_index=True)
    return gpd.GeoDataFrame(out, geometry="geometry", crs=df.crs)


def asset_geometry(asset_id, parcels_gdf, assets_df=None):
    """
    The parcel geometry an asset sits on, resolved the same way B3 does:
    first the parcel layer's own `asset_id` back-reference, then the
    asset's `parcel_id` (shared parcels hold several assets but name
    only one of them). Returns None when neither resolves.
    """
    if parcels_gdf is None or getattr(parcels_gdf, "empty", True):
        return None
    if "asset_id" in parcels_gdf.columns:
        match = parcels_gdf[parcels_gdf["asset_id"] == asset_id]
        if not match.empty:
            geom = match.iloc[0].geometry
            if geom is not None and not geom.is_empty:
                return geom
    if assets_df is None or "parcel_id" not in parcels_gdf.columns:
        return None
    row = assets_df[assets_df["asset_id"] == asset_id]
    if row.empty:
        return None
    pid = row.iloc[0].get("parcel_id")
    if pid is None or (isinstance(pid, float) and pid != pid):
        return None
    pmatch = parcels_gdf[parcels_gdf["parcel_id"] == pid]
    if pmatch.empty:
        return None
    geom = pmatch.iloc[0].geometry
    return None if geom is None or geom.is_empty else geom


def _find_edges_near_asset(asset_id, network_gdf, parcels_gdf, max_edges=5,
                           assets_df=None):
    """
    Return the edge id(s) nearest to the given asset's parcel centroid.

    Parallel edges are common in OSM (a pedestrian path and a
    residential road connecting the same two nodes, geometrically
    identical). Selecting only the single nearest edge risks picking
    the wrong one when distances tie, which would raise canopy on an
    edge the walking graph later discards in favour of its parallel
    counterpart.

    To avoid this, the function returns up to `max_edges` candidate
    edges and prefers walking-eligible types. Each candidate is
    treated as a target by the caller, so the intervention reaches
    whichever parallel edge actually survives graph construction.
    """
    if network_gdf is None or parcels_gdf is None:
        return []
    if "asset_id" not in parcels_gdf.columns:
        return []
    geom = asset_geometry(asset_id, parcels_gdf, assets_df)
    if geom is None:
        return []
    if geom is None or geom.is_empty:
        return []
    rep = geom.centroid if geom.geom_type != "Point" else geom

    distances = network_gdf.geometry.distance(rep)
    if distances.empty:
        return []

    idx = distances.nsmallest(max_edges).index

    # Prefer walking-eligible edges where the type is available.
    if "edge_type" in network_gdf.columns:
        walking_idx = [
            i for i in idx
            if network_gdf.loc[i, "edge_type"] in WALKING_EDGE_TYPES
        ]
        if walking_idx:
            idx = walking_idx

    edge_ids = []
    for i in idx:
        eid = network_gdf.loc[i, "edge_id"]
        if eid is not None:
            edge_ids.append(str(eid))
    return edge_ids