"""v6.0 Phase 5 — LLM gets labelled LBS / Google evidence and flow-island rules."""

from pathlib import Path

from app.deadspace.evidence import build_evidence
from app.deadspace.layer3_lbs import evaluate as proxy_eval
from app.llm import context_builder
from app.llm.orchestrator import _decision_targets

PROMPTS = Path(__file__).resolve().parents[1] / "app" / "llm" / "prompts"

_EXT = {
    "lbs_unique_users_daily": 12.0, "lbs_peer_users_median": 63.0,
    "lbs_dwell_time_minutes": 12.0, "lbs_peer_dwell_median": 13.0,
    "flow_island_ratio": 0.38, "unit_mix_unit_count": 5,
    "operational_place_count": 0, "business_presence_ratio": 0.0,
    "business_turnover_count": 2, "business_vitality_score": 0.03,
}


def test_external_signals_for_sold_shop(monkeypatch):
    monkeypatch.setattr(context_builder, "external_for", lambda aid, st: dict(_EXT))
    sig = context_builder._build_external_signals("A", "commercial", "advisory", "cafe")
    assert sig["tier"] == "3a"
    lbs = sig["lbs_foot_traffic"]
    assert lbs["daily_visitors"] == 12 and lbs["subtype_peer_median_visitors"] == 63
    assert lbs["is_flow_island"] is True  # 0.38 < 0.60
    assert "mock" in lbs["source"]
    g = sig["google_places_presence"]
    assert (g["operating_units"], g["total_units"], g["turnover_count"]) == (0, 5, 2)


def test_no_external_signals_for_owned_or_non_commercial(monkeypatch):
    monkeypatch.setattr(context_builder, "external_for", lambda aid, st: dict(_EXT))
    assert context_builder._build_external_signals("A", "commercial", "full_control", "cafe") is None
    assert context_builder._build_external_signals("A", "residential", "advisory", "terrace") is None
    monkeypatch.setattr(context_builder, "external_for", lambda aid, st: {})
    assert context_builder._build_external_signals("A", "commercial", "advisory", "cafe") is None


def test_final_writer_sees_targets():
    pack = {"targets": [
        {"asset_id": "A", "authority": {"level": "advisory", "ownership_status": "sold"},
         "deadspace": {"status": "community_value_gap", "flags": ["flow_island"]},
         "external_signals": {"tier": "3a"}},
        {"asset_id": "B", "authority": {"level": "full_control"},
         "deadspace": {"status": "deadspace_candidate", "flags": []},
         "external_signals": None},
        None,
    ]}
    rows = _decision_targets(pack)
    assert [r["asset_id"] for r in rows] == ["A", "B"]
    assert rows[0]["external_signals"] == {"tier": "3a"}
    assert "external_signals" not in rows[1]
    assert _decision_targets(None) == []


def test_evidence_quotes_configured_flow_island_limit():
    proxy = proxy_eval(dict(_EXT), {"flow_island_ratio_below": 0.6})
    assert "flow_island" in proxy["reasons"]
    lines = build_evidence("commercial", "cafe", {}, proxy=proxy, external=dict(_EXT))
    island = [l for l in lines if "flow-island" in l]
    assert island and "below 0.6 = isolated" in island[0]


def test_prompts_carry_phase5_rules():
    writer = (PROMPTS / "final_decision_writer.md").read_text(encoding="utf-8")
    gen = (PROMPTS / "candidate_generator.md").read_text(encoding="utf-8")
    assert "External Data Signals" in writer and "Do NOT average" in writer
    assert "never as \"occupancy is X%\"" in writer
    assert "Flow-Island Assets" in gen and "pedestrian_upgrade" in gen
