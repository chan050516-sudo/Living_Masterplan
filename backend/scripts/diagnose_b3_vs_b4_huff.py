"""Diagnose B3 vs B4 Huff input consistency.

Compares:
  1. Asset entries: which assets get an entry in B3 vs B4.
  2. Demand entries: same population nodes.
  3. Supply nodes for BLD-0037.
  4. Distance matrix for a known pair.
  5. Huff result when given IDENTICAL inputs.

Run:
    python backend/scripts/diagnose_b3_vs_b4_huff.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import load_paths, load_assumptions
from app.derived.engine import _prepare_mode_pipeline
from app.derived.huff import (
    huff_by_subtype_per_asset,
    huff_gravity_by_subtype,
)
from app.derived.network_graph import (
    build_walk_graph, find_entry_point, insert_all_entries, extract_nodes,
)
from app.loaders.geometry_loader import load_geometry
from app.loaders.business_loader import load_business
from app.simulation.engine import _build_graph_and_nodes, _compute_distance_matrix
from app.taxonomy import get_taxonomy


def _hdr(t):
    print("\n" + "=" * 72)
    print(f"  {t}")
    print("=" * 72)


def main():
    repo_root = Path(__file__).resolve().parents[2]
    paths = load_paths()
    assumptions = load_assumptions()
    geometry = load_geometry(repo_root, paths)
    business = load_business(repo_root, paths)
    subtypes_config = get_taxonomy().get("subtypes", {})

    walking_cfg = assumptions.get("mode_networks", {}).get("walking", {})
    gamma = assumptions.get("accessibility", {}).get(
        "canopy_impedance_gamma", 0.3,
    )

    print("Building B3 walking pipeline...")
    b3 = _prepare_mode_pipeline(
        mode="walking",
        network_gdf=geometry["network"]["analysis"],
        assets_df=business["assets"],
        parcels_gdf=geometry["parcels"]["analysis"],
        pop_gdf=geometry["population"]["analysis"],
        gamma=gamma,
        cfg=walking_cfg,
    )

    print("Building B4 walking pipeline...")
    G_b4, d_b4, s_b4, _ = _build_graph_and_nodes(
        geometry, business["assets"], assumptions, network_gdf=None,
    )
    dm_b4 = _compute_distance_matrix(G_b4)

    # ------------------------------------------------------------------
    _hdr("1. Asset entries")
    b3_assets = set(b3["asset_entries"].keys())
    b4_assets = set(s["asset_id"] for s in s_b4)
    print(f"  B3 asset_entries: {len(b3_assets)}")
    print(f"  B4 unique supply assets: {len(b4_assets)}")

    only_in_b3 = sorted(b3_assets - b4_assets)
    only_in_b4 = sorted(b4_assets - b3_assets)
    print(f"  Assets in B3 only: {len(only_in_b3)}")
    for aid in only_in_b3[:15]:
        print(f"    {aid}")
    print(f"  Assets in B4 only: {len(only_in_b4)}")
    for aid in only_in_b4[:15]:
        print(f"    {aid}")

    # ------------------------------------------------------------------
    _hdr("2. Demand entries")
    b3_dem_pop = {
        d["demand_id"]: d["population"] for d in b3["demand_entries"]
    }
    b4_dem_pop = {
        d["population_id"]: d["population"] for d in d_b4
    }
    print(f"  B3 demand nodes: {len(b3_dem_pop)}")
    print(f"  B4 demand nodes: {len(b4_dem_pop)}")
    only_d = set(b3_dem_pop) - set(b4_dem_pop)
    if only_d:
        print(f"  B3-only demand: {list(only_d)[:5]}")

    # ------------------------------------------------------------------
    _hdr("3. BLD-0037 supply nodes")
    b3_bld_entry = b3["asset_entries"].get("BLD-0037")
    b4_bld_nodes = [s for s in s_b4 if s["asset_id"] == "BLD-0037"]
    print(f"  B3 entry: {b3_bld_entry}")
    print(f"  B4 supply nodes: {len(b4_bld_nodes)}")
    for s in b4_bld_nodes:
        print(f"    subtype={s['subtype']:<22} area={s['attractiveness']:>8.1f}  node={s['node']}")

    # ------------------------------------------------------------------
    _hdr("4. Distance matrix consistency")
    print(f"  B3 DM source nodes: {len(b3['distance_matrix'])}")
    print(f"  B4 DM source nodes: {len(dm_b4)}")

    # Pick BLD-0037's demand node
    if b3["demand_entries"] and b3_bld_entry:
        d0 = b3["demand_entries"][0]
        b3_d_vn = d0["virtual_node"]
        b3_s_vn = b3_bld_entry["virtual_node"]

        # Find matching B4 nodes
        b4_d_match = [d for d in d_b4 if d["population_id"] == d0["demand_id"]]
        b4_d_vn = b4_d_match[0]["node"] if b4_d_match else None
        b4_s_vn = b4_bld_nodes[0]["node"] if b4_bld_nodes else None

        print(f"  demand_id={d0['demand_id']}")
        print(f"    B3 vn: {b3_d_vn}")
        print(f"    B4 vn: {b4_d_vn}")
        print(f"    match: {b3_d_vn == b4_d_vn}")

        if b3_d_vn == b4_d_vn and b3_s_vn == b4_s_vn:
            b3_dist = b3["distance_matrix"].get(b3_d_vn, {}).get(b3_s_vn)
            b4_dist = dm_b4.get(b4_d_vn, {}).get(b4_s_vn)
            print(f"  B3 distance: {b3_dist}")
            print(f"  B4 distance: {b4_dist}")
            print(f"  match: {b3_dist == b4_dist}")
        elif b3_s_vn != b4_s_vn:
            print(f"  [WARN] supply virtual nodes differ:")
            print(f"    B3: {b3_s_vn}")
            print(f"    B4: {b4_s_vn}")

    # ------------------------------------------------------------------
    _hdr("5. Huff with identical inputs (B3 DM + B3 demand + B4 supply)")
    # This isolates whether the difference is in supply structure or DM.
    b3_demand_for_huff = [
        {
            "population_id": e["demand_id"],
            "node": e["virtual_node"],
            "population": e["population"],
        }
        for e in b3["demand_entries"]
    ]

    huff_a = huff_by_subtype_per_asset(
        b3["distance_matrix"],
        b3_demand_for_huff,
        s_b4,
        subtypes_config=subtypes_config,
        alpha=1.0, beta=2.0,
    )
    a_total = sum(huff_a.get("BLD-0037", {}).values())
    print(f"  B3 DM + B4 supply → BLD-0037 total: {a_total:.2f}")

    # B4 DM + B4 demand + B4 supply
    huff_b = huff_gravity_by_subtype(
        dm_b4,
        d_b4,
        s_b4,
        subtypes_config=subtypes_config,
        alpha=1.0, beta=2.0,
    )
    b_total = huff_b.get("BLD-0037", 0.0)
    print(f"  B4 DM + B4 demand + B4 supply → BLD-0037 total: {b_total:.2f}")

    if a_total > 0:
        print(f"  Ratio (B4 / B3 DM with same supply): {b_total / a_total:.3f}")

    _hdr("Done")
    print("\nIf ratio ≈ 1.00, the bug is in how simulate_scenario builds")
    print("year_supply_nodes. If ratio differs from 1.00, the B3 and B4")
    print("distance matrices are not consistent.")


if __name__ == "__main__":
    main()