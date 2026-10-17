"""Urgency index — internal ranking key for the Deadspace List."""

from typing import List


FLAG_WEIGHTS = {
    # Observed flags
    "negative_noi":                 3,
    "low_occupancy":                2,
    "long_vacancy":                 2,
    "low_utilisation":              2,
    # Derived diagnostic flags
    "dsr_below_threshold":          1,
    "negative_demand_supply_gap":   1,
    "walking_accessibility_deficit":1,
    "driving_accessibility_deficit":1,
    "demographic_mismatch":         1,
    "low_neighborhood_diversity":   1,
    # Phase 11 — stranded carbon
    "high_stranded_carbon":         2,
    # Layer 2 green_space variants
    "low_accessibility":                         1,
    "low_accessibility_high_ecological_value":   1,
    "insufficient_coverage":                     1,
    "maintenance_surge_high":                    1,
    "weak_future_demand":                        1,
    # Phase 15 — unsold inventory: built but unused
    "built_value_not_realized":     2,
    # Phase 16 — early-warning and anomaly flags
    "below_benchmark_occupancy":               1,
    "high_stranded_carbon_ratio_small_asset":  1,
    "high_uhi_exposure":                       1,
    "uhi_data_anomaly":                        1,
    "low_green_coverage":                      1,
    "low_canopy_coverage":                     1,
    "low_green_per_capita":                    1,
    # Phase B.2 — partial death inside a mixed-use commercial asset.
    # A dead subtype in an otherwise healthy mall is significant:
    # the aggregate occupancy hides a whole floor of unused capital.
    "subtype_mix_dead":    3,
    "subtype_mix_low":     1,
}


def compute_urgency_index(flags: List[str]) -> float:
    """Sum the weights of all flags."""
    return float(sum(FLAG_WEIGHTS.get(f, 1) for f in flags))