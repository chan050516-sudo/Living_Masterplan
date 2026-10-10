"""Weighted scoring with hard gate + optional geometric mean."""

from .components import RESOLVERS
from ..derived.normalize import hard_gate, geometric_mean


def score_asset(asset, metrics, weights, benchmarks, scoring_options=None):
    """
    Compute component scores and overall score for one asset.

    Returns:
        {
          "asset_id", "asset_type", "overall_score",
          "component_scores", "weights_used",
          "financial_score", "environmental_score", "social_score",
          "data_completeness", "confidence",
        }
    """
    scoring_options = scoring_options or {}
    atype = asset["asset_type"]
    resolver = RESOLVERS.get(atype)
    if resolver is None:
        return None

    components = resolver(asset, metrics, benchmarks)

    # Available components only
    available = {k: v for k, v in components.items() if v is not None}
    weights_all = weights.get(atype, {})

    if not available or not weights_all:
        return None

    # Restrict weights to available components and re-normalize
    total_w = sum(weights_all.get(k, 0) for k in available)
    if total_w <= 0:
        return None
    norm_weights = {k: weights_all.get(k, 0) / total_w for k in available}

    # Weighted linear combination
    if scoring_options.get("use_geometric_mean", False):
        overall = geometric_mean(available, norm_weights)
    else:
        overall = sum(available[k] * norm_weights[k] for k in available)

    # Hard gate
    threshold = scoring_options.get("hard_gate_threshold", 20)
    multiplier = scoring_options.get("hard_gate_multiplier", 1.5)
    overall = hard_gate(overall, available, threshold=threshold, multiplier=multiplier)

    # Data completeness (share of expected components present)
    expected_n = len(weights_all)
    data_completeness = len(available) / expected_n if expected_n else 0.0

    # Confidence: high if all present, medium if ≥60%, low otherwise
    if data_completeness >= 0.99:
        confidence = "high"
    elif data_completeness >= 0.60:
        confidence = "medium"
    else:
        confidence = "low"

    # Three-pillar rollup (for UI)
    def _avg(keys):
        vals = [available[k] for k in keys if k in available]
        return sum(vals) / len(vals) if vals else None

    financial_score = _avg(["financial", "cost_efficiency", "development_feasibility"])
    environmental_score = _avg(["environment", "thermal", "canopy", "green_coverage", "usage"])
    social_score = _avg(["accessibility", "coverage", "utilisation", "occupancy", "demand"])

    return {
        "asset_id": asset["asset_id"],
        "asset_type": atype,
        "overall_score": round(overall, 2),
        "financial_score": round(financial_score, 2) if financial_score is not None else None,
        "environmental_score": round(environmental_score, 2) if environmental_score is not None else None,
        "social_score": round(social_score, 2) if social_score is not None else None,
        "component_scores": {k: round(v, 2) for k, v in available.items()},
        "weights_used": norm_weights,
        "data_completeness": round(data_completeness, 3),
        "confidence": confidence,
    }