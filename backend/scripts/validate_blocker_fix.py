"""Validate the Phase E blocker fix — reachable_population_walk must
rise when a residential new_development project is delivered inside
an asset's walking catchment.

Run:
    python backend/scripts/validate_blocker_fix.py
"""

import json
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
base = repo_root / "bukit_jelutong" / "processed" / "business"


def _hdr(t):
    print("\n" + "=" * 72)
    print(f"  {t}")
    print("=" * 72)


def _ok(msg):
    print(f"[ OK ] {msg}")

def _warn(msg):
    print(f"[WARN] {msg}")
    
def _fail(msg):
    print(f"[FAIL] {msg}")
    raise SystemExit(1)


def main():
    with open(base / "scenarios" / "SC-CURRENT.json") as f:
        sc = json.load(f)

    years = sorted(sc["years"].keys())
    print(f"  years: {years}")

    # --------------------------------------------------------------
    _hdr("1. residential project nodes are stashed")

    import pandas as pd
    projects = pd.read_csv(base / "development_projects.csv")
    res_projects = projects[
        (projects["land_use"] == "residential")
        & (projects["units"].notna())
    ]
    print(f"  residential projects with units: {len(res_projects)}")

    if len(res_projects) == 0:
        _fail("no residential projects to test — check development_projects.csv")

    # --------------------------------------------------------------
    _hdr("2. any commercial asset's reachable_population_walk rises")

    # Find a commercial asset with a residential project in its catchment.
    # Simplest proxy: iterate all assets, compare 2026 vs 2033.
    rises = []
    for aid, st_2026 in sc["years"]["2026"]["assets"].items():
        if aid.startswith("PRJ::"):
            continue
        st_2033 = sc["years"]["2033"]["assets"].get(aid, {})
        b = st_2026.get("reachable_population_walk")
        a = st_2033.get("reachable_population_walk")
        try:
            b = float(b)
            a = float(a)
        except (TypeError, ValueError):
            continue
        if a > b + 1.0:
            rises.append((aid, b, a, a - b))

    if not rises:
        _fail("no asset shows reachable_population_walk rising — "
              "the blocker fix did not take effect")
    else:
        print(f"  assets whose reachable_population_walk rises: {len(rises)}")
        for aid, b, a, d in sorted(rises, key=lambda x: -x[3])[:5]:
            print(f"    {aid:<12} 2026={b:>8,.1f}  2033={a:>8,.1f}  "
                  f"Δ=+{d:>6,.1f}")
        _ok(f"reachable_population_walk rises for {len(rises)} assets")

    # --------------------------------------------------------------
    # --------------------------------------------------------------
    _hdr("3. commercial asset: reachable_pop AND effective_demand rise together")

    import pandas as pd
    assets_df = pd.read_csv(base / "assets.csv")
    commercial_ids = set(
        assets_df[assets_df["asset_type"] == "commercial"]["asset_id"].astype(str)
    )

    # Find commercial assets whose reachable_population_walk rises
    commercial_rises = [
        (aid, b, a, d) for aid, b, a, d in rises
        if aid in commercial_ids
    ]

    if not commercial_rises:
        _warn(
            "no COMMERCIAL asset shows reachable_population_walk rising. "
            "This could mean:\n"
            "  (a) the residential projects fall outside every commercial "
            "      asset's catchment, OR\n"
            "  (b) the blocker fix applied but only to non-commercial assets"
        )
    else:
        print(f"  commercial assets with rising reachable_pop: "
              f"{len(commercial_rises)}")
        for aid, b, a, d in sorted(commercial_rises, key=lambda x: -x[3])[:5]:
            st_2026 = sc["years"]["2026"]["assets"].get(aid, {})
            st_2033 = sc["years"]["2033"]["assets"].get(aid, {})
            edm_b = st_2026.get("effective_demand_m2")
            edm_a = st_2033.get("effective_demand_m2")
            edm_delta_str = "?"
            if (edm_b is not None and edm_a is not None):
                try:
                    edm_delta_str = f"{float(edm_a) - float(edm_b):+.1f}"
                except (TypeError, ValueError):
                    pass
            print(f"\n  {aid}:")
            print(f"    reachable_population_walk: {b:>8,.0f} -> {a:>8,.0f}  "
                  f"Δ=+{d:>6,.0f}")
            print(f"    effective_demand_m2:       {edm_b} -> {edm_a}  "
                  f"Δ={edm_delta_str}")

        # Positive verification: at least one commercial asset must show
        # BOTH metrics rising.
        both_rise = 0
        for aid, _, _, _ in commercial_rises:
            st_2026 = sc["years"]["2026"]["assets"].get(aid, {})
            st_2033 = sc["years"]["2033"]["assets"].get(aid, {})
            try:
                edm_b = float(st_2026.get("effective_demand_m2"))
                edm_a = float(st_2033.get("effective_demand_m2"))
            except (TypeError, ValueError):
                continue
            if edm_a > edm_b + 1.0:
                both_rise += 1

        if both_rise > 0:
            _ok(f"{both_rise} commercial assets show BOTH metrics rising")
        else:
            _warn(
                "reachable_population rises but effective_demand_m2 does not. "
                "This suggests Huff supply competition is absorbing the "
                "additional demand. Check whether a competitor asset also "
                "delivered in the same catchment."
            )


if __name__ == "__main__":
    main()