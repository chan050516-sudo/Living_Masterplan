import pytest
from app.llm.intent import parse_intent
from app.llm.schemas import InterventionType as T


@pytest.fixture(autouse=True)
def mock_mode(monkeypatch):
    monkeypatch.setenv("USE_MOCK", "true")


def test_repurpose_and_pedestrian():
    i = parse_intent("Repurpose B-03 into a community hub and improve pedestrian access", "B-03")
    assert i.target_asset_id == "B-03"
    assert set(i.proposed_interventions) == {T.REPURPOSE, T.PEDESTRIAN_UPGRADE}


def test_phase3_question():
    i = parse_intent("Should we proceed with Phase 3?", "B-03")
    assert i.objective == "avoid_capex"


def test_unknown_asset_needs_clarification():
    i = parse_intent("demolish B-99", None)
    assert i.needs_clarification