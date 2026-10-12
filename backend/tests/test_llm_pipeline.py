import pytest
from app.llm.pipeline import run_query


@pytest.fixture(autouse=True)
def mock_mode(monkeypatch):
    monkeypatch.setenv("USE_MOCK", "true")
    monkeypatch.setenv("USE_MOCK_SIM", "true")


def test_demo_path():
    r = run_query("Should we proceed with Phase 3?", "B-03")
    opts = r["options"]["B-03"]["options"]
    assert [o["id"] for o in opts] == ["A", "B", "C"]
    assert r["comparison"]["B-03"]["rows"][0]["label"] == "CAPEX"
    assert r["comparison"]["B-03"]["recommended"].startswith("Option")


def test_unknown_asset():
    r = run_query("demolish B-99", None)
    assert r["needs_clarification"]