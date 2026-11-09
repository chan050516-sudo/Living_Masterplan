"""
Soft interventions — actions SDP can take without owning the asset.

Background (team doc "Soft Intervention"): once shoplots are sold to
individual investors, the developer loses control of the tenant mix,
and a street can die even though every unit is "sold". Leading
developers counter this with services that need no ownership:
tenant matching for investors, and tactical placemaking (markets,
food trucks, pop-up courts) that pulls footfall into a dead corner.

Two intervention types live here:

  tenant_matching
      Acts on one (usually sold) commercial unit. Each candidate tenant
      type gets a Suitability Index S in [0, 1] from data the developer
      can see:
        - demand  : the demand/supply ratio (Huff) for that tenant type
                    at this location, scaled to the best candidate
        - room    : how few same-type shops already sit inside the
                    type's competition radius
        - anchor  : footfall generators (cafe, kopitiam, convenience
                    store, restaurant ...) score higher, as in practice
      S = 0.45·demand + 0.30·room + 0.25·anchor.
      The best type is picked unless the plan names one. Leasing is a
      yearly Markov step "vacant -> leased" with success probability
          p = clip(0.25 + 0.50·S + 0.20·footfall_percentile, 0.10, 0.90)
      so the expected occupancy n years after activation is
          occ_n = bench - (bench - occ_0)·(1 - p)^n
      where bench is the tenant type's occupancy benchmark. A leased
      anchor also lifts the Huff attractiveness of shops within 200 m.
      Not modelled (no data): corner vs intermediate lot, the 500 m
      age profile (only a township-wide profile exists).

  tactical_placemaking
      A temporary magnet placed at the target asset for
      `duration_years` (default 3). Every commercial asset within
      `radius_m` (default 400 m) gets an attractiveness and footfall
      multiplier 1 + mass·(1 - d/radius), where `mass` depends on the
      kind of event. When the event ends the effect ends: it is a
      catalyst, not a permanent fix.

All functions are pure apart from a small coordinate cache.
"""

import json
import logging
import math

log = logging.getLogger(__name__)

SOFT_TYPES = {"tenant_matching", "tactical_placemaking"}

# kind -> (mass at the site, default footprint m2). Mass is the peak
# fractional uplift in attractiveness / footfall for a shop next door.
PLACEMAKING_KINDS = {
    "night_market":       (0.60, 2500.0),
    "weekend_market":     (0.45, 2000.0),
    "food_truck_park":    (0.50, 1500.0),
    "popup_sports_court": (0.30, 600.0),
    "community_event_space": (0.25, 800.0),
}
DEFAULT_PLACEMAKING_KIND = "weekend_market"
PLACEMAKING_RADIUS_M = 400.0
PLACEMAKING_DEFAULT_YEARS = 3

# Tenant types that generate footfall for the whole street.
ANCHOR_SUBTYPES = {
    "cafe", "kopitiam", "convenience_retail", "restaurant", "f_and_b",
    "supermarket", "pharmacy", "medical_retail", "clinic",
}
# Subtypes a single shoplot cannot host.
_NOT_A_SHOPLOT = {"mall", "supermarket", "office"}
ANCHOR_RADIUS_M = 200.0
ANCHOR_UPLIFT = 0.15

STREET_RADIUS_M = 300.0
STREET_SURVIVAL_THRESHOLD = 0.50


