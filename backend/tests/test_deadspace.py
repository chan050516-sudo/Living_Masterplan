"""Tests for B6 Deadspace Detector."""

import pytest
from app.deadspace.layer1 import evaluate as layer1_eval
from app.deadspace.layer2 import evaluate as layer2_eval
from app.deadspace.layer3 import evaluate as layer3_eval
from app.deadspace.status import decide_status
from app.deadspace.factors import compute_factors


# ---- Layer 1 -------------------------------------------------------------

def test_layer1_commercial_deadspace():
    metrics = {
        "performance_score": 5.0,
        "occupancy_rate": 0.21,
        "vacancy_duration_months": 14,
        "dsr": 0.35,
    }
    r = layer1_eval("commercial", metrics)
    assert r["triggered"] is True
    assert "low_overall_score" in r["reasons"]
    assert "low_occupancy" in r["reasons"]
    assert "long_vacancy" in r["reasons"]
    assert "dsr_below_threshold" in r["reasons"]


def test_layer1_commercial_healthy():
    metrics = {
        "performance_score": 72.0,
        "occupancy_rate": 0.85,
        "vacancy_duration_months": 1,
        "dsr": 1.05,
    }
    r = layer1_eval("commercial", metrics)
    assert r["triggered"] is False


def test_layer1_facility_low_utilisation():
    metrics = {"performance_score": 55.0, "utilisation_rate": 0.22}
    r = layer1_eval("community_facility", metrics)
    assert r["triggered"] is True
    assert "low_utilisation" in r["reasons"]


def test_layer1_parcel_negative_gap():
    metrics = {"performance_score": 30.0, "demand_supply_gap": -4326}
    r = layer1_eval("undeveloped_parcel", metrics)
    assert r["triggered"] is True
    assert "negative_demand_supply_gap" in r["reasons"]


# ---- Layer 2 -------------------------------------------------------------

def test_layer2_commercial_negative_noi():
    asset = {"maintenance_annual_rm": 180000}
    metrics = {
        "noi_rm": -50962,
        "maintenance_surge_rm": 190962,
    }
    r = layer2_eval("commercial", asset, metrics)
    assert r["triggered"] is True
    assert "negative_noi" in r["reasons"]
    assert "maintenance_surge_high" not in r["reasons"]


def test_layer2_commercial_maintenance_surge():
    asset = {"maintenance_annual_rm": 100000}
    metrics = {
        "noi_rm": 500000,
        "maintenance_surge_rm": 200000,
    }
    r = layer2_eval("commercial", asset, metrics)
    assert "maintenance_surge_high" in r["reasons"]


def test_layer2_green_low_access():
    metrics = {"accessibility_score": 30, "canopy_coverage": 0.15}
    r = layer2_eval("green_space", {}, metrics)
    assert r["triggered"] is True
    assert "low_accessibility_high_ecological_value" in r["reasons"]


def test_layer2_facility_insufficient_coverage():
    metrics = {"service_coverage": 0.45}
    r = layer2_eval("community_facility", {}, metrics)
    assert "insufficient_coverage" in r["reasons"]


# ---- Layer 3 -------------------------------------------------------------

def test_layer3_commercial_actionable():
    r = layer3_eval("commercial")
    assert r["actionable"] is True
    assert "repurpose" in r["candidate_interventions"]


def test_layer3_unknown_asset():
    r = layer3_eval("mystery")
    assert r["actionable"] is False
    assert r["candidate_interventions"] == []


# ---- Status --------------------------------------------------------------

def test_status_healthy():
    status = decide_status(
        "commercial",
        {"triggered": False, "reasons": []},
        {"triggered": False, "reasons": []},
        {"actionable": True, "candidate_interventions": ["repurpose"]},
    )
    assert status == "healthy"


def test_status_deadspace_candidate():
    status = decide_status(
        "commercial",
        {"triggered": True, "reasons": ["low_occupancy"]},
        {"triggered": True, "reasons": ["negative_noi"]},
        {"actionable": True, "candidate_interventions": ["repurpose"]},
    )
    assert status == "deadspace_candidate"


def test_status_monitor_when_no_action():
    status = decide_status(
        "mystery",
        {"triggered": True, "reasons": ["something"]},
        {"triggered": True, "reasons": ["something"]},
        {"actionable": False, "candidate_interventions": []},
    )
    assert status == "monitor"


def test_status_underperforming_facility():
    status = decide_status(
        "community_facility",
        {"triggered": True, "reasons": ["low_utilisation"]},
        {"triggered": False, "reasons": []},
        {"actionable": True, "candidate_interventions": ["retrofit"]},
    )
    assert status == "underperforming_facility"


def test_status_development_risk():
    status = decide_status(
        "undeveloped_parcel",
        {"triggered": True, "reasons": ["negative_demand_supply_gap"]},
        {"triggered": False, "reasons": []},
        {"actionable": True, "candidate_interventions": ["new_development"]},
    )
    assert status == "development_risk"


def test_status_improvement_opportunity():
    status = decide_status(
        "green_space",
        {"triggered": False, "reasons": []},
        {"triggered": True, "reasons": ["low_accessibility_high_ecological_value"]},
        {"actionable": True, "candidate_interventions": ["green_corridor"]},
    )
    assert status == "improvement_opportunity"


# ---- Factors -------------------------------------------------------------

def test_factors_sum_to_one():
    component_scores = {
        "financial": 0.0,
        "occupancy": 0.0,
        "demand": 0.0,
        "accessibility": 95.8,
        "environment": 20.0,
    }
    weights_used = {
        "financial": 0.35,
        "occupancy": 0.25,
        "demand": 0.20,
        "accessibility": 0.10,
        "environment": 0.10,
    }
    factors = compute_factors(component_scores, weights_used)
    total = sum(f["contribution"] for f in factors)
    assert abs(total - 1.0) < 0.001
    # Sorted descending
    assert factors[0]["contribution"] >= factors[-1]["contribution"]


def test_factors_empty_when_no_gaps():
    component_scores = {"a": 100.0, "b": 100.0}
    weights_used = {"a": 0.5, "b": 0.5}
    factors = compute_factors(component_scores, weights_used)
    assert factors == []