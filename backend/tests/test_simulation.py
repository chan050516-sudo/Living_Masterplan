"""Tests for B4 Simulation Engine."""

import pytest
from app.simulation.time_anchors import resolve_phase, Phase, interventions_for_asset
from app.simulation.occupancy import damped_occupancy, target_occupancy_from_dsr
from app.simulation.population import project_population
from app.simulation.interventions import apply_intervention
from app.simulation.supply import active_projects_in_year


# ---- Population ---------------------------------------------------------

def test_project_population_zero_years():
    assert project_population(8200, 2026, 2026, 0.02) == 8200


def test_project_population_growth():
    p = project_population(8200, 2026, 2030, 0.02)
    expected = 8200 * (1.02 ** 4)
    assert abs(p - expected) < 0.01


def test_project_population_multi_decade():
    p = project_population(8200, 2026, 2033, 0.02)
    expected = 8200 * (1.02 ** 7)
    assert abs(p - expected) < 0.01


# ---- Occupancy damped ---------------------------------------------------

def test_damped_occupancy_converges_up():
    # prev = 0.2, target = 0.8, lambda = 0.35 → new = 0.2 + 0.35*0.6 = 0.41
    new = damped_occupancy(0.2, 0.8, 0.35, 2027)
    assert abs(new - 0.41) < 0.001


def test_damped_occupancy_tipping_point():
    # prev = 0.15 (below critical 0.30), kappa = 0.5 → penalty = 0.5 * (0.15)^2 = 0.011
    new_with_tip = damped_occupancy(0.15, 0.8, 0.35, 2027,
                                     critical_threshold=0.30, kappa=0.5)
    new_without = damped_occupancy(0.15, 0.8, 0.35, 2027)
    assert new_with_tip < new_without


def test_damped_occupancy_no_tip_above_critical():
    new_a = damped_occupancy(0.5, 0.8, 0.35, 2027,
                              critical_threshold=0.30, kappa=0.5)
    new_b = damped_occupancy(0.5, 0.8, 0.35, 2027)
    assert new_a == new_b


def test_target_occupancy_dsr_above_one():
    assert target_occupancy_from_dsr(1.5) == 0.98


def test_target_occupancy_dsr_low():
    assert target_occupancy_from_dsr(0.4) == 0.4


def test_target_occupancy_dsr_none():
    assert target_occupancy_from_dsr(None) == 0.5


# ---- Time anchors -------------------------------------------------------

def test_resolve_phase_pre():
    intv = {"construction_start_year": 2027, "activation_year": 2028}
    assert resolve_phase(2026, intv) == Phase.PRE


def test_resolve_phase_during():
    intv = {"construction_start_year": 2027, "activation_year": 2028}
    assert resolve_phase(2027, intv) == Phase.DURING


def test_resolve_phase_post():
    intv = {"construction_start_year": 2027, "activation_year": 2028}
    assert resolve_phase(2028, intv) == Phase.POST
    assert resolve_phase(2033, intv) == Phase.POST


# ---- Interventions ------------------------------------------------------

def test_apply_repurpose():
    asset = {
        "asset_id": "B-03",
        "asset_type": "commercial",
        "land_use": "commercial",
        "capacity": 80,
        "opex_annual_rm": 820000,
    }
    intv = {
        "intervention_type": "repurpose",
        "parameters_json": '{"to": "community_facility", "new_capacity": 200}',
        "opex_delta_rm": 60000,
    }
    new = apply_intervention(asset, intv)
    assert new["asset_type"] == "community_facility"
    assert new["land_use"] == "community_facility"
    assert new["capacity"] == 200
    assert new["opex_annual_rm"] == 880000


def test_apply_retrofit():
    asset = {"maintenance_annual_rm": 100000, "capex_initial_rm": 1000000}
    intv = {
        "intervention_type": "retrofit",
        "parameters_json": "{}",
        "capex_delta_rm": 500000,
    }
    new = apply_intervention(asset, intv)
    assert new["maintenance_annual_rm"] == 80000   # 20% reduction
    assert new["capex_initial_rm"] == 1500000


def test_apply_unknown_type_no_change():
    asset = {"asset_id": "X"}
    intv = {"intervention_type": "mystery", "parameters_json": "{}"}
    new = apply_intervention(asset, intv)
    assert new == asset


# ---- Supply -------------------------------------------------------------

def test_active_projects_none():
    import pandas as pd
    assert active_projects_in_year(pd.DataFrame(), 2030, "SC-CURRENT") == []


def test_active_projects_cancelled_skipped():
    import pandas as pd
    df = pd.DataFrame([{
        "project_status": "cancelled",
        "planned_delivery_year": 2028,
        "gfa_m2": 12000,
    }])
    assert active_projects_in_year(df, 2030, "SC-CURRENT") == []


def test_active_projects_delivered():
    import pandas as pd
    df = pd.DataFrame([{
        "project_status": "proposed",
        "planned_delivery_year": 2028,
        "gfa_m2": 12000,
    }])
    active = active_projects_in_year(df, 2030, "SC-CURRENT")
    assert len(active) == 1


def test_active_projects_not_yet_delivered():
    import pandas as pd
    df = pd.DataFrame([{
        "project_status": "proposed",
        "planned_delivery_year": 2030,
        "gfa_m2": 12000,
    }])
    assert active_projects_in_year(df, 2028, "SC-CURRENT") == []


# ---- Integration --------------------------------------------------------

def test_simulate_sc_current_runs():
    from app.simulation.engine import simulate_scenario
    result = simulate_scenario("SC-CURRENT")
    assert result["scenario_id"] == "SC-CURRENT"
    assert "years" in result
    assert "2026" in result["years"]
    assert "2033" in result["years"]
    assert "comparison" in result
    assert "map_diff" in result


def test_simulate_sc_repurpose_runs():
    from app.simulation.engine import simulate_scenario
    result = simulate_scenario("SC-REPURPOSE")
    assert result["scenario_id"] == "SC-REPURPOSE"
    # B-03 should be repurposed by 2028
    state_2028 = result["years"]["2028"]["assets"].get("B-03", {})
    assert state_2028.get("metric_source") == "simulated"