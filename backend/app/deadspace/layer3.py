"""Layer 3 — Actionability.

Whether an actionable improvement strategy exists.
Reads the intervention library. Does NOT invent new types.

Phase 14 (2026-10-17):
  - Introduces authority levels. Not every asset is under the
    developer's control. Some are fully owned, some are strata-titled
    (shared with a JMB), and some have been transferred to a public
    authority. `classify_by_authority` splits the legal intervention
    set into executable / requires_approval / recommendation_only.

The base ACTION_SPACE is unchanged: it answers "is this intervention
legal for this asset type?". Authority answers a different question:
"can this actor actually execute it?" The validator enforces the
latter; the LLM is told both.
"""

import logging

log = logging.getLogger(__name__)

# ---------------------------------------------------------------
# Intervention legality per asset type
# ---------------------------------------------------------------
# This is a pure legality check: given an asset type, which
# intervention types are architecturally / legally meaningful?
# It says nothing about who can execute them. See
# `classify_by_authority` for the execution split.

ACTION_SPACE = {
    "residential": [
        "repurpose", "retrofit", "pedestrian_upgrade",
        "renovation",   # NEW — same-class subtype change
    ],
    "commercial": [
        "repurpose", "retrofit", "pedestrian_upgrade", "green_corridor",
        "renovation",   # NEW — e.g. convenience_retail → f_and_b
    ],
    "community_facility": [
        "retrofit", "pedestrian_upgrade", "repurpose",
        "renovation",   # NEW — e.g. community_hall → library
    ],
    "green_space": [
        "green_corridor", "pedestrian_upgrade",
    ],
    "undeveloped_parcel": [
        "new_development", "delay_development", "interim_solar_farm",
    ],
    # Phase 15 — residential's legal action space now includes
    # repurpose. Whether it can actually be EXECUTED depends on
    # authority. Developer-held unsold units can be repurposed;
    # sold / strata units cannot. The legal list is the same; the
    # authority check filters the executable subset.
}


# ---------------------------------------------------------------
# Authority model
# ---------------------------------------------------------------
# full_control — the developer owns the asset outright and has not
#                transferred or strata-titled it. All legal actions
#                are executable.
# shared       — the asset is strata-titled and the owners
#                corporation (JMB / MC) has legal control. Internal
#                upgrades (retrofit) are usually executable by the
#                lot owner; structural changes (repurpose, new_dev)
#                require JMB approval.
# advisory     — the asset has been transferred to a public authority
#                (e.g. a community hall handed to MBSJ). The developer
#                has no execution power; every proposal is a
#                recommendation to the responsible authority.

AUTHORITY_LEVELS = {"full_control", "shared", "advisory"}

# Actions that change what the asset IS (purpose, structure, timeline).
# These require full control to execute.
HARD_ACTIONS = {
    "repurpose",
    "new_development",
    "delay_development",
    "interim_solar_farm",
}

# Default authority inferred from asset type when the assets table
# does not carry an explicit `authority` column. Overridable per-asset
# by supplying the column.
_DEFAULT_AUTHORITY_BY_TYPE = {
    "commercial":          "full_control",
    "residential":         "advisory",  # default; overridden by ownership_status
    "community_facility":  "advisory",
    "green_space":         "advisory",
    "undeveloped_parcel":  "full_control",
}


def get_available_interventions(asset_type: str) -> list:
    """
    Return every intervention type legal for the asset type,
    regardless of authority. This is the legality layer, not the
    execution layer.
    """
    return list(ACTION_SPACE.get(asset_type, []))


def default_authority_for(asset_type: str) -> str:
    """Fallback authority for an asset type."""
    return _DEFAULT_AUTHORITY_BY_TYPE.get(asset_type, "advisory")


def classify_by_authority(asset_type: str, authority: str) -> dict:
    """
    Split the legal intervention set into three execution buckets:

    - executable           — this actor may execute without external
                             approval
    - requires_approval    — this actor may propose; execution needs a
                             third party (JMB, planning authority)
    - recommendation_only  — this actor has no execution power; every
                             proposal is a recommendation

    Returns a dict with three sorted lists.
    """
    legal = set(ACTION_SPACE.get(asset_type, []))
    hard = legal & HARD_ACTIONS
    soft = legal - hard

    if authority == "full_control":
        return {
            "executable": sorted(soft | hard),
            "requires_approval": [],
            "recommendation_only": [],
        }
    if authority == "shared":
        return {
            "executable": sorted(soft),
            "requires_approval": sorted(hard),
            "recommendation_only": [],
        }
    # advisory (default)
    return {
        "executable": [],
        "requires_approval": [],
        "recommendation_only": sorted(legal),
    }


