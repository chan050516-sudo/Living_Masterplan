"""Diagnose B3 vs B4 baseline consistency.

After the energy fix, B3's 2026 baseline and B4's year-2026 state
must produce identical carbon for every asset. Any nonzero
difference means a hidden dtype / source mismatch.

Also reports the B4 2026 -> 2033 carbon trend to confirm that
inactivity in SC-CURRENT produces no spurious drift.
"""

import json
from pathlib import Path

import pandas as pd

repo_root = Path(__file__).resolve().parents[2]
base = repo_root / "bukit_jelutong" / "processed" / "business"


def _hdr(t):
    print("\n" + "=" * 72)
    print(f"  {t}")
    print("=" * 72)


def main():
    b3 = pd.read_csv(base / "asset_metrics_enriched.csv")
    b3_2026 = b3[b3["year"] == 2026].set_index("asset_id")

    with open(base / "scenarios" / "SC-CURRENT.json") as f:
        sc = json.load(f)

    # --- 1. B3 vs B4 baseline (2026) ---
    _hdr("1. B3 vs B4 baseline carbon (2026)")
    b4_2026 = sc["years"]["2026"]["assets"]

    diffs = []
    for aid, b4row in b4_2026.items():
        if aid.startswith("PRJ::"):
            continue
        if aid not in b3_2026.index:
            continue
        try:
            b3v = float(b3_2026.loc[aid]["carbon_operational_tco2e"])
            b4v = float(b4row.get("carbon_operational_tco2e"))
        except (TypeError, ValueError, KeyError):
            continue
        if abs(b3v - b4v) > 1.0:
            diffs.append((aid, b3v, b4v, b4v - b3v))

    print(f"  assets with |B3 - B4| > 1 tCO2e: {len(diffs)}")
    for aid, b3v, b4v, d in sorted(diffs, key=lambda x: -abs(x[3]))[:15]:
        print(f"    {aid:<12} B3={b3v:>10.1f}  B4={b4v:>10.1f}  Δ={d:+10.1f}")

    if diffs:
        print("\n  [FAIL] 2026 baseline is not consistent between B3 and B4")
    else:
        print("\n  [ OK ] 2026 baseline is identical")

    # --- 2. B4 carbon drift 2026 -> 2033 (no intervention) ---
    _hdr("2. SC-CURRENT carbon drift 2026 -> 2033")
    b4_2033 = sc["years"]["2033"]["assets"]

    drift = []
    for aid in sorted(b4_2026.keys()):
        if aid.startswith("PRJ::"):
            continue
        try:
            c26 = float(b4_2026[aid].get("carbon_operational_tco2e"))
            c33 = float(b4_2033.get(aid, {}).get("carbon_operational_tco2e"))
        except (TypeError, ValueError):
            continue
        d = c33 - c26
        if abs(d) > 5.0:
            drift.append((aid, c26, c33, d))

    print(f"  assets with |drift| > 5 tCO2e: {len(drift)}")
    for aid, c26, c33, d in sorted(drift, key=lambda x: -abs(x[3]))[:15]:
        print(f"    {aid:<12} 2026={c26:>8.1f}  2033={c33:>8.1f}  Δ={d:+8.1f}")

    if drift:
        print("\n  [WARN] carbon drifts in a no-intervention scenario.")
        print("  Expected sources: canopy growth (lowers HVAC), maintenance")
        print("  carbon aging, population-driven occupancy. Not expected:")
        print("  subtype structure change.")
    else:
        print("\n  [ OK ] no carbon drift in SC-CURRENT")

    # --- 3. Effective demand drift for BLD-0037 ---
    _hdr("3. BLD-0037 effective_demand_m2 over time")
    for year in ("2026", "2027", "2028", "2030", "2033"):
        st = sc["years"].get(year, {}).get("assets", {}).get("BLD-0037", {})
        ed = st.get("effective_demand_m2")
        print(f"  {year}: effective_demand_m2 = {ed}")

    # --- 4. BLD-0183 in SC-REPURPOSE ---
    _hdr("4. BLD-0183 in SC-REPURPOSE (carbon + subtype)")
    with open(base / "scenarios" / "SC-REPURPOSE.json") as f:
        sc_rep = json.load(f)
    for year in ("2026", "2027", "2028", "2030", "2033"):
        st = sc_rep["years"].get(year, {}).get("assets", {}).get("BLD-0183", {})
        c = st.get("carbon_operational_tco2e")
        stype = st.get("subtype") or st.get("_effective_subtype")
        print(f"  {year}: carbon={c}  subtype={stype}")


if __name__ == "__main__":
    main()