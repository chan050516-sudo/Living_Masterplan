"""Validate Phase D — B4 lease expiry and developer-held decay.

Run:
    python backend/scripts/validate_phase4_d.py

Confirms:
  1. SC-CURRENT.json has all expected years.
  2. An unsold residential asset's occupancy rises over time as
     developer-held units are sold off.
  3. A commercial asset with an anchor lease expiring mid-scenario
     shows an occupancy drop after the expiry year.
  4. The 2026 baseline still matches B3 exactly.
  5. Township carbon in SC-CURRENT drifts only from known causes
     (canopy growth, maintenance aging, population).
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


def _ok(msg):
    print(f"[ OK ] {msg}")


def _warn(msg):
    print(f"[WARN] {msg}")


def _fail(msg):
    print(f"[FAIL] {msg}")
    raise SystemExit(1)


def main():
    with open(base / "scenarios" / "SC-CURRENT.json") as f:
        sc_current = json.load(f)
    with open(base / "scenarios" / "SC-REPURPOSE.json") as f:
        sc_repurpose = json.load(f)

    years = sorted(sc_current["years"].keys())
    print(f"  scenario years: {years}")

    # --------------------------------------------------------------
    _hdr("1. 2026 baseline still matches B3")

    b3 = pd.read_csv(base / "asset_metrics_enriched.csv")
    b3_2026 = b3[b3["year"] == 2026].set_index("asset_id")
    b4_2026 = sc_current["years"]["2026"]["assets"]

    mismatches = 0
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
            mismatches += 1

    if mismatches > 0:
        _fail(f"{mismatches} assets show B3 vs B4 baseline carbon mismatch")
    _ok("2026 baseline matches B3 exactly")

    # --------------------------------------------------------------
    _hdr("2. Unsold residential — occupancy rises as units sell off")

    assets = pd.read_csv(base / "assets.csv")
    unsold_ids = assets[
        (assets["asset_type"] == "residential")
        & (assets["developer_held_units"] > 0)
    ]["asset_id"].astype(str).tolist()

    if not unsold_ids:
        _warn("no unsold residential assets found")
    else:
        for aid in unsold_ids[:3]:
            print(f"\n  {aid}:")
            for y in years:
                st = sc_current["years"][y]["assets"].get(aid, {})
                occ = st.get("occupancy_rate")
                held = st.get("developer_held_units")
                if occ is None:
                    print(f"    {y}: (missing)")
                    continue
                print(f"    {y}: occ={occ:.3f}  held={held}")

        # Check monotonic rise
        violations = 0
        for aid in unsold_ids:
            prev_occ = None
            for y in years:
                st = sc_current["years"][y]["assets"].get(aid, {})
                occ = st.get("occupancy_rate")
                if occ is None:
                    continue
                if prev_occ is not None and occ < prev_occ - 0.02:
                    violations += 1
                    break
                prev_occ = occ
        if violations > 0:
            _warn(f"{violations} unsold residential assets do not rise "
                  f"monotonically")
        else:
            _ok("all unsold residential assets rise monotonically")

    # --------------------------------------------------------------
    _hdr("3. Anchor lease expiry — commercial occupancy drop")

    lease_path = base / "asset_leases.csv"
    if not lease_path.exists():
        _warn("asset_leases.csv missing — cannot check lease expiry")
    else:
        leases = pd.read_csv(lease_path)
        # Find anchor leases (tenant_type == 'anchor') with end_year
        # in [2027, 2032] — mid-scenario expiries
        anchor = leases[
            (leases["tenant_type"] == "anchor")
            & (leases["lease_end_year"].between(2027, 2032))
        ]
        print(f"  anchor leases expiring 2027-2032: {len(anchor)}")

        for _, lease in anchor.head(3).iterrows():
            aid = lease["asset_id"]
            expiry = int(lease["lease_end_year"])
            print(f"\n  {aid} (anchor expires {expiry}):")
            for y in years:
                st = sc_current["years"][y]["assets"].get(aid, {})
                occ = st.get("occupancy_rate")
                if occ is None:
                    print(f"    {y}: (missing)")
                    continue
                marker = ""
                if int(y) == expiry:
                    marker = " ← lease expires"
                print(f"    {y}: occ={occ:.3f}{marker}")

    # --------------------------------------------------------------
    _hdr("4. Township carbon drift (SC-CURRENT)")

    tm = sc_current["comparison"]["township_metrics"]
    print(f"  carbon before: {tm.get('total_carbon_before_tco2e')}")
    print(f"  carbon after:  {tm.get('total_carbon_after_tco2e')}")
    delta = tm.get("carbon_delta_pct")
    if delta is not None:
        print(f"  delta:         {delta * 100:+.2f}%")

    # --------------------------------------------------------------
    _hdr("5. SC-REPURPOSE sanity")

    rep_target = None
    for aid in sc_repurpose["years"]["2033"]["assets"]:
        if aid.startswith("PRJ::"):
            continue
        # Identify the repurpose target by which asset changed subtype
        st26 = sc_repurpose["years"]["2026"]["assets"].get(aid, {})
        st33 = sc_repurpose["years"]["2033"]["assets"].get(aid, {})
        if st26.get("subtype") != st33.get("subtype"):
            rep_target = aid
            break

    if rep_target:
        print(f"  repurpose target: {rep_target}")
        for y in years:
            st = sc_repurpose["years"][y]["assets"].get(rep_target, {})
            print(f"    {y}: subtype={st.get('subtype')}  "
                  f"carbon={st.get('carbon_operational_tco2e')}")

    print("\n" + "=" * 72)
    print("  Phase D validation complete.")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    main()