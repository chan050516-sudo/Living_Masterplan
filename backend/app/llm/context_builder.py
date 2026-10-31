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
import pandas as pd

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
        "engineering_spec_vocabulary": _engineering_spec_vocabulary(),
        "model_assumptions": _relevant_assumptions(ds),
    }


# ------------------------------------------------------------------
# Per-target assembly
# ------------------------------------------------------------------


def _build_target_block(asset_id: str, ds) -> dict:
    state = get_asset_state(ds, asset_id)
    if "error" in state:
        return None

    deadspace = get_deadspace_status(ds, asset_id)
    evidence = get_asset_evidence(ds, asset_id)
    walk = get_catchment_profile(ds, asset_id, "walk")
    drive = get_catchment_profile(ds, asset_id, "drive")
    population = get_population_profile(ds, asset_id)

    parcel_id = _get_parcel_id(ds, asset_id)
    candidates = get_development_candidates(ds, parcel_id) if parcel_id else []

    authority_level = _resolve_authority(ds, asset_id)
    asset_type = state.get("identity", {}).get("asset_type") or ""
    asset_row = ds._asset_row(asset_id) or {}
    ownership = asset_row.get("ownership_status")
    authority_block = {
        "level": authority_level,
        "ownership_status": ownership if isinstance(ownership, str) else None,
        **_authority_split(asset_type, authority_level),
    }

    derived = _drop_none(state.get("derived_metrics", {}))
    observed = _drop_none(state.get("observed_metrics", {}))
    
    # Highlight key metrics for non-commercial assets so they aren't ignored
    key_metrics = {}
    if asset_type == "green_space":
        key_metrics = {
            "green_coverage": derived.get("green_coverage"),
            "canopy_coverage": derived.get("canopy_coverage"),
            "green_per_capita_m2": derived.get("green_per_capita_m2"),
            "t_asset_c": derived.get("t_asset_c"),
            "t_township_c": derived.get("t_township_c"),
            "surface_temp_delta_c": derived.get("surface_temp_delta_c"),
            "surface_temp_provenance": derived.get("surface_temp_provenance"),
            "surface_temp_source_catalog": derived.get("surface_temp_source_catalog"),
        }
    elif asset_type == "community_facility":
        key_metrics = {
            "utilisation_rate": observed.get("utilisation_rate"),
            "service_coverage": derived.get("service_coverage"),
            "cost_per_user_rm": derived.get("cost_per_user_rm"),
        }
    elif asset_type == "commercial":
        key_metrics = {
            "occupancy_rate": observed.get("occupancy_rate"),
            "noi_rm": derived.get("noi_rm"),
            "effective_demand_m2": derived.get("effective_demand_m2"),
            "t_asset_c": derived.get("t_asset_c"),
            "t_township_c": derived.get("t_township_c"),
            "surface_temp_delta_c": derived.get("surface_temp_delta_c"),
            "surface_temp_provenance": derived.get("surface_temp_provenance"),
            "surface_temp_source_catalog": derived.get("surface_temp_source_catalog"),
        }
    elif asset_type in ("residential", "community_facility"):
        key_metrics = {
            "t_asset_c": derived.get("t_asset_c"),
            "t_township_c": derived.get("t_township_c"),
            "surface_temp_delta_c": derived.get("surface_temp_delta_c"),
            "surface_temp_provenance": derived.get("surface_temp_provenance"),
            "surface_temp_source_catalog": derived.get("surface_temp_source_catalog"),
        }

    return {
        "asset_id": asset_id,
        "identity": state.get("identity", {}),
        "physical": state.get("physical", {}),
        "financial_static": state.get("financial_static", {}),
        "key_metrics": key_metrics,
        "observed": observed,
        "derived": derived,
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
        "spatial_rings": _build_spatial_rings(ds, asset_id),
        "detailed_neighbors": _build_detailed_neighbors(ds, asset_id), # NEW
        "development_candidates": candidates,
        "trajectory": _build_trajectory_block(ds, asset_id),
        "lease_schedule": _build_lease_schedule(ds, asset_id),
        "subtype_mix": _build_subtype_mix(ds, asset_id),
        "authority": authority_block,
    }