def _params(intv) -> dict:
    try:
        return json.loads(intv.get("parameters_json") or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def asset_points(assets_df, parcels_gdf) -> dict:
    """{asset_id: (x, y)} parcel centroids in the parcels' CRS."""
    from .spatial import asset_geometry
    out = {}
    for aid in assets_df["asset_id"]:
        g = asset_geometry(aid, parcels_gdf, assets_df)
        if g is not None:
            c = g.centroid
            out[aid] = (c.x, c.y)
    return out


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


# ------------------------------------------------------------------
# Tenant matching
# ------------------------------------------------------------------

def suitability_ranking(asset_id, base_row, assets_df, points,
                        subtypes_config, footfall_pct=None):
    """
    Rank candidate tenant types for one shop. Returns a list of dicts
    sorted best first: {subtype, suitability, demand, room, anchor}.
    """
    try:
        dsr = json.loads(base_row.get("dsr_by_subtype_json") or "{}")
    except (json.JSONDecodeError, TypeError):
        dsr = {}
    dsr = {k: v for k, v in dsr.items() if _num(v) is not None}

    shoplot_types = [
        st for st, d in subtypes_config.items()
        if (d or {}).get("asset_class") == "commercial" and st not in _NOT_A_SHOPLOT
    ]
    # Prefer tenant types the Huff model actually measured demand for
    # at this location; the current (failing) type is not a match.
    current = None
    if "subtype" in assets_df.columns:
        _r = assets_df[assets_df["asset_id"] == asset_id]
        current = _r.iloc[0].get("subtype") if not _r.empty else None
    candidates = [st for st in shoplot_types if st in dsr and st != current]
    if not candidates:
        candidates = [st for st in shoplot_types if st != current]
    if not candidates:
        return []
    best_dsr = max([float(dsr.get(st, 0.0)) for st in candidates] or [0.0])
    origin = points.get(asset_id)

    rows = []
    for st in candidates:
        d = float(dsr.get(st, 0.0))
        demand = d / best_dsr if best_dsr > 0 else 0.0
        radius = float((subtypes_config.get(st) or {}).get("competition_radius_m") or 500)
        rivals = 0
        if origin is not None:
            same = assets_df[(assets_df["subtype"] == st) & (assets_df["asset_id"] != asset_id)]
            rivals = sum(
                1 for aid in same["asset_id"]
                if aid in points and _dist(points[aid], origin) <= radius
            )
        room = max(0.0, 1.0 - rivals / 4.0)
        anchor = 1.0 if st in ANCHOR_SUBTYPES else 0.5
        s = 0.45 * demand + 0.30 * room + 0.25 * anchor
        rows.append({
            "subtype": st,
            "suitability": round(s, 3),
            "demand": round(demand, 3),
            "room": round(room, 3),
            "rivals_in_radius": rivals,
            "anchor": anchor == 1.0,
        })
    rows.sort(key=lambda r: r["suitability"], reverse=True)
    return rows


def success_probability(suitability, footfall_pct=None) -> float:
    f = 0.5 if footfall_pct is None else float(footfall_pct)
    p = 0.25 + 0.50 * float(suitability) + 0.20 * f
    return round(min(0.90, max(0.10, p)), 3)


def matched_occupancy(occ_start, benchmark, p, years_active) -> float:
    """Expected occupancy after `years_active` yearly Markov steps."""
    occ0 = 0.0 if occ_start is None else float(occ_start)
    n = max(0, int(years_active))
    return benchmark - (benchmark - occ0) * (1.0 - p) ** n


def resolve_tenant_matching(scenario_interventions, base_derived, assets_df,
                            points, subtypes_config, footfall_lookup):
    """
    Fill in `tenant_subtype`, `_suitability`, `_p_success` and
    `_ranking` for every tenant_matching row that does not name a
    tenant type, by writing them back into parameters_json. Returns
    {asset_id: resolved params} for the comparison block.
    """
    resolved = {}
    if scenario_interventions is None or scenario_interventions.empty:
        return resolved
    base = {r["asset_id"]: r for _, r in base_derived.iterrows()}
    for idx, intv in scenario_interventions.iterrows():
        if intv.get("intervention_type") != "tenant_matching":
            continue
        aid = intv.get("target_asset_id")
        params = _params(intv)
        row = assets_df[assets_df["asset_id"] == aid]
        subtype_now = row.iloc[0].get("subtype") if not row.empty else None
        ranking = suitability_ranking(
            aid, dict(base.get(aid, {})), assets_df, points, subtypes_config,
        )
        chosen = params.get("tenant_subtype")
        pick = next((r for r in ranking if r["subtype"] == chosen), None)
        if pick is None:
            pick = ranking[0] if ranking else {"subtype": subtype_now, "suitability": 0.5}
        footfall = footfall_lookup(aid, subtype_now)
        p = _num(params.get("success_probability"))
        if p is None:
            p = success_probability(pick["suitability"], footfall)
        params.update({
            "tenant_subtype": pick["subtype"],
            "_suitability": pick["suitability"],
            "_p_success": p,
            "_footfall_percentile": footfall,
            "_ranking": ranking[:3],
        })
        scenario_interventions.at[idx, "parameters_json"] = json.dumps(params)
        resolved[aid] = {
            "from_subtype": subtype_now,
            "tenant_subtype": pick["subtype"],
            "suitability": pick["suitability"],
            "success_probability_per_year": p,
            "footfall_percentile": footfall,
            "top_candidates": ranking[:3],
        }
    return resolved


# ------------------------------------------------------------------
# Footfall boosts (placemaking and leased anchors)
# ------------------------------------------------------------------

def _active(intv, year) -> bool:
    try:
        return int(intv.get("activation_year")) <= year
    except (TypeError, ValueError):
        return False


def footfall_boosts(scenario_interventions, year, assets_df, points):
    """
    {asset_id: multiplier >= 1} for `year`, from active placemaking
    events and from anchors placed by tenant matching.
    """
    boosts = {}
    if scenario_interventions is None or scenario_interventions.empty:
        return boosts
    comm = assets_df[assets_df["asset_type"] == "commercial"]["asset_id"]
    for _, intv in scenario_interventions.iterrows():
        itype = intv.get("intervention_type")
        if itype not in SOFT_TYPES or not _active(intv, year):
            continue
        params = _params(intv)
        site = points.get(intv.get("target_asset_id"))
        if site is None:
            continue
        if itype == "tactical_placemaking":
            years = int(_num(params.get("duration_years")) or PLACEMAKING_DEFAULT_YEARS)
            if not params.get("permanent") and year >= int(intv.get("activation_year")) + years:
                continue
            kind = params.get("kind") or DEFAULT_PLACEMAKING_KIND
            mass = PLACEMAKING_KINDS.get(kind, PLACEMAKING_KINDS[DEFAULT_PLACEMAKING_KIND])[0]
            radius = _num(params.get("radius_m")) or PLACEMAKING_RADIUS_M
        else:  # tenant_matching: a leased anchor lifts its neighbours
            if params.get("tenant_subtype") not in ANCHOR_SUBTYPES:
                continue
            p = _num(params.get("_p_success")) or 0.5
            mass, radius = ANCHOR_UPLIFT * p, ANCHOR_RADIUS_M
        for aid in comm:
            pt = points.get(aid)
            if pt is None:
                continue
            d = _dist(pt, site)
            if d > radius:
                continue
            boosts[aid] = boosts.get(aid, 1.0) * (1.0 + mass * (1.0 - d / radius))
    return boosts


# ------------------------------------------------------------------
# The pitch: street survival before / after
# ------------------------------------------------------------------

def _occ_of(st: dict):
    for k in ("occupancy_rate", "proxied_occupancy_lbs"):
        v = _num((st or {}).get(k))
        if v is not None:
            return v
    return None


def street_survival(asset_id, year_state, assets_df, points,
                    radius=STREET_RADIUS_M, threshold=STREET_SURVIVAL_THRESHOLD):
    """
    Share of commercial units within `radius` of the asset (itself
    included) whose occupancy (or LBS estimate) is at least
    `threshold`. Returns (share, units_counted).
    """
    origin = points.get(asset_id)
    if origin is None:
        return None, 0
    comm = assets_df[assets_df["asset_type"] == "commercial"]["asset_id"]
    vals = []
    for aid in comm:
        pt = points.get(aid)
        if pt is None or _dist(pt, origin) > radius:
            continue
        v = _occ_of(year_state.get(aid))
        if v is not None:
            vals.append(v)
    if not vals:
        return None, 0
    return round(sum(1 for v in vals if v >= threshold) / len(vals), 3), len(vals)


def soft_comparison(scenario_interventions, state_by_year, base_year,
                    final_year, assets_df, points, resolved):
    """Per-asset pitch block for every soft intervention in the plan."""
    out = {}
    if scenario_interventions is None or scenario_interventions.empty:
        return out
    years = sorted(state_by_year)
    for _, intv in scenario_interventions.iterrows():
        itype = intv.get("intervention_type")
        if itype not in SOFT_TYPES:
            continue
        aid = intv.get("target_asset_id")
        params = _params(intv)
        before = state_by_year.get(base_year, {})
        after = state_by_year.get(final_year, {})
        block = {"type": itype, "tier": "3b"}
        if itype == "tenant_matching":
            sb, n = street_survival(aid, before, assets_df, points)
            sa, _ = street_survival(aid, after, assets_df, points)
            block.update(resolved.get(aid, {}))
            block.update({
                "occupancy_before": _occ_of(before.get(aid)),
                "occupancy_after": _occ_of(after.get(aid)),
                "street_survival_before": sb,
                "street_survival_after": sa,
                "street_units_counted": n,
                "street_radius_m": STREET_RADIUS_M,
                "survival_threshold_occupancy": STREET_SURVIVAL_THRESHOLD,
                "lbs_users_before": _num((before.get(aid) or {}).get("lbs_unique_users_daily")),
                "lbs_users_after": _num((after.get(aid) or {}).get("lbs_unique_users_daily")),
                "note": ("Expected value of a yearly vacant->leased Markov step. "
                         "Street survival = share of shops within 300 m at "
                         ">= 50% occupancy (LBS estimate for sold shops)."),
            })
        else:
            kind = params.get("kind") or DEFAULT_PLACEMAKING_KIND
            dur = int(_num(params.get("duration_years")) or PLACEMAKING_DEFAULT_YEARS)
            act = int(intv.get("activation_year"))
            active_years = [y for y in years if act <= y and (params.get("permanent") or y < act + dur)]
            peak = active_years[0] if active_years else None
            uplift = {}
            if peak is not None:
                comm = assets_df[assets_df["asset_type"] == "commercial"]["asset_id"]
                for b in comm:
                    st_p = state_by_year[peak].get(b) or {}
                    boost = _num(st_p.get("_footfall_boost"))
                    if boost and boost > 1.0:
                        uplift[b] = round(boost - 1.0, 3)
            block.update({
                "kind": kind,
                "active_years": active_years,
                "temporary": not params.get("permanent"),
                "shops_reached": len(uplift),
                "avg_footfall_uplift_in_active_year": (
                    round(sum(uplift.values()) / len(uplift), 3) if uplift else 0.0
                ),
                "max_footfall_uplift": max(uplift.values()) if uplift else 0.0,
                "note": ("Temporary magnet: uplift applies only while the event "
                         "runs. Pair with tenant matching for a lasting effect."),
            })
        out[aid] = block
    return out
