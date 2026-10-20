"""Tests for Phase 5 simulation fixes."""

import pandas as pd
from app.simulation.engine import simulate_scenario


def test_sc_current_carbon_stable():
    """
    SC-CURRENT has no intervention; total carbon should not change
    materially between the base year and the final year for the same
    asset.
    """
    result = simulate_scenario("SC-CURRENT")
    before = result["years"]["2026"]["assets"]["B-03"]["carbon_operational_tco2e"]
    after = result["years"]["2033"]["assets"]["B-03"]["carbon_operational_tco2e"]
    # No intervention: carbon should stay close to before value.
    assert abs(after - before) / before < 0.05


def test_repurpose_activates_after_construction():
    """
    SC-REPURPOSE constructs 2027-2028. B-03 should be active by 2033,
    with utilisation set from the LLM expectation (0.78).
    """
    result = simulate_scenario("SC-REPURPOSE")
    state_2033 = result["years"]["2033"]["assets"]["B-03"]
    # After activation, utilisation should reflect the expected value.
    assert state_2033.get("utilisation_rate", 0) > 0.5


def test_comparison_uses_facility_primary_metric():
    """
    SC-REPURPOSE converts B-03 to a facility. The comparison block
    should use utilisation_rate as the primary metric.
    """
    result = simulate_scenario("SC-REPURPOSE")
    metrics = result["comparison"]["metrics"]
    assert "utilisation_rate" in metrics


def test_township_metrics_present():
    result = simulate_scenario("SC-REPURPOSE")
    tm = result["comparison"]["township_metrics"]
    assert "walk_15min_avg_coverage_before" in tm
    assert "total_carbon_before_tco2e" in tm
    assert "carbon_delta_pct" in tm