"""Run Phase 2 — B5 Scoring."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.scoring.engine import score_all_assets, write_scores_json


def _fmt(v, decimals=2):
    if v is None:
        return "-"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return f"{round(f, decimals)}"


def _bar(score, width=30):
    """ASCII bar for visual comparison."""
    if score is None:
        return " " * width
    filled = int(round(score / 100 * width))
    return "#" * filled + "." * (width - filled)


def _section(title, width=72):
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)


def main():
    repo_root = Path(__file__).resolve().parents[2]
    year = 2026

    print(f"\nRunning Phase 2 (B5) for year {year}...")
    metrics_df, score_records = score_all_assets(repo_root=repo_root, year=year)

    # --- Summary table ---
    _section(f"ASSET SCORES — {year}")
    header = f"  {'Asset':<8} {'Type':<22} {'Overall':>8}  {'Fin':>6} {'Env':>6} {'Soc':>6}  {'Conf':<7}"
    print(header)
    print("  " + "-" * len(header))

    for r in score_records:
        print(
            f"  {r['asset_id']:<8} {r['asset_type']:<22} "
            f"{_fmt(r['overall_score']):>8}  "
            f"{_fmt(r['financial_score']):>6} "
            f"{_fmt(r['environmental_score']):>6} "
            f"{_fmt(r['social_score']):>6}  "
            f"{r['confidence']:<7}"
        )

    # --- Component breakdown ---
    _section("COMPONENT BREAKDOWN")

    for r in score_records:
        print(f"\n  {r['asset_id']}  ({r['asset_type']})")
        print(f"    Overall: {_fmt(r['overall_score'])}   "
              f"Completeness: {_fmt(r['data_completeness'], 2)}   "
              f"Confidence: {r['confidence']}")
        print(f"    {_bar(r['overall_score'])}")
        print("    Components:")
        for k, v in r["component_scores"].items():
            w = r["weights_used"].get(k, 0)
            print(f"      {k:<24} {_fmt(v):>7}   weight {w:.2f}")

    # --- Write back ---
    metrics_out = repo_root / "mock" / "business" / "asset_metrics_enriched.csv"
    metrics_df.to_csv(metrics_out, index=False)

    scores_json = write_scores_json(score_records, repo_root=repo_root, year=year)

    print("\n" + "=" * 72)
    print(f"  Wrote updated metrics: {metrics_out}")
    print(f"  Wrote scores JSON:     {scores_json}")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    main()