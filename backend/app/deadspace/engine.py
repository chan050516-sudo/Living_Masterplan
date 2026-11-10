"""B6 unified entry point — run detection on every asset.

Phase 3 change: no longer loads scores. Reads enriched metrics directly.
"""

import json
import logging
from pathlib import Path
import numpy as np
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

    dsr_stats = {}
    commercial_metrics = metrics_df[
        (metrics_df["year"] == year) & 
        (metrics_df["subtype"].notna())
    ]
    
    for subtype, group in commercial_metrics.groupby("subtype"):
        dsrs = group["dsr"].dropna()
        if len(dsrs) >= 4:
            q1 = np.percentile(dsrs, 25)
            q3 = np.percentile(dsrs, 75)
            iqr = q3 - q1
            lower_bound = q1 - 1.5 * iqr
            dsr_stats[subtype] = round(max(lower_bound, 0.10), 3)
        else:
            dsr_stats[subtype] = None

    assumptions["deadspace"]["layer1"]["dsr_stats_by_subtype"] = dsr_stats
    # ========================================================

    results = []
    for _, asset in assets_df.iterrows():
        aid = asset["asset_id"]
        row = metrics_df[
            (metrics_df["asset_id"] == aid) & (metrics_df["year"] == year)
        ]
        if row.empty:
            log.warning("No metrics for %s year %d — skipping", aid, year)
            continue

        results.append(
            detect_deadspace_for_asset(
                asset=asset,
                metrics=row.iloc[0],
                assumptions=assumptions,
            )
        )

    return results


def write_deadspace_json(records: list, repo_root: Path = None, year: int = 2026) -> Path:
    """
    FIX: output path now derives from paths.yml instead of a hard-coded
    "mock/" prefix, so moving `base` in config does not silently write
    to the wrong place.
    """
    repo_root = repo_root or Path(__file__).resolve().parents[3]
    paths = load_paths()
    out = repo_root / paths["base"] / "business" / f"deadspace_{year}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
    return out


def deadspace_list(records: list) -> list:
    """Return only non-healthy assets, sorted by urgency (descending)."""
    non_healthy = [r for r in records if r["status"] != "healthy"]
    non_healthy.sort(key=lambda r: r["urgency_index"], reverse=True)
    return non_healthy