"""Urgency index — internal ranking key for the Deadspace List.

Phase 3 replaces the numeric performance score with an internal-only
urgency index. This index:
  - is used ONLY to sort the deadspace list
  - is NOT shown in the UI
  - is NOT part of the scenario comparison
  - does NOT feed into B4 simulation

The name "urgency" is intentional: it conveys "how quickly should a
human look at this" rather than "how good is this asset".
"""

from typing import List


# Flag severities. Chosen so that the sum reflects overall pressure
# on the asset. These values are calibrated by hand and should be
# revisited once real outcome data is available.
FLAG_WEIGHTS = {
    # Observed flags
    "negative_noi":                 3,
    "low_occupancy":                2,
    "long_vacancy":                 2,
    "low_utilisation":              2,
    "inactive_construction":        2,
    # Derived diagnostic flags
    "dsr_below_threshold":          1,
    "negative_demand_supply_gap":   1,
    "walking_accessibility_deficit":1,
    "driving_accessibility_deficit":1,
    "demographic_mismatch":         1,
    "low_neighborhood_diversity":   1,
}


def compute_urgency_index(flags: List[str]) -> float:
    """
    Sum the weights of all flags. Higher = more urgent to look at.
    This is NOT a score. It only exists to sort the deadspace list.
    """
    return float(sum(FLAG_WEIGHTS.get(f, 1) for f in flags))