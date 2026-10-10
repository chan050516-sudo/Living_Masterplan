"""B6 unified entry point — run detection on every asset."""

import json
import logging
from pathlib import Path

import pandas as pd

from ..config import load_paths, load_assumptions
from .detector import detect_deadspace_for_asset

log = logging.getLogger(__name__)


def detect_all_deadspace(repo_root: Path = None, year: int = 2026) -> list:
    repo_root = repo_root or Path(__file__).resolve().parents[3]
    paths = load_paths()
    assumptions = load_assumptions()

    base = repo_root / paths["base"]
    metrics_df = pd.read_csv(base / "business" / "asset_metrics_enriched.csv")
    assets_df = pd.read_csv(base / "business" / "assets.csv")
    scores_path = base / "business" / f"scores_{year}.json"

    if not scores_path.exists():
        raise FileNotFoundError(
            f"Scores JSON not found: {scores_path}. Run Phase 2 first."
        )

    with open(scores_path, "r", encoding="utf-8") as f:
        scores = json.load(f)
    scores_by_id = {s["asset_id"]: s for s in scores}

    results = []
    for _, asset in assets_df.iterrows():
        aid = asset["asset_id"]
        row = metrics_df[
            (metrics_df["asset_id"] == aid) & (metrics_df["year"] == year)
        ]
        if row.empty:
            log.warning("No metrics for %s year %d — skipping", aid, year)
            continue

        score_record = scores_by_id.get(aid)
        if score_record is None:
            log.warning("No score for %s — skipping", aid)
            continue

        results.append(
            detect_deadspace_for_asset(
                asset=asset,
                metrics=row.iloc[0],
                score_record=score_record,
                assumptions=assumptions,
            )
        )

    return results


def write_deadspace_json(records: list, repo_root: Path = None, year: int = 2026) -> Path:
    repo_root = repo_root or Path(__file__).resolve().parents[3]
    out = repo_root / "mock" / "business" / f"deadspace_{year}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
    return out


def deadspace_list(records: list) -> list:
    """Filter to only those that triggered a non-healthy status."""
    return [r for r in records if r["status"] != "healthy"]