"""Test the ProposalValidator with real Bukit Jelutong data.

Run from repo root:
    python backend/scripts/diagnose_validator.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.tool_service import TownshipDataSource
from app.llm.validator import ProposalValidator


def main():
    repo_root = Path(__file__).resolve().parents[2]
    ds = TownshipDataSource(repo_root, year=2026)
    validator = ProposalValidator(ds, base_year=2026)

    # Pick a deadspace candidate as target
    candidates = [
        aid for aid, r in ds.deadspace.items()
        if r.get("status") == "deadspace_candidate"
    ]
    if not candidates:
        print("No deadspace_candidate found; cannot test validator")
        return

    target = candidates[0]
    print(f"Target asset: {target}")
    row = ds._asset_row(target)
    print(f"  asset_type: {row['asset_type']}")
    print(f"  subtype:    {row['subtype']}")
    print()

    # ---- Test 1: valid plan (repurpose commercial -> clinic)
    print("=" * 72)
    print("Test 1: valid repurpose plan")
    print("=" * 72)
    plan = [{
        "asset_id": target,
        "type": "repurpose",
        "parameters": {"to_subtype": "clinic", "new_capacity": 200},
        "expected_effects": {"utilisation": 0.72},
    }]
    result = validator.validate(plan)
    print(f"  valid: {result.valid}")
    for e in result.errors:
        print(f"  ERROR: {e}")
    for w in result.warnings:
        print(f"  WARN:  {w}")
    if result.normalised_plan:
        np = result.normalised_plan[0]
        print(f"  normalised: capex={np['capex_delta_rm']:,.0f}, "
              f"opex={np['opex_delta_rm']:,.0f}, "
              f"start={np['construction_start_year']}, "
              f"activation={np['activation_year']}")

    # ---- Test 2: invalid subtype
    print()
    print("=" * 72)
    print("Test 2: invalid subtype")
    print("=" * 72)
    plan = [{
        "asset_id": target,
        "type": "repurpose",
        "parameters": {"to_subtype": "spaceship_hangar"},
    }]
    result = validator.validate(plan)
    print(f"  valid: {result.valid} (should be False)")
    for e in result.errors:
        print(f"  ERROR: {e}")

    # ---- Test 3: nonexistent asset
    print()
    print("=" * 72)
    print("Test 3: nonexistent asset")
    print("=" * 72)
    plan = [{
        "asset_id": "NOT-A-REAL-ID",
        "type": "repurpose",
        "parameters": {"to_subtype": "clinic"},
    }]
    result = validator.validate(plan)
    print(f"  valid: {result.valid} (should be False)")
    for e in result.errors:
        print(f"  ERROR: {e}")

    # ---- Test 4: capex_limit
    print()
    print("=" * 72)
    print("Test 4: capex_limit exceeded")
    print("=" * 72)
    plan = [{
        "asset_id": target,
        "type": "repurpose",
        "parameters": {"to_subtype": "clinic"},
    }]
    result = validator.validate(plan, constraints={"capex_limit": 100_000})
    print(f"  valid: {result.valid} (likely False)")
    for e in result.errors:
        print(f"  ERROR: {e}")


if __name__ == "__main__":
    main()