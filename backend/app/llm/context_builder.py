"""Deterministic context assembly for the LLM reasoning layer.

Phase 12 (2026-10-16): replaces the agentic `_gather_context` loop in
the orchestrator. Instead of letting the LLM decide which tools to
call, this module builds a complete, well-shaped context pack up front
from the township data source. The LLM then sees everything it could
possibly need in a single prompt, and produces a structured plan in
one inference call.

Design principles:
  - One pack per reasoning run. The pack is deterministic: same
    intent + same data source → identical pack.
  - Only decision-relevant fields. The pack is not a data dump; it
    carries the values the LLM actually reasons about.
  - Everything JSON-serialisable. No pandas objects, no numpy types.
  - No LLM calls. Zero API cost, zero latency, fully unit-testable.
"""

import logging
import math
import json

from ..deadspace.layer3 import (
    classify_by_authority,
    default_authority_for,
)
from .tool_service import (
    get_asset_state,
    get_asset_evidence,
    get_catchment_profile,
    get_deadspace_status,
    get_development_candidates,
    get_nearby_assets,
    get_population_profile,
)

log = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Public entry point
# ------------------------------------------------------------------


def build_context_pack(intent: dict, ds) -> dict:
    """
    Assemble the full context pack for one reasoning run.

    Parameters
    ----------
    intent : dict
        Output of Stage 0 (parse_intent). Must contain
        `target_asset_ids`, `objective`, `constraints`, `question_text`.
    ds : TownshipDataSource
        Loaded township data.

    Returns
    -------
    dict with keys:
      - user_query, objective, constraints
      - targets:               list of per-asset blocks (see _build_target_block)
      - available_subtypes:    {asset_class: [subtype_defs]}
      - available_interventions: {asset_class: [intervention_types]}
      - nearby_subtype_radii:  {subtype: competition_radius_m}
      - model_assumptions:     {huff, environmental, ...}
    """
    targets = []
    for aid in intent.get("target_asset_ids", []):
        block = _build_target_block(aid, ds)
        if block is None:
            log.warning("Skipping target %s: no data", aid)
            continue
        targets.append(block)

    # Collect asset classes present in the targets so we can pre-load
    # the taxonomy slices the LLM will need.
    asset_classes = sorted({
        t["identity"]["asset_type"] for t in targets
        if t.get("identity") and t["identity"].get("asset_type")
    })

    available_subtypes = {
        cls: _subtypes_for_class(cls, ds) for cls in asset_classes
    }
    available_interventions = {
        cls: _interventions_for_class(cls, ds) for cls in asset_classes
    }

    # Only send competition radii the LLM might actually need: those
    # for the subtypes reachable from the target asset classes.
    relevant_subtypes = set()
    for cls in asset_classes:
        for sub in available_subtypes.get(cls, []):
            relevant_subtypes.add(sub.get("subtype"))
    nearby_subtype_radii = {
        st: _subtype_radius(st, ds) for st in relevant_subtypes if st
    }

    return {
        "user_query": intent.get("question_text", ""),
        "objective": intent.get("objective", "balanced"),
        "constraints": intent.get("constraints") or {},
        "township_baseline": _build_township_baseline(ds),
        "targets": targets,
        "available_subtypes": available_subtypes,
        "available_interventions": available_interventions,
        "nearby_subtype_radii": nearby_subtype_radii,
        "catalytic_vocabulary": _catalytic_vocabulary(),
        "model_assumptions": _relevant_assumptions(ds),
    }


# ------------------------------------------------------------------
# Per-target assembly
# ------------------------------------------------------------------


