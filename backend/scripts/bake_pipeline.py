"""Bake the walking and driving pipeline to disk for sub-second boot.

Run this ONCE offline (or whenever the base network geojson changes):
    python backend/scripts/bake_pipeline.py

The simulation engine will preferentially load these pickles at runtime,
bypassing the 20+ second NetworkX graph build and Dijkstra computation.
"""

import pickle
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config import load_paths, load_assumptions
from app.loaders.geometry_loader import load_geometry
from app.loaders.business_loader import load_business
from app.derived.engine import _prepare_mode_pipeline
from app.derived.network_graph import extract_nodes

def main():
    print("Loading paths and geometry...")
    paths = load_paths()
    assumptions = load_assumptions()
    geometry = load_geometry(REPO_ROOT, paths)
    business = load_business(REPO_ROOT, paths)

    base_network = geometry["network"]["analysis"]
    parcels = geometry["parcels"]["analysis"]
    pop_analysis = geometry["population"]["analysis"]
    
    mode_configs = assumptions.get("mode_networks", {})
    walking_cfg = mode_configs.get("walking", {})
    driving_cfg = mode_configs.get("driving", {})

    print("Building walking pipeline (this takes ~20s)...")
    walking_pipe = _prepare_mode_pipeline(
        mode="walking",
        network_gdf=base_network,
        assets_df=business["assets"],
        parcels_gdf=parcels,
        pop_gdf=pop_analysis,
        gamma=assumptions.get("accessibility", {}).get("canopy_impedance_gamma", 0.3),
        cfg=walking_cfg,
    )
    walking_pipe["nodes_gdf"] = extract_nodes(base_network)
    
    print("Building driving pipeline...")
    driving_pipe = _prepare_mode_pipeline(
        mode="driving",
        network_gdf=base_network,
        assets_df=business["assets"],
        parcels_gdf=parcels,
        pop_gdf=pop_analysis,
        gamma=0.0,
        cfg=driving_cfg,
    )

    cache_dir = REPO_ROOT / paths["base"] / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    walk_path = cache_dir / "walking_pipeline_base.pkl"
    drive_path = cache_dir / "driving_pipeline_base.pkl"

    print(f"Saving to {walk_path}...")
    with open(walk_path, "wb") as f:
        pickle.dump(walking_pipe, f, protocol=pickle.HIGHEST_PROTOCOL)

    print(f"Saving to {drive_path}...")
    with open(drive_path, "wb") as f:
        pickle.dump(driving_pipe, f, protocol=pickle.HIGHEST_PROTOCOL)

    print("Bake complete. Checkpoints are ready.")

if __name__ == "__main__":
    main()