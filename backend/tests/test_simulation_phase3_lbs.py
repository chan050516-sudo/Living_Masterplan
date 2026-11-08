"""v6.0 Phase 3 — LBS-aware simulation pieces (no full simulation run)."""

import pandas as pd

from app.deadspace import external
from app.simulation import engine
from app.llm.orchestrator import _verify_catalytic_links


def test_huff_vitality_flag_off_is_legacy():
    assert external.huff_vitality("X", "cafe", 0.05, use_lbs=False) == 0.1
    assert external.huff_vitality("X", "cafe", 0.7, use_lbs=False) == 0.7


def test_huff_vitality_blends_footfall(monkeypatch):
    monkeypatch.setattr(external, "lbs_users_percentile", lambda aid, st: 1.0)
    assert round(external.huff_vitality("X", "cafe", 0.2, use_lbs=True), 2) == 0.68
    monkeypatch.setattr(external, "lbs_users_percentile", lambda aid, st: None)
    assert external.huff_vitality("X", "cafe", 0.2, use_lbs=True) == 0.2


def test_comparison_metrics_depend_on_authority():
    owned = {k for k, _ in engine._comparison_metrics_for("full_control")}
    sold = {k for k, _ in engine._comparison_metrics_for("advisory")}
    assert "maintenance_surge_rm" in owned and "maintenance_surge_rm" not in sold
    assert "lbs_unique_users_daily" in sold and "lbs_unique_users_daily" not in owned
    assert "flow_island_ratio" in owned and "flow_island_ratio" in sold


def test_proxy_seed_order(monkeypatch):
    monkeypatch.setattr(engine, "external_for", lambda aid, st: {
        "proxied_occupancy_google": 0.6, "proxied_occupancy_lbs": 0.42})
    assert engine._proxy_occupancy_seed("A", "cafe") == (0.42, "kido_dynamics_mock")
    monkeypatch.setattr(engine, "external_for", lambda aid, st: {
        "proxied_occupancy_google": 0.6})
    assert engine._proxy_occupancy_seed("A", "cafe") == (0.6, "google_places_mock")
    monkeypatch.setattr(engine, "external_for", lambda aid, st: {})
    assert engine._proxy_occupancy_seed("A", "cafe") == (0.5, "neutral_default")


def _sold_state(monkeypatch, cov_after):
    monkeypatch.setattr(engine, "external_for", lambda aid, st: {
        "lbs_unique_users_daily": 100.0, "flow_island_ratio": 0.5})
    assets = pd.DataFrame([{"asset_id": "A", "asset_type": "commercial",
                            "subtype": "cafe", "authority": "advisory"}])
    states = {2026: {"A": {"coverage_ratio_10min_walk": 0.4}},
              2033: {"A": {"coverage_ratio_10min_walk": cov_after}}}
    engine._attach_proxy_state(states, 2026, assets, {"A": "google_places_mock"}, 0.25)
    return states


def test_footfall_follows_walking_access(monkeypatch):
    states = _sold_state(monkeypatch, 0.44)  # +10% access
    assert states[2026]["A"]["lbs_unique_users_daily"] == 100.0
    assert round(states[2033]["A"]["lbs_unique_users_daily"], 2) == 102.5
    assert states[2033]["A"]["_authority"] == "advisory"
    assert states[2033]["A"]["_occupancy_seed_source"] == "google_places_mock"


def _candidate(per_asset):
    return [{
        "simulation": {}, "simulation_brief": {"per_asset_metrics": per_asset},
        "plan": [{"role": "catalytic", "catalytic_link": {
            "beneficiary_asset_id": "A", "mechanism": "walkability_improvement",
            "verification_level": "verified"}}],
    }]


def test_catalytic_needs_footfall_when_lbs_present():
    cov = {"coverage_ratio_10min_walk": {"before": 0.4, "after": 0.5}}
    flat = _candidate({"A": {**cov, "lbs_unique_users_daily": {"before": 10, "after": 10}}})
    _verify_catalytic_links(flat)
    assert flat[0]["plan"][0]["catalytic_link"]["verification_level"] == "partially_verified"

    up = _candidate({"A": {**cov, "lbs_unique_users_daily": {"before": 10, "after": 12}}})
    _verify_catalytic_links(up)
    assert up[0]["plan"][0]["catalytic_link"]["verification_level"] == "verified"

    no_lbs = _candidate({"A": cov})
    _verify_catalytic_links(no_lbs)
    assert no_lbs[0]["plan"][0]["catalytic_link"]["verification_level"] == "verified"