def _build_target_block(asset_id: str, ds) -> dict:
    """
    Assemble one asset's full decision context.

    Returns None if the asset is not in the township.
    """
    state = get_asset_state(ds, asset_id)
    if "error" in state:
        return None

    deadspace = get_deadspace_status(ds, asset_id)
    evidence = get_asset_evidence(ds, asset_id)

    walk = get_catchment_profile(ds, asset_id, "walk")
    drive = get_catchment_profile(ds, asset_id, "drive")
    population = get_population_profile(ds, asset_id)

    # Nearby assets: filter residential out — the LLM never needs to
    # reason about 40 single-family houses within 800 m. Keep the
    # non-residential neighbours only, capped at 25 entries.
    nearby = get_nearby_assets(ds, asset_id, radius_m=800.0)
    nearby_filtered = [
        n for n in nearby
        if n.get("asset_type") != "residential"
    ][:25]

    parcel_id = _get_parcel_id(ds, asset_id)
    candidates = (
        get_development_candidates(ds, parcel_id) if parcel_id else []
    )

    # Phase 14 — execution authority.
    authority_level = _resolve_authority(ds, asset_id)
    asset_type = state.get("identity", {}).get("asset_type") or ""
    asset_row = ds._asset_row(asset_id) or {}
    ownership = asset_row.get("ownership_status")
    authority_block = {
        "level": authority_level,
        "ownership_status": ownership if isinstance(ownership, str) else None,
        **_authority_split(asset_type, authority_level),
    }

    return {
        "asset_id": asset_id,
        "identity": state.get("identity", {}),
        "physical": state.get("physical", {}),
        "financial_static": state.get("financial_static", {}),
        "observed": _drop_none(state.get("observed_metrics", {})),
        "derived": _drop_none(state.get("derived_metrics", {})),
        "deadspace": {
            "status": deadspace.get("status"),
            "flags": deadspace.get("flags", []),
            "urgency_index": deadspace.get("urgency_index"),
            "contributing_factors": deadspace.get("contributing_factors", []),
        },
        "evidence": evidence,
        "catchment": {
            "walk": _drop_none(walk),
            "drive": _drop_none(drive),
        },
        "population": _drop_none(population),
        "nearby_800m": nearby_filtered,
        "development_candidates": candidates,
        # Phase E — structured decision inputs
        "trajectory": _build_trajectory_block(ds, asset_id),
        "lease_schedule": _build_lease_schedule(ds, asset_id),
        "subtype_mix": _build_subtype_mix(ds, asset_id),
        "authority": authority_block,
    }


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _subtypes_for_class(asset_class: str, ds) -> list:
    """Return a compact list of subtypes for an asset class."""
    from .tool_service import get_available_subtypes
    raw = get_available_subtypes(ds, asset_class)
    # Keep only the fields the LLM reasons about.
    return [
        {
            "subtype": s.get("subtype"),
            "display_name": s.get("display_name"),
            "target_demographics": s.get("target_demographics", []),
            "is_core_amenity": s.get("is_core_amenity", False),
            "target_area_m2": s.get("target_area_m2"),
            "competition_radius_m": s.get("competition_radius_m"),
        }
        for s in raw
    ]


def _interventions_for_class(asset_class: str, ds) -> list:
    """Return the intervention types legal for an asset class."""
    from .tool_service import get_action_space
    return get_action_space(ds, asset_class)


def _subtype_radius(subtype: str, ds):
    defn = ds.subtypes_config.get(subtype) or {}
    return defn.get("competition_radius_m")


def _relevant_assumptions(ds) -> dict:
    """
    Slice the assumptions the LLM needs. Keep it small — the full
    assumptions.yml is huge and mostly irrelevant.
    """
    assumptions = ds.assumptions or {}
    out = {}
    for key in ("huff", "environmental", "occupancy_dynamics"):
        if key in assumptions:
            out[key] = assumptions[key]
    return out


def _get_parcel_id(ds, asset_id: str):
    row = ds._asset_row(asset_id)
    if row is None:
        return None
    pid = row.get("parcel_id")
    if pid is None:
        return None
    if isinstance(pid, float) and math.isnan(pid):
        return None
    return str(pid)


def _drop_none(d: dict) -> dict:
    """Strip None / NaN values so the pack is compact."""
    if not isinstance(d, dict):
        return d
    return {
        k: v for k, v in d.items()
        if v is not None and not (isinstance(v, float) and math.isnan(v))
    }


