"""B5 unified entry point."""

import json
import logging
from pathlib import Path

import pandas as pd

from ..config import load_paths, load_weights, load_benchmarks
from .score import score_asset

log = logging.getLogger(__name__)


def score_all_assets(repo_root: Path = None, year: int = 2026) -> tuple[pd.DataFrame, list]:
    """
    Read B3 output (asset_metrics_enriched.csv), score each asset, return:
      - updated metrics DataFrame (with financial_score etc. filled)
      - list of asset_score dicts (for scores.json)
    """
    repo_root = repo_root or Path(__file__).resolve().parents[3]
    paths = load_paths()
    weights_cfg = load_weights()
    benchmarks = load_benchmarks()

    base = repo_root / paths["base"]
    metrics_path = base / "business" / "asset_metrics_enriched.csv"
    if not metrics_path.exists():
        # Fall back to raw asset_metrics if enriched not present
        metrics_path = base / "business" / "asset_metrics.csv"

    metrics_df = pd.read_csv(metrics_path)
    assets_df = pd.read_csv(base / "business" / "assets.csv")

    weights = {k: v for k, v in weights_cfg.items() if isinstance(v, dict)}
    scoring_options = weights_cfg.get("scoring_options", {})

    score_records = []

    for _, asset in assets_df.iterrows():
        aid = asset["asset_id"]
        row = metrics_df[(metrics_df["asset_id"] == aid) & (metrics_df["year"] == year)]
        if row.empty:
            log.warning("No metrics for %s year %d — skipping", aid, year)
            continue
        metrics_row = row.iloc[0]

        result = score_asset(asset, metrics_row, weights, benchmarks, scoring_options)
        if result is None:
            log.warning("Scoring returned None for %s", aid)
            continue

        result["year"] = year
        result["model_version"] = "0.3.0"
        score_records.append(result)

        # Write back to metrics_df
        mask = (metrics_df["asset_id"] == aid) & (metrics_df["year"] == year)
        metrics_df.loc[mask, "financial_score"] = result["financial_score"]
        metrics_df.loc[mask, "environmental_score"] = result["environmental_score"]
        metrics_df.loc[mask, "social_score"] = result["social_score"]
        metrics_df.loc[mask, "performance_score"] = result["overall_score"]

    return metrics_df, score_records


def write_scores_json(score_records: list, repo_root: Path = None, year: int = 2026):
    repo_root = repo_root or Path(__file__).resolve().parents[3]
    out = repo_root / "mock" / "business" / f"scores_{year}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(score_records, f, indent=2)
    return out