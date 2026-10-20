"""Verify that spatial interventions actually shorten door-to-door paths.

Prints the door-to-door distance from B-03 to each population node
before and after a spatial intervention activates. Use this in demo
to show the mechanism working even when coverage_ratio is saturated.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import load_paths
from app.loaders.geometry_loader import load_geometry
from app.simulation.spatial import (
    spatial_interventions_for_year,
    apply_spatial_interventions,
)
from app.derived.engine import compute_derived_metrics

repo_root = Path(__file__).resolve().parents[2]
paths = load_paths()

geometry = load_geometry(repo_root, paths)
base_network = geometry["network"]["analysis"]

# --- B-03's entry point (its virtual node) ---
# Easiest: run B3 twice and read `median_walk_distance_m` for B-03
# under each network. But median is dominated by POP-R01. Instead
# we read `mean_walk_distance_m`, which weights by population but is
# still sensitive to POP-R02 because its weight is nonzero.
# 
# For a cleaner signal we compare the raw derived frame's
# `reachable_population_walk` and the individual catchment stats.

for label, network_override in (
    ("2027 (no intervention)", None),
    ("2028 (post_INT-002)", apply_spatial_interventions(
        base_network,
        spatial_interventions_for_year(
            __import__("pandas").read_csv(
                repo_root / paths["base"] / "business" / "interventions.csv"
            ).query("scenario_id == 'SC-REPURPOSE'"),
            2028,
        ),
    )),
):
    derived = compute_derived_metrics(
        repo_root=repo_root, year=2026, network_override=network_override,
    )
    b03 = derived[derived["asset_id"] == "B-03"].iloc[0]
    print(f"\n{label}")
    print(f"  median_walk_distance_m:   {b03['median_walk_distance_m']:.3f}")
    print(f"  mean_walk_distance_m:     {b03['mean_walk_distance_m']:.3f}")
    print(f"  p90_walk_distance_m:      {b03['p90_walk_distance_m']:.3f}")
    print(f"  coverage_ratio_5min_walk: {b03['coverage_ratio_5min_walk']:.4f}")
    print(f"  reachable_population:     {b03['reachable_population_walk']:.0f}")