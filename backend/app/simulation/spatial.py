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

Design notes:
  - Interventions are cumulative. Once activated in year Y they remain
    in effect for every later year.
  - The canopy boost is additive on canopy_coverage_ratio and clipped
    at 1.0. The default boost depends on the intervention type; it can
    be overridden per-intervention through parameters_json.
  - Which edges an intervention affects is resolved from the
    intervention's parameters_json first, and from target_asset_id as
    a legacy fallback (the mock data uses edge ids as target ids).
"""

import json
import logging

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

    Used as a cache key in B4 so that the network pipeline is rebuilt
    only when the set of active interventions actually changes. Two
    sets with the same members produce the same tag.
    """
    if not active_spatial:
        return "base"

    ids = []
    for intv in active_spatial:
        iid = intv.get("intervention_id")
        if not iid:
            iid = intv.get("target_asset_id") or "?"
        ids.append(str(iid))
    return "post_" + "_".join(sorted(ids))


def apply_spatial_interventions(network_gdf, active_spatial):
    """
    Return a copy of `network_gdf` with `canopy_coverage_ratio` adjusted
    on the edges targeted by the given spatial interventions.

    If `active_spatial` is empty, the input is returned unchanged.

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

        target_edges = _resolve_target_edges(intv, params)
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


def _resolve_target_edges(intv, params):
    """
    Determine which network edge ids an intervention affects.

    Resolution order:
      1. params["edge_id"]       single edge id
      2. params["edge_ids"]      list of edge ids
      3. intv["target_asset_id"] legacy: the asset id doubles as an
                                 edge id. The mock interventions.csv
                                 targets "E-R17" this way.
    """
    if params.get("edge_id"):
        return [str(params["edge_id"])]
    if params.get("edge_ids"):
        ids = params["edge_ids"]
        if isinstance(ids, str):
            return [ids]
        return [str(x) for x in ids]
    target = intv.get("target_asset_id")
    if target:
        return [str(target)]
    return []