def _subtypes_for_class(asset_class: str, ds) -> list:
    from .tool_service import get_available_subtypes
    raw = get_available_subtypes(ds, asset_class)
    return [
        {
            "subtype": s.get("subtype"),
            "display_name": s.get("display_name"),
            "is_core_amenity": s.get("is_core_amenity", False),
            "target_area_m2": s.get("target_area_m2"),
            "competition_radius_m": s.get("competition_radius_m"),
        }
        for s in raw
    ]


def _build_detailed_neighbors(ds, asset_id, radius_m=1200.0, max_items=25) -> list:
    """Detailed list of non-residential neighbors for catalytic analysis."""
    nearby = get_nearby_assets(ds, asset_id, radius_m=radius_m)
    detailed = []

    for n in nearby:
        if n.get("asset_type") == "residential":
            continue
        if len(detailed) >= max_items:
            break

        _m = ds._metric_row(n["asset_id"], ds.year) or {}
        _ds = ds.deadspace.get(n["asset_id"]) or {}
        _a = ds._asset_row(n["asset_id"]) or {}

        occ = _m.get("occupancy_rate") or _m.get("utilisation_rate")
        try:
            occ_f = float(occ) if occ is not None else 0.0
        except (TypeError, ValueError):
            occ_f = 0.0

        # Look for lease expiry to help LLM reason about joint timing
        lease_info = None
        if not ds.leases.empty:
            _l = ds.leases[ds.leases["asset_id"] == n["asset_id"]]
            if not _l.empty and "lease_end_year" in _l.columns:
                lease_info = _l["lease_end_year"].dropna().min()
                try:
                    lease_info = int(lease_info)
                except (TypeError, ValueError):
                    lease_info = None

        detailed.append({
            "asset_id": n["asset_id"],
            "subtype": n.get("subtype"),
            "distance_m": round(n["distance_m"]),
            "occupancy": round(occ_f, 2),
            "status": _ds.get("status", "healthy"),
            "floor_area_m2": _a.get("floor_area_m2"),
            "lease_expiry_year": lease_info,
            "authority": _a.get("authority"),
        })

    return detailed


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


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


# ------------------------------------------------------------------
# Township Baseline (Macro)
# ------------------------------------------------------------------