def _resolve_authority(ds, asset_id: str) -> str:
    """
    Look up the execution authority level of an asset.

    Resolution order:
      1. `authority` column on the asset row (explicit).
      2. Derived from `ownership_status` (developer_held → full_control,
         sold / public_transferred → advisory, strata_jmb → shared).
      3. Default inferred from asset type.
      4. "advisory" as the safest fallback.
    """
    row = ds._asset_row(asset_id)
    if row is None:
        return "advisory"

    explicit = row.get("authority")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()

    ownership = row.get("ownership_status")
    if isinstance(ownership, str) and ownership.strip():
        from ..deadspace.layer3 import _AUTHORITY_BY_OWNERSHIP
        mapped = _AUTHORITY_BY_OWNERSHIP.get(ownership.strip())
        if mapped:
            return mapped

    asset_type = row.get("asset_type")
    if isinstance(asset_type, str):
        return default_authority_for(asset_type)
    return "advisory"


def _authority_split(asset_type: str, authority_level: str) -> dict:
    """
    Expand an authority level into the three execution buckets the
    LLM needs to see. Includes a short human-readable note so the
    LLM understands why some actions cannot be executed.
    """
    split = classify_by_authority(asset_type, authority_level)

    if authority_level == "full_control":
        note = (
            "The developer owns this asset outright (unsold inventory "
            "or undeveloped land). Every legal intervention is "
            "executable without external approval."
        )
    elif authority_level == "shared":
        note = (
            "This asset is strata-titled. Internal upgrades "
            "(retrofit) are normally executable by the lot owner, "
            "but structural changes (repurpose, new_development) "
            "require the owners corporation (JMB / MC) to approve. "
            "Propose them, but the validator will mark them as "
            "requires_approval."
        )
    else:
        note = (
            "This asset has been sold to a private owner or "
            "transferred to a public authority. The developer has no "
            "execution power. Every proposal is a recommendation, "
            "not a commitment. Use role phrasing such as 'recommend "
            "the responsible authority to...' in the rationale."
        )

    return {
        "executable": split["executable"],
        "requires_approval": split["requires_approval"],
        "recommendation_only": split["recommendation_only"],
        "note": note,
    }


def _build_township_baseline(ds) -> dict:
    """
    Township-level reference values the LLM needs for township-first
    reasoning. These come from the current (pre-intervention) asset
    metrics file, aggregated across every asset in the township.
    """
    metrics = ds.metrics
    if metrics is None or metrics.empty:
        return {"note": "metrics file unavailable"}

    # Restrict to the current year and one row per asset.
    year = ds.year
    if "year" in metrics.columns:
        current = metrics[metrics["year"] == year]
    else:
        current = metrics
    if current.empty:
        return {"note": f"no metrics for year {year}"}

    def _avg(col):
        if col not in current.columns:
            return None
        vals = current[col].dropna()
        if vals.empty:
            return None
        return round(float(vals.mean()), 4)

    def _sum(col):
        if col not in current.columns:
            return None
        vals = current[col].dropna()
        if vals.empty:
            return None
        return round(float(vals.sum()), 2)

    # Baselines the LLM must reason against. These are the numbers
    # any township-first candidate must not degrade without a stated
    # trade-off.
    return {
        "asset_count": int(len(current)),
        "year": year,
        "avg_walk_15min_coverage": _avg("coverage_ratio_15min_walk"),
        "avg_walk_10min_coverage": _avg("coverage_ratio_10min_walk"),
        "total_operational_carbon_tco2e": _sum("carbon_operational_tco2e"),
        "total_stranded_carbon_tco2e": _sum("carbon_stranded_tco2e"),
        "total_embodied_carbon_tco2e": _sum("embodied_carbon_total_tco2e"),
    }


def _catalytic_vocabulary() -> dict:
    """
    The catalytic mechanism vocabulary, its description, and the
    maximum verification level B4 can support for each. Exposed in
    the context pack so the LLM knows what it can honestly claim.
    """
    return {
        "walkability_improvement": {
            "description": "spatial intervention raises the beneficiary's walking coverage",
            "max_verification": "verified",
        },
        "catchment_growth": {
            "description": "new residents in the beneficiary's catchment raise demand",
            "max_verification": "verified",
        },
        "competition_relief": {
            "description": "reduces direct competitive pressure on the beneficiary",
            "max_verification": "partially_verified",
        },
        "complementary_use": {
            "description": "a nearby use attracts customers who also consume at the beneficiary",
            "max_verification": "claimed",
        },
        "footfall_injection": {
            "description": "an anchor use draws visitors to the area",
            "max_verification": "claimed",
        },
    }


