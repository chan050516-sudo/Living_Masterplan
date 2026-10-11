"""Map (asset_type, layer triggers) to a final deadspace status enum."""


def decide_status(asset_type: str, layer1: dict, layer2: dict, layer3: dict) -> str:
    """
    Decide the final status for a single asset.

    Priority order:
      1. No layer triggered -> healthy
      2. No actionable intervention -> monitor
      3. Type-specific classification

    Important semantic rules:
      - green_space is NEVER a "deadspace" (it has ecological value by nature).
      - residential is NEVER a "deadspace" (it is not a revenue asset in our scope).
    """
    l1 = layer1["triggered"]
    l2 = layer2["triggered"]
    l3 = layer3["actionable"]

    # 1. Nothing triggered
    if not (l1 or l2):
        return "healthy"

    # 2. Something triggered but no actionable path
    if not l3:
        return "monitor"

    # 3. Type-specific classification
    if asset_type == "commercial":
        # A commercial asset with both underperformance AND low value realization
        # is our strict definition of a deadspace candidate.
        if l1 and l2:
            return "deadspace_candidate"
        # A commercial asset with only one layer triggered is monitored,
        # not marked as a full deadspace.
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
        # Any trigger on a green space is an "improvement opportunity",
        # never a "deadspace" — green space has intrinsic value.
        if l1 or l2:
            return "improvement_opportunity"
        return "monitor"

    if asset_type == "residential":
        # Residential reached this point means l1 or l2 triggered.
        # We do not classify residential as deadspace in this iteration;
        # it is flagged for attention but not actioned by the demo engine.
        return "monitor"

    # Unknown asset type with a trigger: default to monitor (conservative).
    return "monitor"