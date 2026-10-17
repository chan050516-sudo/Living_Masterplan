"""Map (asset_type, layer triggers) to a final deadspace status enum."""


def decide_status(asset_type, layer1, layer2, layer3, authority=None):
    """
    Decide the final status for a single asset.

    Priority order:
      1. No layer triggered -> healthy
      2. No actionable intervention -> monitor
      3. Type-specific classification

    Phase 15 — authority-aware classification:
      - residential + sold / advisory    -> monitor (owner-occupied)
      - residential + developer_held     -> deadspace_candidate if both
                                            layers trigger (built but
                                            unsold)
      - green_space is NEVER deadspace (intrinsic ecological value)

    Phase B.3 — rapid_decline override.
      A commercial or developer-held residential asset with a
      rapid_decline trajectory is failing RIGHT NOW. Requiring layer2
      confirmation would postpone the intervention by a full year —
      exactly when postponement is most expensive. Rapid decline
      plus ANY snapshot flag is sufficient for deadspace_candidate.
      The full l1 AND l2 requirement still applies to slow declines,
      where the asset is still functional and the operator has time.
    """
    l1 = layer1["triggered"]
    l2 = layer2["triggered"]
    l3 = layer3["actionable"]

    if not (l1 or l2):
        return "healthy"

    if not l3:
        return "monitor"

    reasons = layer1.get("reasons", [])
    has_rapid_decline = "rapid_decline" in reasons

    if asset_type == "commercial":
        # Rapid decline plus any flagged signal = deadspace candidate.
        # Slow decline still requires both layers.
        if has_rapid_decline or (l1 and l2):
            return "deadspace_candidate"
        return "monitor"

    if asset_type == "community_facility":
        if l1:
            return "underperforming_facility"
        return "monitor"

    if asset_type == "undeveloped_parcel":
        if l1 or l2:
            return "development_risk"
        return "monitor"

    if asset_type == "green_space":
        if l1 or l2:
            return "improvement_opportunity"
        return "monitor"

    if asset_type == "residential":
        if authority == "full_control":
            # Same rule as commercial: rapid decline + any signal
            # crosses into deadspace_candidate. Slow decline still
            # requires both layers.
            if has_rapid_decline or (l1 and l2):
                return "deadspace_candidate"
            return "monitor"
        return "monitor"

    return "monitor"