# ------------------------------------------------------------------
# Phase E — structured decision inputs
# ------------------------------------------------------------------


def _build_trajectory_block(ds, asset_id: str) -> dict:
    """
    Structured view of the asset's five-year trajectory.

    The evidence block already summarises the trajectory as prose.
    This block carries the numeric fields the LLM needs to reason
    quantitatively about the asset's direction, not just read a
    sentence about it.

    Returns None when the trajectory is "unknown" (green_space,
    undeveloped_parcel, and any asset B3 could not classify) — the
    LLM sees a null and reasons accordingly.
    """
    m = ds._metric_row(asset_id, ds.year) or {}
    tclass = m.get("trajectory_class")
    if not tclass or tclass == "unknown":
        return None

    def _f(v):
        try:
            if v is None:
                return None
            f = float(v)
            if math.isnan(f):
                return None
            return round(f, 4)
        except (TypeError, ValueError):
            return None

    return {
        "trajectory_class": tclass,
        "peak_occupancy": _f(m.get("peak_occupancy")),
        "years_since_peak": _f(m.get("years_since_peak")),
        "occupancy_trend_3yr": _f(m.get("occupancy_trend_3yr")),
        "years_below_benchmark": _f(m.get("years_below_benchmark")),
        "vacancy_streak_months": _f(m.get("vacancy_streak_months")),
    }


def _build_lease_schedule(ds, asset_id: str) -> dict:
    """
    Structured view of the asset's lease schedule.

    Returns None when the asset has no lease records (non-commercial
    or a commercial asset with no unit_mix). When present, the block
    summarises:
      - total_leases: how many lease rows exist
      - next_expiry_year: earliest active lease ending year
      - anchor_lease: the (single) anchor tenant, if any
      - expiry_calendar: count of active leases ending per year

    The LLM uses this to decide `construction_start_year` on a
    structural intervention. A mall whose anchor lease runs to 2031
    cannot be repurposed before 2031 with a frictionless schedule.
    """
    leases = getattr(ds, "leases", None)
    if leases is None or leases.empty:
        return None
    m = leases[leases["asset_id"] == asset_id]
    if m.empty:
        return None

    total = int(len(m))
    active = m[m["lease_status"] == "active"]
    if active.empty:
        return {
            "total_leases": total,
            "next_expiry_year": None,
            "anchor_lease": None,
            "expiry_calendar": {},
        }

    ends = active["lease_end_year"].dropna()
    next_end = None
    if not ends.empty:
        try:
            next_end = int(ends.min())
        except (TypeError, ValueError):
            next_end = None

    anchor = active[active["tenant_type"] == "anchor"]
    anchor_block = None
    if not anchor.empty:
        a = anchor.iloc[0]
        anchor_block = {
            "floor_area_m2": _nan_to_none(a.get("floor_area_m2")),
            "end_year": _nan_to_none(a.get("lease_end_year")),
        }

    calendar = {}
    for _, lease in active.iterrows():
        yr = lease.get("lease_end_year")
        if yr is None:
            continue
        try:
            yr_int = int(yr)
        except (TypeError, ValueError):
            continue
        calendar[str(yr_int)] = calendar.get(str(yr_int), 0) + 1

    return {
        "total_leases": total,
        "next_expiry_year": next_end,
        "anchor_lease": anchor_block,
        "expiry_calendar": calendar,
    }


