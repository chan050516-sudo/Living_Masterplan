"""Three normalisation functions from Part 4.2 plus scoring helpers.

NOTE: this module is reserved for B5 (asset scoring), which is not yet
implemented. None of the helpers below are consumed by B3 / B4 / B6.
They are kept here so that B5 can import them directly when it lands.
"""

import math
from typing import Optional


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def s_benefit(x: Optional[float], L: float, U: float) -> Optional[float]:
    """
    Higher is better. Returns 0-100.
    S_benefit(x) = 100 * clip((x - L) / (U - L), 0, 1)
    """
    if x is None or math.isnan(x):
        return None
    if U == L:
        return 100.0
    return 100.0 * _clip((x - L) / (U - L))


def s_cost(x: Optional[float], L: float, U: float) -> Optional[float]:
    """
    Lower is better. Returns 0-100.
    S_cost(x) = 100 * clip((U - x) / (U - L), 0, 1)
    """
    if x is None or math.isnan(x):
        return None
    if U == L:
        return 100.0
    return 100.0 * _clip((U - x) / (U - L))


def s_target(x: Optional[float], L: float, U: float, H: float) -> Optional[float]:
    """
    Target range. Returns 0-100.
      x < L:      100 * x / L
      L <= x <= U: 100
      U < x < H:  100 * (H - x) / (H - U)
      x >= H:     0
    """
    if x is None or math.isnan(x):
        return None
    if x < L:
        return 100.0 * x / L if L > 0 else 0.0
    if L <= x <= U:
        return 100.0
    if U < x < H:
        return 100.0 * (H - x) / (H - U) if H > U else 0.0
    return 0.0


def hard_gate(
    weighted_score: float,
    component_scores: dict,
    threshold: float = 20.0,
    multiplier: float = 1.5,
) -> float:
    """
    Non-compensatory gate. If any component < threshold,
    cap the overall score at multiplier * min(component).
    Used by B5 (Phase 2).
    """
    valid = [v for v in component_scores.values() if v is not None]
    if not valid:
        return weighted_score
    min_component = min(valid)
    if min_component < threshold:
        cap = multiplier * min_component
        return min(weighted_score, cap)
    return weighted_score


def geometric_mean(component_scores: dict, weights: dict) -> float:
    """
    Cobb-Douglas aggregation. Use when weights.yml says use_geometric_mean: true.
    Safe against zero by adding epsilon.
    """
    eps = 1e-6
    total = 1.0
    total_w = 0.0
    for key, w in weights.items():
        s = component_scores.get(key)
        if s is None:
            continue
        total *= max(s, eps) ** w
        total_w += w
    if total_w == 0:
        return 0.0
    return total ** (1.0 / total_w)