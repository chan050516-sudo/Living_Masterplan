"""Damped occupancy adjustment with optional tipping-point acceleration.

O_t = O_{t-1} + lambda * (O*_t - O_{t-1}) - kappa * I(O_{t-1} < O_critical) * (O_critical - O_{t-1})^2
"""


def damped_occupancy(prev_occupancy: float, target_occupancy: float,
                     lambda_: float, year: int,
                     critical_threshold: float = None,
                     kappa: float = 0.0) -> float:
    """
    prev_occupancy, target_occupancy in [0, 1].
    """
    base = prev_occupancy + lambda_ * (target_occupancy - prev_occupancy)

    if critical_threshold is not None and kappa > 0:
        if prev_occupancy < critical_threshold:
            gap = critical_threshold - prev_occupancy
            base -= kappa * (gap ** 2)

    return max(0.0, min(1.0, base))


def target_occupancy_from_dsr(dsr: float) -> float:
    """
    If dsr >= 1, demand >= supply → target high occupancy.
    If dsr < 1, use dsr as proportional target.
    Capped to [0.05, 0.98].
    """
    if dsr is None:
        return 0.5
    target = min(dsr, 0.98)
    return max(0.05, target)