"""Compare B3 and B4 supply node generation for a single asset."""

import json
import pandas as pd
from pathlib import Path


def _hdr(t):
    print("\n" + "=" * 72)
    print(f"  {t}")
    print("=" * 72)


def _parse_mix(raw):
    if raw is None:
        return None
    try:
        if pd.isna(raw):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(raw, dict):
        return raw or None
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) and obj else None
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def main():
    repo_root = Path(__file__).resolve().parents[2]
    base = repo_root / "bukit_jelutong" / "processed" / "business"

    assets = pd.read_csv(base / "assets.csv")
    bld = assets[assets["asset_id"] == "BLD-0037"]

    _hdr("1. BLD-0037 raw asset row")
    if bld.empty:
        print("  BLD-0037 not in assets.csv")
        return
    row = bld.iloc[0]
    print(f"  asset_type:     {row.get('asset_type')}")
    print(f"  subtype:        {row.get('subtype')}")
    print(f"  lettable_m2:    {row.get('lettable_area_m2')}")
    print(f"  floor_area_m2:  {row.get('floor_area_m2')}")
    raw_mix = row.get("unit_mix_json")
    print(f"  unit_mix_json:  {raw_mix if pd.notna(raw_mix) else '(NaN)'}")

    mix = _parse_mix(raw_mix)
    if mix:
        print(f"  parsed mix keys: {list(mix.keys())}")
        total_mix_area = sum(m.get("area_m2", 0) for m in mix.values())
        print(f"  total mix area: {total_mix_area}")
    else:
        print("  parsed mix:     None (single subtype)")

    _hdr("2. SC-CURRENT.json 2026 baseline (B3)")
    with open(base / "scenarios" / "SC-CURRENT.json") as f:
        sc = json.load(f)

    y2026 = sc["years"]["2026"]["assets"].get("BLD-0037", {})
    print(f"  effective_demand_m2: {y2026.get('effective_demand_m2')}")
    print(f"  effective_demand_by_subtype_json: "
          f"{y2026.get('effective_demand_by_subtype_json')}")

    _hdr("3. SC-CURRENT.json 2027 (B4)")
    if "2027" in sc["years"]:
        y2027 = sc["years"]["2027"]["assets"].get("BLD-0037", {})
        print(f"  effective_demand_m2: {y2027.get('effective_demand_m2')}")
        print(f"  effective_demand_by_subtype_json: "
              f"{y2027.get('effective_demand_by_subtype_json')}")
    else:
        print("  2027 not in SC-CURRENT.json (run without --quick to see)")

    _hdr("4. Compare mix consistency")
    if mix and "2027" in sc["years"]:
        y2027_mix = y2027.get("effective_demand_by_subtype_json")
        if y2027_mix:
            try:
                y2027_parsed = json.loads(y2027_mix)
                print(f"  2026 subtypes: {list(mix.keys())}")
                print(f"  2027 subtypes: {list(y2027_parsed.keys())}")
                if set(mix.keys()) != set(y2027_parsed.keys()):
                    print("  [FAIL] subtype set differs between B3 and B4")
                else:
                    print("  [ OK ] subtype set identical")
            except (json.JSONDecodeError, TypeError):
                print("  could not parse 2027 subtype json")


if __name__ == "__main__":
    main()