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
        "targets": targets,
        "available_subtypes": available_subtypes,
        "available_interventions": available_interventions,
        "nearby_subtype_radii": nearby_subtype_radii,
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
    authority_block = {
        "level": authority_level,
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
      1. The `authority` column on the asset row.
      2. A default inferred from the asset type.
      3. "advisory" as the safest fallback.
    """
    row = ds._asset_row(asset_id)
    if row is None:
        return "advisory"
    raw = row.get("authority")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
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
            "The developer owns this asset outright. Every legal "
            "intervention is executable without external approval."
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
            "This asset has been transferred to a public authority. "
            "The developer has no execution power. Every proposal is "
            "a recommendation, not a commitment. Use role phrasing "
            "such as 'recommend the responsible authority to...' in "
            "the rationale."
        )

    return {
        "executable": split["executable"],
        "requires_approval": split["requires_approval"],
        "recommendation_only": split["recommendation_only"],
        "note": note,
    }