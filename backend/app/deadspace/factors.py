"""Contributing factors — normalized gap shares.

For each component score, gap = 100 - score. Contribution = gap * weight / total_gap.
"""


def compute_factors(component_scores: dict, weights_used: dict) -> list:
    """
    Returns list of { factor, contribution } sorted descending.
    Contributions sum to 1.0 (or empty list if no gaps).
    """
    gaps = {}
    for k, s in component_scores.items():
        w = weights_used.get(k, 0.0)
        if s is None or w <= 0:
            continue
        gaps[k] = max(0.0, 100.0 - float(s)) * w

    total = sum(gaps.values())
    if total <= 0:
        return []

    items = [
        {"factor": k, "contribution": round(v / total, 4)}
        for k, v in gaps.items()
    ]
    items.sort(key=lambda x: x["contribution"], reverse=True)
    return items