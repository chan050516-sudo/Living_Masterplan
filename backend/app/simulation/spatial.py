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


def apply_spatial_interventions(network_gdf, active_spatial, parcels_gdf=None):
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
        )
        if not target_edges:
            log.info(
                "Spatial intervention %s has no resolvable target edges; skipped.",
                intv.get("intervention_id"),
            )
            continue

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


def _resolve_target_edges(intv, params, network_gdf=None, parcels_gdf=None):
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
            target_str, network_gdf, parcels_gdf,
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


def _find_edges_near_asset(asset_id, network_gdf, parcels_gdf, max_edges=5):
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
    match = parcels_gdf[parcels_gdf["asset_id"] == asset_id]
    if match.empty:
        return []
    geom = match.iloc[0].geometry
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