def _build_township_baseline(ds) -> dict:
    metrics = ds.metrics
    if metrics is None or metrics.empty:
        return {"note": "metrics file unavailable"}

    year = ds.year
    current = metrics[metrics["year"] == year] if "year" in metrics.columns else metrics
    if current.empty:
        return {"note": f"no metrics for year {year}"}

    if not ds.assets.empty:
        merge_cols = ["asset_id"]
        for col in ["asset_type", "capacity", "subtype", "lettable_area_m2"]:
            if col in ds.assets.columns and col not in current.columns:
                merge_cols.append(col)
        if len(merge_cols) > 1:
            current = current.merge(ds.assets[merge_cols], on="asset_id", how="left")

    def _avg(col):
        if col not in current.columns: return None
        vals = current[col].dropna()
        return round(float(vals.mean()), 4) if not vals.empty else None

    def _sum(col):
        if col not in current.columns: return None
        vals = current[col].dropna()
        return round(float(vals.sum()), 2) if not vals.empty else None

    comm_mask = current["asset_type"] == "commercial"
    res_mask = current["asset_type"] == "residential"
    green_mask = current["asset_type"] == "green_space"
    fac_mask = current["asset_type"] == "community_facility"

    subtype_stats = []
    if comm_mask.any() and "subtype" in current.columns:
        for st in current.loc[comm_mask, "subtype"].dropna().unique():
            _df = current[(current["asset_type"] == "commercial") & (current["subtype"] == st)]
            _occ = _df["occupancy_rate"].mean()
            if _occ is not None and not pd.isna(_occ):
                subtype_stats.append({"subtype": st, "avg_occ": round(float(_occ), 3)})
    
    subtype_stats.sort(key=lambda x: x["avg_occ"])
    oversupplied = [s for s in subtype_stats[:3] if s["avg_occ"] < 0.50]

    total_pop = 0
    if res_mask.any() and "capacity" in current.columns:
        total_pop = int(current.loc[res_mask, "capacity"].fillna(0).sum())

    green_avg_canopy = _avg("canopy_coverage") if green_mask.any() else None
    fac_avg_util = _avg("utilisation_rate") if fac_mask.any() else None

    return {
        "asset_count": int(len(current)),
        "year": year,
        "township_total_population_est": total_pop,
        "commercial_supply_m2": _sum("lettable_area_m2") if "lettable_area_m2" in current.columns else None,
        "commercial_avg_occupancy": round(float(current.loc[comm_mask, "occupancy_rate"].mean()), 3) if comm_mask.any() else None,
        "oversupplied_subtypes_globally": oversupplied,
        "green_space_avg_canopy": green_avg_canopy,
        "community_facility_avg_util": fac_avg_util,
        "deadspace_candidates_total": len([r for r in ds.deadspace.values() if r.get("status") == "deadspace_candidate"]),
        "avg_walk_15min_coverage": _avg("coverage_ratio_15min_walk"),
        "total_operational_carbon_tco2e": _sum("carbon_operational_tco2e"),
    }


# ------------------------------------------------------------------
# Spatial Rings (Meso)
# ------------------------------------------------------------------

def _build_spatial_rings(ds, asset_id, radius_m=1200.0) -> dict:
    """
    Group nearby commercial assets into three walking-distance rings:
    0-400m, 400-800m, and 800-1200m.
    
    For each ring, summarize the count, average occupancy, dead
    competitors (occupancy < 10%), and healthy anchors (occupancy > 80%).
    This gives the LLM a spatial topology without overwhelming the context.
    """
    nearby = get_nearby_assets(ds, asset_id, radius_m=radius_m)
    
    rings = {
        "0_400m": {"count": 0, "occupancies": [], "dead": [], "healthy": []},
        "400_800m": {"count": 0, "occupancies": [], "dead": [], "healthy": []},
        "800_1200m": {"count": 0, "occupancies": [], "dead": [], "healthy": []},
    }

    for n in nearby:
        if n.get("asset_type") == "residential":
            continue
        
        d = n["distance_m"]
        ring_key = "0_400m" if d <= 400 else ("400_800m" if d <= 800 else "800_1200m")
        
        _m = ds._metric_row(n["asset_id"], ds.year) or {}
        _ds = ds.deadspace.get(n["asset_id"]) or {}
        
        occ = _m.get("occupancy_rate") or _m.get("utilisation_rate") or 0.0
        status = _ds.get("status", "healthy")
        
        try:
            occ_f = float(occ)
        except (TypeError, ValueError):
            occ_f = 0.0

        rings[ring_key]["count"] += 1
        rings[ring_key]["occupancies"].append(occ_f)
        
        item = {
            "subtype": n.get("subtype"), 
            "dist_m": round(d), 
            "occ": round(occ_f, 2)
        }
        
        # Categorize as dead competitor or healthy anchor
        if status == "deadspace_candidate" or occ_f < 0.10:
            rings[ring_key]["dead"].append(item)
        elif occ_f > 0.80:
            rings[ring_key]["healthy"].append(item)

    # Compile output, keeping only top closest competitors per ring
    out = {}
    for k, v in rings.items():
        if v["count"] == 0:
            continue
            
        avg_occ = round(sum(v["occupancies"]) / v["count"], 3) if v["count"] > 0 else 0
        r_out = {"count": v["count"], "avg_occ": avg_occ}
        
        if v["dead"]:
            r_out["dead_competitors"] = sorted(v["dead"], key=lambda x: x["dist_m"])[:2]
        if v["healthy"]:
            r_out["healthy_anchors"] = sorted(v["healthy"], key=lambda x: x["dist_m"])[:3]
            
        out[k] = r_out

    return out


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


