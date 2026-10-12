"""Layer 3 — Actionability.

Whether an actionable improvement strategy exists.
Reads the intervention library. Does NOT invent new types.
"""

# Static mapping: asset_type -> list of intervention types applicable
ACTION_SPACE = {
    "commercial":         ["repurpose", "retrofit", "pedestrian_upgrade", "green_corridor"],
    "community_facility": ["retrofit", "pedestrian_upgrade", "repurpose"],
    "green_space":        ["green_corridor", "pedestrian_upgrade"],
    # NOTE: "green_space" used to appear in the undeveloped_parcel list,
    # but green_space is an asset_class, not an intervention type. To
    # turn a parcel into green space, propose new_development with
    # parameters.to_subtype = "park" (or pocket_park / green_corridor /
    # sports_field / water_body). This keeps the intervention vocabulary
    # consistent with interventions.schema.json.
    "undeveloped_parcel": ["new_development", "delay_development"],
    "residential":        ["retrofit", "pedestrian_upgrade"],
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