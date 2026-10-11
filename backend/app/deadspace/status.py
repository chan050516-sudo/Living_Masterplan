"""Map (asset_type, layer triggers) to a final deadspace status enum."""


def decide_status(asset_type: str, layer1: dict, layer2: dict, layer3: dict) -> str:
    l1 = layer1["triggered"]
    l2 = layer2["triggered"]
    l3 = layer3["actionable"]

    if not (l1 or l2):
        return "healthy"

    if not l3:
        return "monitor"

    if asset_type == "commercial" and l1 and l2:
        return "deadspace_candidate"

    if asset_type == "community_facility" and l1:
        return "underperforming_facility"

    if asset_type == "undeveloped_parcel" and (l1 or l2):
        return "development_risk"

    # green_space: any trigger → improvement opportunity (not deadspace)
    if asset_type == "green_space" and (l1 or l2):
        return "improvement_opportunity"

    if asset_type == "residential":
        # Residential reached here means l1 or l2 triggered.
        # Never mark as healthy; use monitor (needs attention).
        return "monitor"

    # Commercial/facility fallback
    if l1:
        return "deadspace_candidate"

    return "monitor"