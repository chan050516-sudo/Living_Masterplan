"""Run Phase 1 — compute derived metrics for the mock township."""

import sys
from pathlib import Path

import pandas as pd

# Allow running as a script
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.derived.engine import compute_derived_metrics, merge_into_asset_metrics


def main():
    repo_root = Path(__file__).resolve().parents[2]
    year = 2026

    print(f"Running Phase 1 (B3) for year {year}...")
    derived = compute_derived_metrics(repo_root=repo_root, year=year)
    print("\n--- Derived metrics ---")
    print(derived.to_string(index=False))

    # Merge back into asset_metrics.csv
    metrics_path = repo_root / "mock" / "business" / "asset_metrics.csv"
    existing = pd.read_csv(metrics_path)
    merged = merge_into_asset_metrics(derived, existing, year=year)

    out_path = repo_root / "mock" / "business" / "asset_metrics_enriched.csv"
    merged.to_csv(out_path, index=False)
    print(f"\nWrote enriched metrics to {out_path}")


if __name__ == "__main__":
    main()