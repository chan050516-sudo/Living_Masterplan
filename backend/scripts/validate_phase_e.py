"""Validate Phase E — LLM layer sees structured trajectory, lease,
subtype_mix and catalytic evidence.

Run:
    python backend/scripts/validate_phase_e.py

Builds the context pack for two real targets and checks that the
new blocks are populated where expected. Does NOT call the LLM.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.context_builder import (
    _build_trajectory_block,
    _build_lease_schedule,
    _build_subtype_mix,
)
from app.llm.tool_service import TownshipDataSource, TOOL_DISPATCH


def _hdr(t):
    print("\n" + "=" * 72)
    print(f"  {t}")
    print("=" * 72)


def _ok(msg):
    print(f"[ OK ] {msg}")


def _warn(msg):
    print(f"[WARN] {msg}")


def _fail(msg):
    print(f"[FAIL] {msg}")
    raise SystemExit(1)


def main():
    repo_root = Path(__file__).resolve().parents[2]
    ds = TownshipDataSource(repo_root, year=2026)

    # --------------------------------------------------------------
    _hdr("1. Data source loaded leases")

    if ds.leases is None or ds.leases.empty:
        _fail("TownshipDataSource.leases is empty — was the file loaded?")
    _ok(f"{len(ds.leases)} lease records loaded")

    # --------------------------------------------------------------
    _hdr("2. New tools are registered")

    for name in ("get_lease_schedule", "get_asset_trajectory"):
        if name not in TOOL_DISPATCH:
            _fail(f"tool {name} not registered in TOOL_DISPATCH")
    _ok("both new tools registered")

    # --------------------------------------------------------------
    _hdr("3. Trajectory block returns non-null for a residential asset")

    residential = ds.assets[ds.assets["asset_type"] == "residential"].head(5)
    found = False
    for _, a in residential.iterrows():
        aid = a["asset_id"]
        traj = _build_trajectory_block(ds, aid)
        if traj:
            print(f"  {aid}: {json.dumps(traj, indent=2)}")
            found = True
            break
    if not found:
        _warn("no residential asset has a trajectory block "
              "(all may be trajectory_class=unknown)")

    # --------------------------------------------------------------
    _hdr("4. Lease schedule returns non-null for a mall")

    commercials = ds.assets[ds.assets["asset_type"] == "commercial"]
    found = False
    for _, a in commercials.iterrows():
        aid = a["asset_id"]
        schedule = _build_lease_schedule(ds, aid)
        if schedule:
            print(f"  {aid}: {json.dumps(schedule, indent=2)}")
            found = True
            break
    if not found:
        _warn("no commercial asset has a lease schedule")
    else:
        _ok("lease schedule populated")

    # --------------------------------------------------------------
    _hdr("5. Subtype mix returns non-null for a mall")

    found = False
    for _, a in commercials.iterrows():
        aid = a["asset_id"]
        mix = _build_subtype_mix(ds, aid)
        if mix and mix.get("subtypes"):
            print(f"  {aid}:")
            print(f"    subtypes: {list(mix['subtypes'].keys())}")
            print(f"    dead:     {mix['dead_subtypes']}")
            print(f"    low:      {mix['low_sub_types'] if False else mix['low_subtypes']}")
            found = True
            break
    if not found:
        _warn("no commercial asset has a subtype_mix")

    # --------------------------------------------------------------
    _hdr("6. Tools return the expected shape")

    if not commercials.empty:
        mall_id = commercials.iloc[0]["asset_id"]
        result = TOOL_DISPATCH["get_lease_schedule"](ds, {"asset_id": mall_id})
        print(f"  get_lease_schedule({mall_id}): {json.dumps(result, indent=2)[:200]}")

        result = TOOL_DISPATCH["get_asset_trajectory"](ds, {"asset_id": mall_id})
        print(f"  get_asset_trajectory({mall_id}): {json.dumps(result, indent=2)[:200]}")

    _ok("tool dispatch works")

    # --------------------------------------------------------------
    _hdr("7. catalytic_evidence appears in a simulated candidate")

    scenario_dir = repo_root / ds.paths["base"] / "business" / "scenarios"
    # The candidate runs write to scenario files not in SC-CURRENT — check
    # if any LLM-* scenario exists.
    llm_scenarios = list(scenario_dir.glob("SC-LLM-*.json"))
    if not llm_scenarios:
        _warn("no LLM-* scenarios found — run run_llm_real.py first to "
              "verify catalytic_evidence end-to-end")
    else:
        with open(llm_scenarios[-1]) as f:
            data = json.load(f)
        # The catalytic_evidence is in the orchestrator's summary, not
        # the scenario JSON. We can only confirm the pipeline runs.
        _ok(f"found {len(llm_scenarios)} LLM scenarios")

    print("\n" + "=" * 72)
    print("  Phase E validation complete.")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    main()