"""Flag tiers and authority-aware evaluation modes (v6.0 Phase 2).

Every flag the detector can raise is tagged with the tier of the data
behind it, so the UI and the LLM can tell an observed fact from a proxy.

  tier_1_observed        SDP internal record (only real for full_control)
  tier_2_derived         physics / network formula, authority-independent
  tier_3a_proxied        external proxy (Google Places, LBS) for sold assets
  tier_3b_counterfactual "if SDP had retained it" — simulation only
"""

_FLAGS_BY_TIER = {
    "tier_1_observed": frozenset({
        "low_occupancy", "below_benchmark_occupancy", "long_vacancy",
        "negative_noi", "noi_yield_below",
        "maintenance_surge_high",
        "subtype_mix_dead", "subtype_mix_low",
        "built_value_not_realized",
        "rapid_decline", "falling_from_healthy", "chronic_stagnation",
        "low_utilisation",
    }),
    "tier_2_derived": frozenset({
        "dsr_below_threshold",
        "walking_accessibility_deficit",
        "driving_accessibility_deficit",
        "demographic_mismatch",
        "low_neighborhood_diversity",
        "high_uhi_exposure", "uhi_data_anomaly",
        "high_stranded_carbon", "high_stranded_carbon_ratio_small_asset",
        "low_green_coverage", "low_canopy_coverage", "low_green_per_capita",
        "negative_demand_supply_gap", "weak_future_demand",
        "insufficient_coverage",
        "low_accessibility", "low_accessibility_high_ecological_value",
    }),
    "tier_3a_proxied": frozenset({
        # Operational proxies (Google Places)
        "low_occupancy_proxied",
        "long_vacancy_proxied",
        "business_presence_low",
        "business_turnover_high",
        "business_vitality_low",
        # Operational proxies (LBS)
        "low_footfall_lbs",
        "short_dwell_lbs",
        "flow_island",
        # Survival floor
        "operating_hemorrhage",
        # Cross-source
        "data_conflict",
    }),
    "tier_3b_counterfactual": frozenset({
        "noi_negative_counterfactual",
    }),
}

_TIER_OF = {f: tier for tier, flags in _FLAGS_BY_TIER.items() for f in flags}

# Flags whose input data a developer cannot see once the asset is sold.
# For non-full_control assets these come from the mock trajectory, not
# from a real record, so the detector drops them. Stranded carbon is
# tier 2 but is computed from occupancy, so it falls with it.
OPERATIONAL_FLAGS = (
    _FLAGS_BY_TIER["tier_1_observed"]
    | _FLAGS_BY_TIER["tier_3b_counterfactual"]
    | {"high_stranded_carbon", "high_stranded_carbon_ratio_small_asset"}
)

# 3a flags that say the business itself is struggling (as opposed to
# data_conflict, which says the proxies cannot be trusted).
OPERATING_PROXY_FLAGS = _FLAGS_BY_TIER["tier_3a_proxied"] - {"data_conflict", "flow_island"}

# Flags that point to a cause outside the building: people cannot reach it.
ACCESS_FLAGS = frozenset({
    "walking_accessibility_deficit",
    "driving_accessibility_deficit",
    "flow_island",
})


def tier_of(flag: str) -> str:
    return _TIER_OF.get(flag, "tier_2_derived")


def is_full_control(authority) -> bool:
    """Missing authority keeps the legacy behaviour (treated as owned)."""
    return authority in (None, "", "full_control") or authority != authority


def evaluation_mode(authority) -> str:
    """Which financial lens applies (v6.0 §1.2)."""
    if is_full_control(authority):
        return "operating_performance"
    return "developer_realization"
