"""Print the LLM context pack for a specific asset."""
import sys
import json
from pathlib import Path

# Ensure the app module can be imported
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.tool_service import TownshipDataSource
from app.llm.context_builder import build_context_pack

def main():
    repo_root = Path(__file__).resolve().parents[2]
    ds = TownshipDataSource(repo_root, year=2026)

    # Test query
    intent = {
        "target_asset_ids": ["BLD-0183"],
        "objective": "balanced",
        "constraints": {"capex_limit": 3000000, "no_demolition": True},
        "question_text": "What should we do with BLD-0183?",
    }

    print(f"\nBuilding context pack for: {intent['target_asset_ids'][0]} ...\n")
    pack = build_context_pack(intent, ds)

    # 1. Print Macro Baseline
    print("=" * 60)
    print(" MACRO: TOWNSHIP BASELINE")
    print("=" * 60)
    print(json.dumps(pack.get("township_baseline"), indent=2))

    # 2. Print Meso Spatial Rings
    target = pack["targets"][0]
    print("\n" + "=" * 60)
    print(" MESO: SPATIAL RINGS (Top Competitors & Anchors)")
    print("=" * 60)
    print(json.dumps(target.get("spatial_rings"), indent=2))

    # 3. Print Micro Catchment (Population)
    print("\n" + "=" * 60)
    print(" MICRO: CATCHMENT POPULATION (Walk 15min)")
    print("=" * 60)
    print(json.dumps(target.get("population"), indent=2))

    # Export full JSON for inspection
    out_path = Path("llm_context_debug.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(pack, f, indent=2, default=str)
    
    print(f"\n[+] Full context pack exported to {out_path.resolve()}")

if __name__ == "__main__":
    main()