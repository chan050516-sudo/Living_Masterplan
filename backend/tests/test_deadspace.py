"""Tests for B6 Deadspace Detector (flag-based)."""

import pandas as pd
from app.deadspace.layer1 import evaluate as layer1_eval
from app.deadspace.layer2 import evaluate as layer2_eval
from app.deadspace.layer3 import evaluate as layer3_eval
from app.deadspace.status import decide_status
from app.deadspace.factors import compute_factors
from app.deadspace.urgency import compute_urgency_index


def test_layer1_commercial_deadspace():
    metrics = {
        "occupancy_rate": 0.21,
        "vacancy_duration_months": 14,
        "dsr": 0.35,
        "coverage_ratio_5min_walk": 0.15,
        "coverage_ratio_10min_drive": 0.35,
    }
    r = layer1_eval("commercial", metrics)
    assert r["triggered"] is True
    assert "low_occupancy" in r["reasons"]
    assert "long_vacancy" in r["reasons"]
    assert "dsr_below_threshold" in r["reasons"]
    assert "walking_accessibility_deficit" in r["reasons"]


def test_layer1_commercial_healthy():
    metrics = {
        "occupancy_rate": 0.85,
        "vacancy_duration_months": 1,
        "dsr": 1.05,
        "coverage_ratio_5min_walk": 0.65,
        "coverage_ratio_10min_drive": 0.80,
    }
    r = layer1_eval("commercial", metrics)
    assert r["triggered"] is False


def test_layer2_commercial_negative_noi():
    asset = {"maintenance_annual_rm": 180000}
    metrics = {
        "noi_rm": -50962,
        "maintenance_surge_rm": 190962,
    }
    r = layer2_eval("commercial", asset, metrics)
    assert r["triggered"] is True
    assert "negative_noi" in r["reasons"]


def test_layer3_commercial_actionable():
    r = layer3_eval("commercial")
    assert r["actionable"] is True
    assert "repurpose" in r["candidate_interventions"]


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


def test_factors_sum_to_one():
    layer1 = {"triggered": True, "reasons": ["low_occupancy"]}
    layer2 = {"triggered": True, "reasons": ["negative_noi"]}
    factors = compute_factors({}, layer1, layer2)
    total = sum(f["contribution"] for f in factors)
    assert abs(total - 1.0) < 0.001


def test_urgency_index():
    assert compute_urgency_index([]) == 0.0
    assert compute_urgency_index(["negative_noi"]) == 3.0
    assert compute_urgency_index(["negative_noi", "low_occupancy"]) == 5.0


def test_detect_deadspace_no_score_required():
    from app.deadspace.detector import detect_deadspace_for_asset

    asset = pd.Series({
        "asset_id": "B-03",
        "asset_type": "commercial",
        "subtype": "convenience_retail",
        "maintenance_annual_rm": 180000,
    })
    metrics = pd.Series({
        "year": 2026,
        "occupancy_rate": 0.21,
        "vacancy_duration_months": 14,
        "dsr": 0.35,
        "noi_rm": -50962,
        "coverage_ratio_5min_walk": 0.15,
        "coverage_ratio_10min_drive": 0.30,
    })
    assumptions = {"deadspace": {"layer1": {}, "layer2": {}}}

    result = detect_deadspace_for_asset(asset, metrics, assumptions)
    assert result["status"] in ("deadspace_candidate", "monitor")
    assert "urgency_index" in result
    assert result["urgency_index"] > 0