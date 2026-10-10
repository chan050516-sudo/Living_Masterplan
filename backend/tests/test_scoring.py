"""Tests for B5 scoring engine."""

import pytest
from app.scoring.score import score_asset
from app.scoring.components import RESOLVERS


BENCHMARKS = {
    "commercial": {
        "occupancy_rate": {"L": 0.4, "U": 0.85},
        "noi_yield": {"L": 0.02, "U": 0.08},
        "dsr": {"L": 0.6, "U": 1.2},
        "thermal_exposure": {"L": 0.0, "U": 100.0},
    },
    "community_facility": {
        "utilisation_rate": {"L": 0.3, "U": 0.8, "H": 1.0},
        "service_coverage": {"L": 0.5, "U": 1.0},
        "cost_per_user_rm": {"L": 0.0, "U": 200.0},
    },
    "green_space": {
        "green_coverage": {"L": 0.05, "U": 0.4},
        "canopy_coverage": {"L": 0.05, "U": 0.4},
        "green_per_capita_m2": {"L": 2.0, "U": 20.0},
        "thermal_exposure": {"L": 0.0, "U": 100.0},
    },
    "undeveloped_parcel": {
        "development_feasibility": {"L": 0.0, "U": 1.0},
        "demand_supply_gap": {"L": -1000.0, "U": 2000.0},
    },
    "residential": {
        "occupancy_rate": {"L": 0.6, "U": 0.95},
        "energy_intensity_kwh_m2": {"L": 50.0, "U": 200.0},
        "sell_through": {"L": 0.5, "U": 1.0},
    },
}

WEIGHTS = {
    "commercial": {
        "financial": 0.35, "occupancy": 0.25, "demand": 0.20,
        "accessibility": 0.10, "environment": 0.10,
    },
    "community_facility": {
        "utilisation": 0.25, "coverage": 0.25, "accessibility": 0.20,
        "cost_efficiency": 0.15, "environment": 0.15,
    },
    "green_space": {
        "green_coverage": 0.25, "canopy": 0.20, "accessibility": 0.20,
        "thermal": 0.20, "usage": 0.15,
    },
    "undeveloped_parcel": {
        "development_feasibility": 0.30, "demand": 0.25, "accessibility": 0.20,
        "environment": 0.15, "risk": 0.10,
    },
    "residential": {
        "financial": 0.35, "occupancy": 0.25, "demand": 0.20,
        "accessibility": 0.10, "environment": 0.10,
    },
}

SCORING_OPTIONS = {"hard_gate_threshold": 20, "hard_gate_multiplier": 1.5}


def _asset(aid, atype, **kw):
    d = {"asset_id": aid, "asset_type": atype, "land_area_m2": 1000}
    d.update(kw)
    return d


def _metrics(**kw):
    return kw


def test_b03_realistic():
    asset = _asset("B-03", "commercial")
    metrics = _metrics(
        occupancy_rate=0.21, noi_yield=0.03, dsr=0.6,
        accessibility_score=80, thermal_exposure=40,
    )
    r = score_asset(asset, metrics, WEIGHTS, BENCHMARKS, SCORING_OPTIONS)
    assert r is not None
    assert 0 <= r["overall_score"] <= 100
    assert r["confidence"] == "high"   # all 5 components present
    assert "financial" in r["component_scores"]


def test_b03_hard_gate():
    asset = _asset("B-03", "commercial")
    metrics = _metrics(
        occupancy_rate=0.1, noi_yield=-0.05, dsr=0.3,
        accessibility_score=90, thermal_exposure=80,
    )
    r = score_asset(asset, metrics, WEIGHTS, BENCHMARKS, SCORING_OPTIONS)
    # 3 of 5 components are below 20 → hard gate triggers
    assert r["overall_score"] <= 20.0


def test_facility_utilisation_target_range():
    asset = _asset("F-02", "community_facility")
    # utilisation = 0.5 → within target, score = 100
    metrics = _metrics(
        utilisation_rate=0.5, service_coverage=0.9,
        accessibility_score=70, cost_per_user_rm=50,
    )
    r = score_asset(asset, metrics, WEIGHTS, BENCHMARKS, SCORING_OPTIONS)
    assert r["component_scores"]["utilisation"] == 100.0


def test_green_score():
    asset = _asset("G-01", "green_space")
    metrics = _metrics(
        green_coverage=1.0, canopy_coverage=0.08,
        accessibility_score=95, thermal_exposure=72,
        green_per_capita_m2=2.857,
    )
    r = score_asset(asset, metrics, WEIGHTS, BENCHMARKS, SCORING_OPTIONS)
    assert r is not None
    assert 0 <= r["overall_score"] <= 100


def test_parcel_feasibility():
    asset = _asset("P-05", "undeveloped_parcel", land_area_m2=3600)
    metrics = _metrics(
        developable_area_m2=3600, demand_supply_gap=-4326,
        accessibility_score=86,
    )
    r = score_asset(asset, metrics, WEIGHTS, BENCHMARKS, SCORING_OPTIONS)
    assert r["component_scores"]["development_feasibility"] == 100.0
    # demand_supply_gap = -4326 is below L=-1000 → 0
    assert r["component_scores"]["demand"] == 0.0


def test_missing_components_reduce_confidence():
    asset = _asset("R-01", "residential")
    metrics = _metrics(occupancy_rate=0.92)  # only 1 of 5
    r = score_asset(asset, metrics, WEIGHTS, BENCHMARKS, SCORING_OPTIONS)
    assert r["confidence"] == "low"
    assert r["data_completeness"] < 0.5


def test_unknown_asset_type_returns_none():
    asset = _asset("X-99", "mystery_type")
    r = score_asset(asset, {}, WEIGHTS, BENCHMARKS, SCORING_OPTIONS)
    assert r is None