def _build_subtype_mix(ds, asset_id: str) -> dict:
    """
    Structured view of a mixed-use commercial asset's unit_mix.

    Returns None for non-commercial assets or commercial assets
    without a unit_mix (small shoplots). When present, the block
    carries:
      - subtypes: {st: area_m2}
      - occupancy_by_subtype: {st: occupancy_ratio}
      - dead_subtypes: subtypes with occupancy < 0.10
      - low_subtypes: subtypes with 0.10 <= occupancy < 0.40

    The LLM uses this to identify partial death — a mall whose
    supermarket is at 0.95 but whose f_and_b floor is at 0.08 has a
    dead F&B department even if the aggregate occupancy looks fine.
    """
    m = ds._metric_row(asset_id, ds.year) or {}
    row = ds._asset_row(asset_id)
    if row is None:
        return None
    if row.get("asset_type") != "commercial":
        return None

    raw_mix = row.get("unit_mix_json")
    if raw_mix is None or (isinstance(raw_mix, float) and math.isnan(raw_mix)):
        return None
    try:
        mix = json.loads(raw_mix) if isinstance(raw_mix, str) else raw_mix
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(mix, dict) or not mix:
        return None

    subtypes = {}
    for st, info in mix.items():
        area = info.get("area_m2") if isinstance(info, dict) else None
        if area is not None:
            subtypes[st] = _nan_to_none(area)

    occ_raw = m.get("occupancy_by_subtype_calc_json")
    occ_by = {}
    if occ_raw is not None and isinstance(occ_raw, str):
        try:
            parsed = json.loads(occ_raw)
            if isinstance(parsed, dict):
                for st, v in parsed.items():
                    fv = _nan_to_none(v)
                    if fv is not None:
                        occ_by[st] = float(fv)
        except (json.JSONDecodeError, TypeError):
            pass

    # Phase B.3 — per-subtype TARGET from the B3 deriver.
    # This is the occupancy the Huff demand model says
    # each subtype COULD sustain today, before any
    # intervention. The LLM compares it against
    # `occupancy_by_subtype` (actual) to classify the
    # failure as supply-side or demand-side.
    target_raw = m.get("occupancy_by_subtype_target_json")
    targets = {}
    if target_raw is not None and isinstance(target_raw, str):
        try:
            parsed = json.loads(target_raw)
            if isinstance(parsed, dict):
                for st, v in parsed.items():
                    fv = _nan_to_none(v)
                    if fv is not None:
                        targets[st] = float(fv)
        except (json.JSONDecodeError, TypeError):
            pass

    dead = []
    low = []
    for st, v in occ_by.items():
        if v < 0.10:
            dead.append(st)
        elif v < 0.40:
            low.append(st)

    return {
        "subtypes": subtypes,
        "occupancy_by_subtype": occ_by,
        "dead_subtypes": sorted(dead),
        "low_subtypes": sorted(low),
    }


def _classify_subtype_failures(actual, targets):
    """
    Phase B.3 — pair actual and target occupancy per subtype
    into a coarse diagnosis the LLM can reason over.

    Returns a dict keyed by subtype with:
        actual     : float | None
        target     : float | None
        kind       : "healthy" | "supply_side" | "demand_side"
                     | "unknown"
        gap        : target - actual (positive = underused)
    """
    out = {}
    for st in set(actual.keys()) | set(targets.keys()):
        a = actual.get(st)
        t = targets.get(st)
        if a is None or t is None:
            out[st] = {
                "actual": a, "target": t,
                "kind": "unknown", "gap": None,
            }
            continue
        gap = t - a
        if a >= 0.60 and t >= 0.60:
            kind = "healthy"
        elif gap > 0.20 and t >= 0.60:
            # Actual << target AND target is high enough to
            # be worth chasing. This is the supply-side case.
            kind = "supply_side"
        elif t < 0.40:
            # Target itself is low. No amount of tenant
            # churn will fix the demand reality.
            kind = "demand_side"
        else:
            kind = "unknown"
        out[st] = {
            "actual": round(a, 4),
            "target": round(t, 4),
            "kind": kind,
            "gap": round(gap, 4),
        }
    return out


def _nan_to_none(v):
    """Local NaN-safe conversion for context_builder."""
    if v is None:
        return None
    try:
        if isinstance(v, float) and math.isnan(v):
            return None
    except (TypeError, ValueError):
        pass
    return v