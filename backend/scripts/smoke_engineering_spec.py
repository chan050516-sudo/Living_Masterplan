"""Smoke test for the P1 engineering_spec path.

Writes a throwaway scenario to interventions.csv, runs B4, and
verifies the spec was consumed by the LST-coupled cooling model.

Run from the repository root:
    python backend/scripts/smoke_engineering_spec.py

Or from backend/:
    python -m scripts.smoke_engineering_spec
"""

import sys
from pathlib import Path

# Make `app` importable regardless of the caller's cwd.
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.llm.tool_service import TownshipDataSource
from app.llm.orchestrator import _write_interventions
from app.simulation.engine import simulate_scenario
from app.llm.validator import ProposalValidator


def main() -> int:
    ds = TownshipDataSource(REPO_ROOT, year=2026)
    ProposalValidator(ds, base_year=2026)  # availability check only

    commercial = ds.assets[ds.assets["asset_type"] == "commercial"]
    if commercial.empty:
        print("FAIL: no commercial asset found")
        return 1
    aid = commercial.iloc[0]["asset_id"]
    print(f"Testing engineering_spec on {aid}")

    plan = [{
        "asset_id": aid,
        "intervention_type": "retrofit",
        "role": "primary",
        "catalytic_link": None,
        "parameters": {
            "engineering_spec": {
                "structure_retention_ratio": 0.9,
                "facade_action": "insulated_overclad",
                "primary_material": "ggbs_concrete",
                "roof_intervention": "green_roof",
                "hvac_cop": 4.2,
                "operating_hours_per_week": 70,
                "rooftop_pv_coverage": 0.6,
            },
            "measures": ["hvac_upgrade", "led_lighting"],
        },
        "expected_derived_json": None,
        "construction_start_year": 2027,
        "construction_duration_months": 12,
        "activation_year": 2028,
        "during_construction_status": "partial",
        "capacity_ratio": 0.6,
        "capex_delta_rm": 500000,
        "opex_delta_rm": 0,
    }]

    _write_interventions(ds, "SC-SPEC-SMOKE", plan)
    print("Wrote SC-SPEC-SMOKE to interventions.csv")

    result = simulate_scenario("SC-SPEC-SMOKE", _shared_cache={})
    if result.get("error"):
        print(f"FAIL: simulation error: {result['error']}")
        return 1

    final = result["years"]["2033"]["assets"].get(aid, {})
    pv = final.get("energy_kwh_pv_offset")
    carbon = final.get("carbon_operational_tco2e")

    print(f"  energy_kwh_pv_offset: {pv}")
    print(f"  carbon_operational:   {carbon}")

    # Basic assertions
    ok = True
    if pv is None:
        print("FAIL: energy_kwh_pv_offset is None (spec not consumed)")
        ok = False
    elif pv <= 0:
        print(
            f"FAIL: energy_kwh_pv_offset = {pv} — expected > 0 "
            f"with rooftop_pv_coverage=0.6"
        )
        ok = False
    if carbon is None:
        print("FAIL: carbon_operational_tco2e is None")
        ok = False

    if ok:
        print("PASS — engineering_spec was consumed by the B4 engine")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())