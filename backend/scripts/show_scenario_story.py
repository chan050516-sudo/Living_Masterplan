"""Print the BLD-0037 story from SC-REPURPOSE.json.

Run from repo root:
    python backend/scripts/show_scenario_story.py
"""
import json
from pathlib import Path


def main():
    repo_root = Path(__file__).resolve().parents[2]
    path = (
        repo_root / "bukit_jelutong" / "processed" / "business"
        / "scenarios" / "SC-REPURPOSE.json"
    )
    if not path.exists():
        print(f"Not found: {path}")
        return

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    print("=" * 72)
    print("SC-REPURPOSE — township aggregate")
    print("=" * 72)
    agg = data["comparison"]["aggregate"]
    for k in (
        "asset_count",
        "total_carbon_before_tco2e",
        "total_carbon_after_tco2e",
        "carbon_delta_pct",
        "avoided_embodied_carbon_tco2e",
    ):
        v = agg.get(k)
        if isinstance(v, float):
            print(f"  {k:<40} {v:,.2f}")
        else:
            print(f"  {k:<40} {v}")

    print()
    print("=" * 72)
    print("BLD-0037 — per-asset comparison")
    print("=" * 72)
    per_asset = data["comparison"]["per_asset"]
    b37 = per_asset.get("BLD-0037")
    if not b37:
        print("  BLD-0037 not in per_asset")
        return

    for key, v in b37.items():
        if key == "_linked_projects":
            continue
        before = v.get("before")
        after = v.get("after")
        unit = v.get("unit", "")
        b = f"{before:,.3f}" if isinstance(before, (int, float)) else str(before)
        a = f"{after:,.3f}" if isinstance(after, (int, float)) else str(after)
        print(f"  {key:<38} {b:>16}  ->  {a:<16} {unit}")

    print()
    print("=" * 72)
    print("Comparison across three scenarios (township carbon)")
    print("=" * 72)
    scen_dir = path.parent
    for sid in ("SC-CURRENT", "SC-REPURPOSE", "SC-DELAY"):
        p = scen_dir / f"{sid}.json"
        if not p.exists():
            continue
        with open(p, encoding="utf-8") as f:
            s = json.load(f)
        agg = s["comparison"]["aggregate"]
        tm = s["comparison"]["township_metrics"]
        print(f"  {sid:<16} "
              f"township_carbon_after={tm.get('total_carbon_after_tco2e', 0):,.0f}  "
              f"avoided_embodied={agg.get('avoided_embodied_carbon_tco2e')}")


if __name__ == "__main__":
    main()