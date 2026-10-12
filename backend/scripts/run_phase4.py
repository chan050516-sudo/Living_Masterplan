"""Run Phase 4 — B4 Simulation for all scenarios.

Phase 5 change: prints township-level metrics alongside the per-asset
comparison block.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.simulation.engine import simulate_scenario, write_scenario_result


def _fmt(v, decimals=3):
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

    _section("METRIC COMPARISON")
    for sid in SCENARIOS:
        r = results.get(sid)
        if not r:
            continue
        c = r["comparison"]
        print(f"\n  {r['scenario_name']} ({sid})")
        print(f"    Focus asset: {c.get('focus_asset_id')}")
        metrics = c.get("metrics", {})
        if not metrics:
            print("    (no comparable metrics)")
            continue
        print(f"    {'Metric':<32} {'Before':>12} {'After':>12}  Unit")
        print("    " + "-" * 68)
        for key, val in metrics.items():
            print(
                f"    {key:<32} "
                f"{_fmt(val.get('before')):>12} "
                f"{_fmt(val.get('after')):>12}  "
                f"{val.get('unit', '')}"
            )

    _section("TOWNSHIP-LEVEL METRICS")
    for sid in SCENARIOS:
        r = results.get(sid)
        if not r:
            continue
        tm = r["comparison"].get("township_metrics", {})
        print(f"\n  {r['scenario_name']} ({sid})")
        print(f"    Walk 15-min avg coverage (before): "
              f"{_fmt(tm.get('walk_15min_avg_coverage_before'))}")
        print(f"    Walk 15-min avg coverage (after):  "
              f"{_fmt(tm.get('walk_15min_avg_coverage_after'))}")
        print(f"    Walk 15-min coverage delta:        "
              f"{_fmt(tm.get('walk_15min_coverage_delta'))}")
        print(f"    Total carbon before (tCO2e):       "
              f"{_fmt(tm.get('total_carbon_before_tco2e'), 1)}")
        print(f"    Total carbon after (tCO2e):        "
              f"{_fmt(tm.get('total_carbon_after_tco2e'), 1)}")
        print(f"    Carbon delta (%):                  "
              f"{_fmt(tm.get('carbon_delta_pct'), 4)}")

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