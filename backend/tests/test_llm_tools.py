import json
from app.llm.schemas import Option, Intervention, InterventionType
from app.llm.tools import simulate_option, get_asset_state
from app.llm.validator import validate_option


def _repurpose_option():
    return Option(option_id="A", title="Repurpose B-03", interventions=[
        Intervention(
            intervention_id="INT-LLM-A1", target_asset_id="B-03",
            intervention_type=InterventionType.REPURPOSE,
            parameters={"from": "commercial", "to": "community_facility", "new_capacity": 200},
            construction_start_year=2027, construction_duration_months=18,
            activation_year=2028, during_construction_status="unavailable",
            capex_delta_rm=1200000, opex_delta_rm=60000)])


def test_asset_state():
    assert get_asset_state("B-03")["asset_type"] == "commercial"


def test_validator_accepts_good_option():
    assert validate_option(_repurpose_option()) == []


def test_validator_rejects_unknown_asset():
    opt = _repurpose_option()
    opt.interventions[0].target_asset_id = "B-99"
    assert validate_option(opt) != []


def test_simulate_option_runs():
    result = simulate_option(_repurpose_option())
    print("KEYS:", list(result.keys()))
    print(json.dumps(result, indent=2, default=str)[:3500])
    assert isinstance(result, dict)