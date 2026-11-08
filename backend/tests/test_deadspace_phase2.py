"""v6.0 Phase 2 — tier flags, proxy layer, survival floor, sold-asset status."""

import pandas as pd

from app.deadspace import detector
from app.deadspace.layer3_lbs import evaluate as proxy_eval
from app.deadspace.layer3_survival import evaluate_survival_floor
from app.deadspace.status import decide_sold_commercial_status
from app.deadspace.tiers import evaluation_mode, tier_of


def test_proxy_flags_fire_on_their_thresholds():
    ext = {
        "proxied_occupancy_google": 0.2,
        "business_presence_ratio": 0.2,
        "business_vitality_score": 0.1,
        "business_turnover_count": 2,
        "proxied_vacancy_duration": 13,
        "lbs_unique_users_daily": 3, "lbs_peer_users_median": 20,
        "lbs_dwell_time_minutes": 10, "lbs_peer_dwell_median": 45,
        "flow_island_ratio": 0.2,
        "observed_demand_ratio": 0.05,
    }
    reasons = proxy_eval(ext)["reasons"]
    for flag in (
        "low_occupancy_proxied", "business_presence_low", "business_vitality_low",
        "business_turnover_high", "long_vacancy_proxied", "low_footfall_lbs",
        "short_dwell_lbs", "flow_island",
    ):
        assert flag in reasons
    assert "data_conflict" not in reasons


def test_data_conflict_when_sources_disagree():
    ext = {"business_presence_ratio": 0.9, "observed_demand_ratio": 0.05}
    assert "data_conflict" in proxy_eval(ext)["reasons"]


def test_occupancy_proxy_prefers_lbs():
    # D-21: LBS footfall is the primary occupancy proxy, Google the fallback.
    out = proxy_eval({"proxied_occupancy_google": 0.8, "proxied_occupancy_lbs": 0.2})
    assert out["proxied_occupancy_source"] == "kido_dynamics_mock"
    assert "low_occupancy_proxied" in out["reasons"]
    out = proxy_eval({"proxied_occupancy_google": 0.8})
    assert out["proxied_occupancy_source"] == "google_places_mock"
    assert "low_occupancy_proxied" not in out["reasons"]


def test_survival_floor():
    asset = {"subtype": "cafe", "lettable_area_m2": 200}
    cfg = {"survival_analysis": {
        "conversion_rate_by_subtype": {"cafe": 0.04},
        "avg_spend_rm_by_subtype": {"cafe": 22},
        "operating_days_by_subtype": {"cafe": 340},
        "survival_opex_per_m2_by_subtype": {"cafe": 220},
        "inflation_index": {2026: 1.0, 2028: 1.06},
    }}
    low = evaluate_survival_floor(asset, {"lbs_unique_users_daily": 100}, cfg)
    assert low["triggered"]  # revenue RM 29,920 < floor RM 44,000
    high = evaluate_survival_floor(asset, {"lbs_unique_users_daily": 1000}, cfg)
    assert not high["triggered"]
    assert evaluate_survival_floor(asset, {}, cfg)["reason"] == "no_lbs_footfall"


def test_sold_status_rules():
    assert decide_sold_commercial_status([]) == "healthy"
    assert decide_sold_commercial_status(["low_footfall_lbs", "data_conflict"]) == "monitor"
    assert decide_sold_commercial_status(["low_footfall_lbs", "flow_island"]) == "community_value_gap"
    assert decide_sold_commercial_status(
        ["low_occupancy_proxied", "walking_accessibility_deficit"]) == "community_value_gap"
    assert decide_sold_commercial_status(["low_occupancy_proxied", "dsr_below_threshold"]) == "strategic_learning"
    assert decide_sold_commercial_status(["dsr_below_threshold"]) == "monitor"


def test_tiers_and_mode():
    assert tier_of("low_occupancy") == "tier_1_observed"
    assert tier_of("low_footfall_lbs") == "tier_3a_proxied"
    assert evaluation_mode("full_control") == "operating_performance"
    assert evaluation_mode(None) == "operating_performance"
    assert evaluation_mode("advisory") == "developer_realization"


def _failing_commercial(authority):
    asset = pd.Series({
        "asset_id": "B-03", "asset_type": "commercial",
        "subtype": "convenience_retail", "maintenance_annual_rm": 180000,
        "lettable_area_m2": 300, "authority": authority,
    })
    metrics = pd.Series({
        "year": 2026, "subtype": "convenience_retail",
        "occupancy_rate": 0.21, "vacancy_duration_months": 14,
        "dsr": 0.35, "noi_rm": -50962, "coverage_ratio_5min_walk": 0.15,
    })
    return asset, metrics


def test_sold_asset_is_never_deadspace(monkeypatch):
    monkeypatch.setattr(detector, "external_for", lambda aid, st: {
        "proxied_occupancy_google": 0.2, "business_presence_ratio": 0.2,
        "observed_demand_ratio": 0.2, "lbs_unique_users_daily": 500,
    })
    asset, metrics = _failing_commercial("advisory")
    out = detector.detect_deadspace_for_asset(asset, metrics, {"deadspace": {}})
    assert out["status"] == "community_value_gap"
    assert "low_occupancy" in out["suppressed_flags"]
    assert "low_occupancy" not in out["flags"]
    assert out["flag_tiers"]["low_occupancy_proxied"] == "tier_3a_proxied"
    assert out["evaluation_mode"] == "developer_realization"
    assert not any(line.startswith("Occupancy:") for line in out["evidence"])


def test_owned_asset_keeps_observed_flags():
    asset, metrics = _failing_commercial("full_control")
    out = detector.detect_deadspace_for_asset(asset, metrics, {"deadspace": {}})
    assert out["status"] == "deadspace_candidate"
    assert out["layer3a"] is None
    assert "low_occupancy" in out["flags"]
