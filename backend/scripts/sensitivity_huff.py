"""Sensitivity analysis for Huff gravity model.

Runs B3 + B5 for beta ∈ {1.5, 2.0, 2.5} and reports how DSR and
performance score respond. Used for pitch credibility.
"""

import copy
import sys
from pathlib import Path
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import load_paths, load_benchmarks, load_weights, load_assumptions
from app.derived.engine import compute_derived_metrics
from app.scoring.score import score_asset


def _section(t, w=72):
    print("\n" + "=" * w)
    print(f"  {t}")
    print("=" * w)


def main():
    repo_root = Path(__file__).resolve().parents[2]

    base_assumptions = load_assumptions()
    weights_cfg = load_weights()
    benchmarks = load_benchmarks()
    weights = {k: v for k, v in weights_cfg.items() if isinstance(v, dict)}
    scoring_options = weights_cfg.get("scoring_options", {})

    betas = [1.5, 2.0, 2.5]

    _section("Huff beta sensitivity — B-03")
    print("  Purpose: verify that DSR and score do not collapse")
    print("           under reasonable variation of the distance-decay exponent.")
    print()

    results = []
    for beta in betas:
        assumptions = copy.deepcopy(base_assumptions)
        assumptions["huff"]["beta"] = beta

        # Patch: engine reads assumptions from config, so we monkey-patch
        import app.derived.engine as eng
        original_loader = eng.load_assumptions
        eng.load_assumptions = lambda a=assumptions: a

        try:
            derived = compute_derived_metrics(repo_root=repo_root, year=2026)
        finally:
            eng.load_assumptions = original_loader

        b03 = derived[derived["asset_id"] == "B-03"]
        if b03.empty:
            continue
        row = b03.iloc[0]

        assets = pd.read_csv(repo_root / "mock" / "business" / "assets.csv")
        asset = assets[assets["asset_id"] == "B-03"].iloc[0]
        score = score_asset(asset, row, weights, benchmarks, scoring_options)

        results.append({
            "beta": beta,
            "dsr": row.get("dsr"),
            "effective_demand": row.get("effective_demand"),
            "effective_demand_m2": row.get("effective_demand_m2"),
            "overall_score": score["overall_score"] if score else None,
        })

    print(f"  {'beta':<6} {'eff_demand':>12} {'eff_demand_m2':>14} "
          f"{'DSR':>8} {'Score':>8}")
    print("  " + "-" * 60)
    for r in results:
        print(f"  {r['beta']:<6} "
              f"{_fmt(r['effective_demand']):>12} "
              f"{_fmt(r['effective_demand_m2']):>14} "
              f"{_fmt(r['dsr']):>8} "
              f"{_fmt(r['overall_score'], 1):>8}")

    if len(results) >= 2:
        d0, dN = results[0], results[-1]
        if d0["effective_demand"] and dN["effective_demand"]:
            change = ((dN["effective_demand"] - d0["effective_demand"])
                      / d0["effective_demand"] * 100)
            print(f"\n  Effective demand change from beta={d0['beta']} "
                  f"to beta={dN['beta']}: {change:+.1f}%")


def _fmt(v, decimals=1):
    if v is None:
        return "-"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(f) >= 1000:
        return f"{f:,.0f}"
    return f"{round(f, decimals)}"


if __name__ == "__main__":
    main()