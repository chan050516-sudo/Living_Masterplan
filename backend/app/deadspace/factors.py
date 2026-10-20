"""Contributing factors — flag-based attribution.

Phase 3 change: factors no longer derive from scoring components.
Each flag contributes a share proportional to its weight relative to
the total weight of all flags on the asset.
"""

from .urgency import FLAG_WEIGHTS


def compute_factors(layer1: dict, layer2: dict) -> list:
    """
    Return a list of { factor, contribution } sorted descending.
    Contributions sum to 1.0 when any flag is present.

    FIX: dropped the unused `metrics` parameter.
    """
    all_flags = list(layer1.get("reasons", [])) + list(layer2.get("reasons", []))
    if not all_flags:
        return []

    weights = {f: FLAG_WEIGHTS.get(f, 1) for f in all_flags}
    total = sum(weights.values())
    if total <= 0:
        return []

    items = [
        {"factor": f, "contribution": round(w / total, 4)}
        for f, w in weights.items()
    ]
    items.sort(key=lambda x: x["contribution"], reverse=True)
    return items