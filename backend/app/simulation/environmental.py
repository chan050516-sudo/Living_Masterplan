"""Environmental model — scenario-level helpers.

Asset-level energy and carbon calculations live in
`derived/environmental.py` so that B3 can use them without importing
the simulation layer.

This module re-exports those functions for backward compatibility and
adds scenario-level aggregation (10-year totals).
"""

# Re-exports so existing `from .environmental import ...` imports
# in simulation/engine.py continue to work unchanged.
from ..derived.environmental import (  # noqa: F401
    operational_carbon,
    energy_from_intensity,
    energy_from_subtype,
    embodied_carbon,
)


def carbon_10y_total(
    operational_annual_tco2e: float,
    embodied_oneshot_tco2e: float,
    horizon_years: int = 10,
) -> float:
    """
    Unify operational carbon (annual) and embodied carbon (one-shot)
    into a comparable 10-year total.
    """
    return operational_annual_tco2e * horizon_years + embodied_oneshot_tco2e