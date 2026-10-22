"""Urgency index — internal ranking key for the Deadspace List.

Phase B.3 — flag grouping.

The flags emitted by layer1 and layer2 are not independent. A
commercial asset that is "not being used" typically triggers
low_occupancy, long_vacancy, AND high_stranded_carbon simultaneously,
because all three are consequences of the same fact. Summing their
weights treats the failure as if it were described three separate
times, so an asset whose data happens to be well-documented gets a
higher urgency than one whose data is sparse.

The grouping recognises this: within each root-cause group, only the
highest-weight flag contributes. Independent flags (rapid_decline,
negative_demand_supply_gap, ...) are not grouped and add on top.

The effect is that the deadspace list orders by depth of failure,
not by richness of description.
"""

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
    "subtype_mix_dead":    3,
    "subtype_mix_low":     1,
    # Phase B.3 — trajectory signals from B3.
    "rapid_decline":        2,   # abrupt drop; asset is failing now
    "chronic_stagnation":   1,   # long-term low; stable at low level
    "falling_from_healthy": 1,   # was healthy, drifting down
}


# Phase B.3 — group flags by root cause.
#
# Within a group, only the highest-weight flag contributes to the
# urgency index. The grouping is deliberately conservative: a group
# only exists when the flags genuinely describe the same underlying
# state. Flags not listed here are treated as independent.
_FLAG_GROUPS = {
    "occupancy": {
        "low_occupancy",
        "long_vacancy",
        "high_stranded_carbon",
        "high_stranded_carbon_ratio_small_asset",
        "below_benchmark_occupancy",
        "built_value_not_realized",
        "chronic_stagnation",   # the temporal version of low_occupancy
    },
    "financial": {
        "negative_noi",
        "dsr_below_threshold",
        "maintenance_surge_high",
    },
    "accessibility": {
        "walking_accessibility_deficit",
        "driving_accessibility_deficit",
        "low_accessibility",
        "low_accessibility_high_ecological_value",
    },
    "environmental": {
        "high_uhi_exposure",
        "uhi_data_anomaly",
        "low_green_coverage",
        "low_canopy_coverage",
        "low_green_per_capita",
    },
    "subtype_mix": {
        "subtype_mix_dead",
        "subtype_mix_low",
    },
}

# Reverse map: flag -> group name. Precomputed for speed.
_FLAG_GROUP_OF = {
    f: group
    for group, flags in _FLAG_GROUPS.items()
    for f in flags
}


def compute_urgency_index(flags: List[str]) -> float:
    """
    Sum the weights of all flags, deduplicated by root cause.

    A group of correlated flags contributes only the weight of its
    strongest member. Un-grouped flags contribute their full weight.
    """
    grouped: dict = {}
    ungrouped: float = 0.0

    for f in flags:
        w = FLAG_WEIGHTS.get(f, 1)
        group = _FLAG_GROUP_OF.get(f)
        if group is not None:
            grouped[group] = max(grouped.get(group, 0), w)
        else:
            ungrouped += w

    return float(sum(grouped.values()) + ungrouped)