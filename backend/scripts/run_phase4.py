"""Run Phase 4 — B4 Simulation for all scenarios."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.simulation.engine import simulate_scenario, write_scenario_result


def _fmt(v, decimals=2):
    if v is None:
        return "-"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(f) >= 1000:
        return f"{f:,.0f}"
    return f"{round(f, decimals)}"


def _section(title, width=72):
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)


SCENARIOS = ["SC-CURRENT", "SC-REPURPOSE", "SC-DELAY"]


def main():
    repo_root = Path(__file__).resolve().parents[2]

    print("\nRunning Phase 4 (B4) — Simulation")
    results = {}

    for scenario_id in SCENARIOS:
        print(f"\n  Simulating {scenario_id} ...")
        try:
            result = simulate_scenario(scenario_id, repo_root=repo_root)
            results[scenario_id] = result
            out = write_scenario_result(result, repo_root=repo_root)
            print(f"    → wrote {out.name}")
        except Exception as e:
            print(f"    ERROR: {e}")

    # ---- Per-scenario score timeline ----
    _section("SCORE TIMELINE — B-03 (primary demo asset)")
    print(f"  {'Year':<6} ", end="")
    for sid in SCENARIOS:
        print(f"{sid:<14} ", end="")
    print()
    print("  " + "-" * 60)
    all_years = [2026, 2027, 2028, 2030, 2033]
    for y in all_years:
        print(f"  {y:<6} ", end="")
        for sid in SCENARIOS:
            r = results.get(sid, {})
            score = r.get("years", {}).get(str(y), {}).get("scores", {}).get("B-03", {})
            overall = score.get("overall_score")
            print(f"{_fmt(overall, 1):<14} ", end="")
        print()

    # ---- Comparison table ----
    _section("COMPARISON — final year vs current")
    for sid in SCENARIOS:
        r = results.get(sid)
        if not r:
            continue
        c = r["comparison"]
        print(f"\n  {r['scenario_name']} ({sid})")
        print(f"    CAPEX:                   RM {_fmt(c['capex'], 0)}")
        print(f"    Projected utilisation:   {_fmt(c['projected_utilisation'], 3)}")
        print(f"    Performance score:       {_fmt(c['performance_score'], 1)}")
        print(f"    Δ Score:                 {_fmt(c['delta_score'], 1)}")
        print(f"    Environmental:           {_fmt(c['environmental_score'], 1)}")
        print(f"    Social:                  {_fmt(c['social_score'], 1)}")
        print(f"    Time to impact:          {_fmt(c['time_to_impact_months'], 0)} months")

    # ---- Map diff ----
    _section("MAP DIFF")
    for sid in SCENARIOS:
        r = results.get(sid)
        if not r:
            continue
        md = r["map_diff"]
        print(f"\n  {sid}:")
        if md["changed_assets"]:
            for a in md["changed_assets"]:
                print(f"    [blue]   {a['asset_id']} — {a['change_type']}")
        if md["spillover_assets"]:
            for a in md["spillover_assets"]:
                print(f"    [purple] {a['asset_id']} — {a['change_type']}")
        if md["negative_assets"]:
            for a in md["negative_assets"]:
                print(f"    [black]  {a['asset_id']} — {a['change_type']}")
        if not (md["changed_assets"] or md["spillover_assets"] or md["negative_assets"]):
            print("    (no changes)")

    print("\n" + "=" * 72)
    print(f"  Scenario results in: {repo_root / 'mock' / 'business' / 'scenarios'}/")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    main()