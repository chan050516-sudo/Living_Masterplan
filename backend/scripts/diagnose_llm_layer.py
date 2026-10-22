"""Diagnose the B7 data layer against bukit_jelutong/processed.

Run from repo root:
    python backend/scripts/diagnose_llm_layer.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.tool_service import TownshipDataSource, TOOL_DISPATCH


def main():
    repo_root = Path(__file__).resolve().parents[2]
    ds = TownshipDataSource(repo_root, year=2026)

    print("=" * 72)
    print("TownshipDataSource — loaded")
    print("=" * 72)
    print(f"  repo_root:      {ds.repo_root}")
    print(f"  base:           {ds.paths['base']}")
    print(f"  assets:         {len(ds.assets)} rows")
    print(f"  metrics:        {len(ds.metrics)} rows")
    print(f"  projects:       {len(ds.projects)} rows")
    print(f"  candidates:     {len(ds.candidates)} rows")
    print(f"  interventions:  {len(ds.interventions)} rows")
    print(f"  deadspace:      {len(ds.deadspace)} records")

    if ds.assets.empty:
        print("\n  FATAL: assets.csv is empty or unreadable")
        return

    print()
    print("=" * 72)
    print("Asset sample")
    print("=" * 72)
    print(ds.assets[["asset_id", "asset_type", "subtype"]].head(5).to_string())

    print()
    print("=" * 72)
    print("Deadspace status distribution")
    print("=" * 72)
    from collections import Counter
    statuses = Counter(
        r.get("status", "unknown") for r in ds.deadspace.values()
    )
    for s, n in statuses.most_common():
        print(f"  {s:<28} {n}")

    # Pick a candidate target asset for later testing
    candidates = [
        aid for aid, r in ds.deadspace.items()
        if r.get("status") == "deadspace_candidate"
    ][:3]
    print()
    print("=" * 72)
    print("Sample deadspace_candidate asset IDs for later tests")
    print("=" * 72)
    for aid in candidates:
        print(f"  {aid}")

    # Test every tool
    print()
    print("=" * 72)
    print("Tool dispatch smoke test")
    print("=" * 72)
    test_calls = []
    if candidates:
        aid = candidates[0]
        test_calls = [
            ("get_asset_state", {"asset_id": aid}),
            ("get_asset_evidence", {"asset_id": aid}),
            ("get_deadspace_status", {"asset_id": aid}),
            ("get_catchment_profile", {"asset_id": aid, "mode": "walk"}),
            ("get_population_profile", {"asset_id": aid}),
            ("get_nearby_assets", {"asset_id": aid, "radius_m": 800}),
            ("get_action_space", {"asset_type": "commercial"}),
        ]
    test_calls.extend([
        ("get_available_subtypes", {"asset_class": "community_facility"}),
        ("get_assumptions_slice", {"keys": ["huff", "environmental"]}),
        ("get_taxonomy_entry", {"subtype": "clinic"}),
    ])

    for name, args in test_calls:
        fn = TOOL_DISPATCH.get(name)
        if fn is None:
            print(f"  [MISSING] {name}")
            continue
        try:
            result = fn(ds, args)
            kind = type(result).__name__
            if isinstance(result, list):
                summary = f"list[{len(result)}]"
            elif isinstance(result, dict):
                keys = list(result.keys())[:5]
                summary = f"dict({len(result)} keys: {keys})"
            else:
                summary = str(result)[:60]
            print(f"  [OK]   {name:<28} -> {summary}")
        except Exception as e:
            print(f"  [FAIL] {name:<28} -> {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()