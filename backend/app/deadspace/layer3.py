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

# ---------------------------------------------------------------
# Intervention legality per asset type
# ---------------------------------------------------------------
# This is a pure legality check: given an asset type, which
# intervention types are architecturally / legally meaningful?
# It says nothing about who can execute them. See
# `classify_by_authority` for the execution split.

ACTION_SPACE = {
    "commercial": [
        "repurpose", "retrofit", "pedestrian_upgrade", "green_corridor",
    ],
    "community_facility": [
        "retrofit", "pedestrian_upgrade", "repurpose",
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
    "residential": [
        "repurpose", "retrofit", "pedestrian_upgrade",
    ],
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


def evaluate(asset_type: str, diagnostics: dict = None) -> dict:
    """
    `diagnostics` is reserved for future extensions (budget caps,
    land-use rules, constraint filters). Phase 3 reads only the static
    action space.
    """
    candidates = ACTION_SPACE.get(asset_type, [])
    return {
        "actionable": len(candidates) > 0,
        "candidate_interventions": candidates,
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