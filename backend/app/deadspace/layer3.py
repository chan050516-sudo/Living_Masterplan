"""Layer 3 — Actionability.

Whether an actionable improvement strategy exists.
Reads the intervention library. Does NOT invent new types.
"""

ACTION_SPACE = {
    "commercial":         ["repurpose", "retrofit", "pedestrian_upgrade", "green_corridor"],
    "community_facility": ["retrofit", "pedestrian_upgrade", "repurpose"],
    "green_space":        ["green_corridor", "pedestrian_upgrade"],
    # Phase 11 — interim_solar_farm added for undeveloped parcels
    "undeveloped_parcel": ["new_development", "delay_development", "interim_solar_farm"],
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