# ---------------------------------------------------------------
# Phase 16+ — flag → physical intervention mapping
# ---------------------------------------------------------------
# A flag says *what is wrong*. This table says *what kind of
# intervention can physically address that problem*. It is a
# **soft** filter: `candidate_interventions` is filtered to the
# union of mapped interventions across the fired flags, BUT if that
# union is empty (a flag maps to no intervention, or the union
# misses the asset's legal set), we fall back to the full legal
# set so the LLM never sees an empty action space.
#
# Why we filter at all
# --------------------
# `high_uhi_exposure` says "this asset is a heat island". The
# physically reasonable responses are canopy injection
# (green_corridor / pedestrian_upgrade) and envelope / HVAC work
# (retrofit). Returning `repurpose` alongside them lets the LLM
# propose demolishing a live asset just to fix heat — an
# over-broad action space invites an over-broad plan.
#
# Why the fallback
# ----------------
# Trajectory flags (rapid_decline / falling_from_healthy /
# chronic_stagnation) and `uhi_data_anomaly` are *symptoms* or
# *data problems*, not problem classes. They map to `set()` on
# purpose: when they are the only fired flags, the union is
# empty, and the caller receives the full legal set. This
# deliberately avoids "we detected a problem but have no
# candidate interventions" dead ends.
#
# A flag not in this table is logged at WARNING (see
# `evaluate`) so a newly introduced flag cannot silently
# disappear from the LLM's action space.
_FLAG_TO_INTERVENTIONS = {
    # ---- Occupancy / utilisation failure ----
    "low_occupancy":                    {"repurpose", "pedestrian_upgrade", "green_corridor", "retrofit"},
    "below_benchmark_occupancy":        {"repurpose", "pedestrian_upgrade", "retrofit"},
    "long_vacancy":                     {"repurpose", "retrofit"},
    "low_utilisation":                  {"repurpose", "retrofit", "pedestrian_upgrade"},
    "chronic_stagnation":               set(),   # symptom; fallback to full set
    "built_value_not_realized":         {"repurpose", "retrofit", "pedestrian_upgrade"},

    # ---- Demand-supply / financial ----
    "dsr_below_threshold":              {"repurpose"},
    "negative_noi":                     {"repurpose", "retrofit"},
    "maintenance_surge_high":           {"retrofit"},
    "demographic_mismatch":             {"repurpose"},
    "low_neighborhood_diversity":       {"repurpose"},

    # ---- Accessibility ----
    "walking_accessibility_deficit":    {"pedestrian_upgrade", "green_corridor"},
    "driving_accessibility_deficit":    {"pedestrian_upgrade"},
    "low_accessibility":                {"pedestrian_upgrade", "green_corridor"},
    "low_accessibility_high_ecological_value": {"pedestrian_upgrade", "green_corridor"},

    # ---- Facility coverage ----
    "insufficient_coverage":            {"repurpose", "pedestrian_upgrade"},

    # ---- Environmental ----
    "high_stranded_carbon":             {"repurpose", "retrofit"},
    "high_stranded_carbon_ratio_small_asset": {"repurpose", "retrofit"},
    "high_uhi_exposure":                {"green_corridor", "pedestrian_upgrade", "retrofit"},
    "uhi_data_anomaly":                 set(),   # data problem; no physical fix
    "low_green_coverage":               {"green_corridor"},
    "low_canopy_coverage":              {"green_corridor"},
    "low_green_per_capita":             {"green_corridor"},

    # ---- Subtype mix ----
    "subtype_mix_dead":                 {"repurpose"},
    "subtype_mix_low":                  {"repurpose", "retrofit"},

    # ---- Undeveloped parcel ----
    "negative_demand_supply_gap":       {"delay_development", "interim_solar_farm"},
    "weak_future_demand":               {"delay_development", "interim_solar_farm"},

    # ---- Trajectory-only (never a problem class on its own) ----
    "rapid_decline":                    set(),   # symptom; fallback to full set
    "falling_from_healthy":             set(),   # symptom; fallback to full set
}


