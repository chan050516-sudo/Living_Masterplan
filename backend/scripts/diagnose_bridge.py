"""Diagnose whether walking-graph bridging is working.

Run from repo root:
    python backend/scripts/diagnose_bridge.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import load_paths, load_assumptions
from app.loaders.geometry_loader import load_geometry
from app.derived.network_graph import build_graph_by_mode
import networkx as nx


def main():
    repo_root = Path(__file__).resolve().parents[2]
    paths = load_paths()
    assumptions = load_assumptions()
    geometry = load_geometry(repo_root, paths)

    gamma = assumptions.get("accessibility", {}).get(
        "canopy_impedance_gamma", 0.3
    )

    network = geometry["network"]["analysis"]
    print(f"Network CRS: {network.crs}")
    print(f"Network rows: {len(network)}")
    print(f"edge_id dtype: {network['edge_id'].dtype}")
    print(f"from_node sample: {network['from_node'].head(3).tolist()}")

    G = build_graph_by_mode(network, mode="walking", gamma=gamma)

    print()
    print(f"Graph nodes: {G.number_of_nodes()}")
    print(f"Graph edges: {G.number_of_edges()}")

    bridge_count = sum(
        1 for _, _, d in G.edges(data=True) if d.get("is_bridge")
    )
    print(f"Bridge edges added: {bridge_count}")

    comps = list(nx.connected_components(G))
    print(f"Components: {len(comps)}")
    print(f"Top sizes: {sorted([len(c) for c in comps], reverse=True)[:10]}")

    # Sample bridge edges
    bridge_samples = [
        (u, v, d) for u, v, d in G.edges(data=True) if d.get("is_bridge")
    ][:5]
    if bridge_samples:
        print()
        print("Sample bridge edges:")
        for u, v, d in bridge_samples:
            print(f"  {u} <-> {v}, length={d['length_m']:.1f}m, "
                  f"eff={d['effective_length_m']:.1f}m")


if __name__ == "__main__":
    main()