def _engineering_spec_vocabulary() -> dict:
    """Vocabulary and guidance for the P1 engineering_spec block.

    Exposed in the context pack so the LLM has a menu of legal values
    and typical magnitudes without guessing. Does NOT prescribe a
    specific spec — the LLM picks based on asset state.
    """
    return {
        "when_to_use": (
            "Use engineering_spec on retrofit and repurpose items when "
            "the user's intent implies material, HVAC, or PV decisions. "
            "Omit it for spatial interventions (green_corridor, "
            "pedestrian_upgrade) or when only an aggregate efficiency "
            "number is known."
        ),
        "fields": {
            "structure_retention_ratio": {
                "type": "float [0.0, 1.0]",
                "typical_values": {
                    "cosmetic_retrofit": 0.95,
                    "adaptive_reuse": 0.85,
                    "heavy_retrofit": 0.60,
                    "demolish_rebuild": 0.0,
                },
                "physics_hook": (
                    "Avoided embodied carbon = new_build_intensity + "
                    "demolition - (R_s × structural_intensity + facade "
                    "+ fitout). Values below 0.10 yield zero avoided "
                    "carbon — the engine treats them as a rebuild."
                ),
            },
            "facade_action": {
                "type": "enum",
                "values": [
                    "retain", "insulated_overclad",
                    "curtain_wall", "timber_clad",
                ],
                "physics_hook": (
                    "Adds facade embodied intensity: retain=0, "
                    "insulated_overclad=0.06, curtain_wall=0.12, "
                    "timber_clad=0.04 tCO2e/m2."
                ),
            },
            "primary_material": {
                "type": "enum",
                "values": [
                    "standard_concrete", "ggbs_concrete",
                    "mass_timber", "recycled_steel",
                ],
                "physics_hook": (
                    "Structural embodied intensity per m2 retained: "
                    "standard_concrete=0.22, ggbs_concrete=0.14, "
                    "mass_timber=0.05, recycled_steel=0.18 tCO2e/m2."
                ),
            },
            "roof_intervention": {
                "type": "enum",
                "values": ["none", "cool_roof", "green_roof", "solar_canopy"],
                "physics_hook": (
                    "Reduces cooling ambient temperature: cool_roof="
                    "-1.5°C, green_roof=-2.2°C, solar_canopy=-1.8°C. "
                    "Prefer green_roof or solar_canopy when the asset's "
                    "observed surface_temp_delta_c exceeds +2.0°C."
                ),
            },
            "hvac_cop": {
                "type": "float [2.0, 6.0]",
                "typical_values": {
                    "legacy_split_ac": 2.8,
                    "standard_vrf": 3.5,
                    "premium_vrf": 4.2,
                    "district_cooling": 5.5,
                },
                "physics_hook": (
                    "Cooling energy scales as 3.0 / hvac_cop relative "
                    "to a standard split system. COP 4.2 delivers "
                    "~29% energy reduction for the same load."
                ),
            },
            "operating_hours_per_week": {
                "type": "float [20, 168]",
                "typical_values": {
                    "standard_office": 70,
                    "extended_retail": 84,
                    "community_hub": 112,
                    "24_7": 168,
                },
                "physics_hook": (
                    "Cooling energy scales linearly with operating "
                    "hours. Do not exceed what the target usage "
                    "actually requires."
                ),
            },
            "rooftop_pv_coverage": {
                "type": "float [0.0, 0.9]",
                "physics_hook": (
                    "Annual PV yield = footprint_m2 × coverage × 0.18 "
                    "× 4.2 kWh/day × 365. Deducted from operational "
                    "energy before carbon conversion."
                ),
            },
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
