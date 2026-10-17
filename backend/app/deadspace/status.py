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
    """
    l1 = layer1["triggered"]
    l2 = layer2["triggered"]
    l3 = layer3["actionable"]

    if not (l1 or l2):
        return "healthy"

    if not l3:
        return "monitor"

    if asset_type == "commercial":
        if l1 and l2:
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
        # Phase 15 — developer-held unsold residential can be a
        # deadspace candidate: the developer built units the market
        # is not absorbing. Sold residential is flagged for
        # attention but not classified as deadspace, because the
        # developer has no execution power over it.
        if authority == "full_control":
            if l1 and l2:
                return "deadspace_candidate"
            return "monitor"
        return "monitor"

    return "monitor"