def evaluate(asset_type: str, diagnostics: dict = None,
             layer1: dict = None, layer2: dict = None) -> dict:
    """
    Phase 16 — gate-aware actionability.

    Previously this returned "actionable": len(legal) > 0 for every
    asset type, which made "actionable" always True and turned the
    "if not l3: return monitor" branch in decide_status into dead
    code. It also misled every downstream consumer (LLM, UI) into
    reading "has legal interventions" as "the asset needs them".

    The three fields now separate:

    has_legal_actions — the asset TYPE has some legal intervention.
        A type property. Not a state.

    candidate_interventions — the subset of legal interventions
        indicated by the asset's diagnosis. Two levels of filtering:

          1. Gate: empty when neither layer1 nor layer2 fired.
          2. Flag match: restricted to the union of
             `_FLAG_TO_INTERVENTIONS[flag]` across every fired
             flag, intersected with the asset's legal set.
             If that union is empty (trajectory-only diagnosis,
             or a flag with no mapped intervention), we fall back
             to the full legal set so the LLM never sees an
             empty action space.

    actionable — legacy alias for has_legal_actions. Deprecated;
        retained only for schema compatibility.

    The `diagnostics` parameter is accepted for backward
    compatibility and unused. Fired flags come from `layer1.reasons`
    and `layer2.reasons`.
    """
    legal = ACTION_SPACE.get(asset_type, [])

    layer1_triggered = bool(layer1 and layer1.get("triggered"))
    layer2_triggered = bool(layer2 and layer2.get("triggered"))
    diagnosed = layer1_triggered or layer2_triggered

    if not diagnosed:
        return {
            "has_legal_actions": len(legal) > 0,
            "actionable": len(legal) > 0,   # deprecated alias
            "candidate_interventions": [],
            "diagnosis_active": False,
            "reason": (
                "no layer triggered; no intervention is indicated "
                "regardless of legal action space"
            ),
        }

    # ---- Flag → intervention union ----
    all_flags = (
        list((layer1 or {}).get("reasons", []))
        + list((layer2 or {}).get("reasons", []))
    )

    mapped: set = set()
    unmapped_flags: list = []
    for f in all_flags:
        if f in _FLAG_TO_INTERVENTIONS:
            mapped |= _FLAG_TO_INTERVENTIONS[f]
        else:
            unmapped_flags.append(f)

    if unmapped_flags:
        # Newly introduced flag without a mapping. Surface it so
        # the developer knows to extend `_FLAG_TO_INTERVENTIONS`.
        # The fallback below keeps the LLM productive meanwhile.
        log.warning(
            "layer3: flags without an intervention mapping: %s "
            "(asset_type=%s). These contribute nothing to "
            "candidate_interventions; falling back to the full "
            "legal set will be applied if the union is empty.",
            unmapped_flags, asset_type,
        )

    filtered = [i for i in legal if i in mapped]

    if not filtered:
        # Fallback: trajectory-only diagnosis, or a flag with no
        # mapped intervention that intersects this asset's legal
        # set. Keep the LLM productive by returning the full
        # legal set; the rationale field explains why.
        filtered = list(legal)
        filter_note = (
            "no flag-mapped intervention intersected the legal set; "
            "using the full legal set as fallback"
        )
    else:
        filter_note = (
            f"filtered to {len(filtered)} of {len(legal)} legal "
            f"interventions based on fired flags"
        )

    parts = []
    if layer1_triggered:
        parts.append("layer1")
    if layer2_triggered:
        parts.append("layer2")
    reason = f"diagnosis triggered by {'+'.join(parts)}; {filter_note}"

    return {
        "has_legal_actions": len(legal) > 0,
        "actionable": len(legal) > 0,   # deprecated alias
        "candidate_interventions": filtered,
        "diagnosis_active": True,
        "reason": reason,
    }


def classify_by_ownership(asset_type: str, ownership_status: str) -> dict:
    """
    Classify an asset's execution split from its ownership status.

    This is a thin wrapper around classify_by_authority that
    respects the ownership-to-authority mapping when the asset row
    carries an `ownership_status` column. When the column is
    missing, falls back to the asset-type default.
    """
    authority = _AUTHORITY_BY_OWNERSHIP.get(
        ownership_status,
        _DEFAULT_AUTHORITY_BY_TYPE.get(asset_type, "advisory"),
    )
    return {
        "authority": authority,
        "split": classify_by_authority(asset_type, authority),
    }


_AUTHORITY_BY_OWNERSHIP = {
    "developer_held":      "full_control",
    "sold":                "advisory",
    "public_transferred":  "advisory",
    "strata_jmb":          "shared",
}