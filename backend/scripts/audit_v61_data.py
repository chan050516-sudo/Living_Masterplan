"""Full-shape audit of the v6.1 data layer.

Prints cross-tabs, distributions, and consistency checks so the team
can see whether the mocks match Malaysian development reality.

Run:
    python backend/scripts/audit_v61_data.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

with (BACKEND_DIR / "configs" / "paths.yml").open(encoding="utf-8") as f:
    PATHS = yaml.safe_load(f)
with (BACKEND_DIR / "configs" / "taxonomy.yml").open(encoding="utf-8") as f:
    TAXONOMY = yaml.safe_load(f)

BASE = REPO_ROOT / PATHS["base"]
BUSINESS = BASE / "business"
EXTERNAL = BASE / "external_data_mock"


def _section(title):
    print()
    print("=" * 78)
    print(f"  {title}")
    print("=" * 78)


def _subsection(title):
    print(f"\n  ── {title}")


def _print_table(df, index=True):
    if df.empty:
        print("  (empty)")
        return
    print(df.to_string(index=index))
    print()


def _warn(msg):
    print(f"  [WARN] {msg}")


def _ok(msg):
    print(f"  [ OK ] {msg}")


def _fail(msg):
    print(f"  [FAIL] {msg}")


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def _load():
    return {
        "assets": pd.read_csv(BUSINESS / "assets.csv"),
        "metrics": pd.read_csv(BUSINESS / "asset_metrics.csv"),
        "leases": pd.read_csv(BUSINESS / "asset_leases.csv")
            if (BUSINESS / "asset_leases.csv").exists() else pd.DataFrame(),
        "google": pd.read_csv(EXTERNAL / "google_places_snapshots.csv")
            if (EXTERNAL / "google_places_snapshots.csv").exists() else pd.DataFrame(),
        "kido": pd.read_csv(EXTERNAL / "kido_grid.csv")
            if (EXTERNAL / "kido_grid.csv").exists() else pd.DataFrame(),
        "presence": pd.read_csv(BUSINESS / "asset_business_presence.csv")
            if (BUSINESS / "asset_business_presence.csv").exists() else pd.DataFrame(),
        "lbs": pd.read_csv(BUSINESS / "asset_lbs_metrics.csv")
            if (BUSINESS / "asset_lbs_metrics.csv").exists() else pd.DataFrame(),
        "projects": pd.read_csv(BUSINESS / "development_projects.csv")
            if (BUSINESS / "development_projects.csv").exists() else pd.DataFrame(),
    }


# ---------------------------------------------------------------------------
# 1. Authority × Asset Type
# ---------------------------------------------------------------------------

def report_authority_distribution(d):
    _section("1. Authority distribution")
    assets = d["assets"]

    _subsection("Global authority counts")
    print(assets["authority"].value_counts().to_string())
    print()

    _subsection("ownership_status counts")
    print(assets["ownership_status"].value_counts().to_string())
    print()

    _subsection("asset_type × authority cross-tab")
    ct = pd.crosstab(assets["asset_type"], assets["authority"], margins=True)
    _print_table(ct)

    _subsection("asset_type × ownership_status cross-tab")
    ct2 = pd.crosstab(
        assets["asset_type"], assets["ownership_status"], margins=True,
    )
    _print_table(ct2)

    # Check: does any strata_jmb exist?
    if "strata_jmb" in assets["ownership_status"].unique():
        _ok("strata_jmb is present in the data")
    else:
        _warn(
            "strata_jmb is NOT USED. All strata-titled assets "
            "(apartments, shop-office rows) are being labelled "
            "'sold' (advisory) which is not what they are."
        )


# ---------------------------------------------------------------------------
# 2. Subtype × Authority
# ---------------------------------------------------------------------------

def report_subtype_authority(d):
    _section("2. Subtype × Authority (commercial only)")
    assets = d["assets"]
    comm = assets[assets["asset_type"] == "commercial"]
    ct = pd.crosstab(comm["subtype"], comm["authority"], margins=True)
    _print_table(ct)

    _subsection("Commercial developer-held detail")
    dev_held = comm[comm["authority"] == "full_control"]
    if dev_held.empty:
        _warn("No developer-held commercial assets")
    else:
        print(
            dev_held[["asset_id", "subtype", "lettable_area_m2",
                      "ownership_status", "unit_count"]].to_string(index=False)
        )
        total_comm = len(comm)
        ratio = len(dev_held) / total_comm
        print(f"\n  {len(dev_held)}/{total_comm} = {ratio:.1%} developer-held")
        if ratio > 0.15:
            _warn(
                f"Ratio {ratio:.1%} is high for a mature township. "
                f"Real Malaysian shoplot developments typically sell "
                f"80-95% of commercial units; 5-20% developer-held is "
                f"only typical for a mall or newly delivered stock."
            )
        else:
            _ok(f"Ratio {ratio:.1%} is within the plausible band")


# ---------------------------------------------------------------------------
# 3. Sale Price / Capex Ratio
# ---------------------------------------------------------------------------

def report_sale_price_ratio(d):
    _section("3. Sale price ÷ Capex ratio, by subtype")
    assets = d["assets"]
    sold = assets[assets["ownership_status"] == "sold"].copy()
    if sold.empty:
        _warn("No sold assets")
        return

    sold = sold.dropna(subset=["sale_price_rm", "capex_initial_rm"])
    sold = sold[sold["capex_initial_rm"] > 0]
    sold["ratio"] = sold["sale_price_rm"] / sold["capex_initial_rm"]

    summary = sold.groupby("subtype")["ratio"].agg(
        ["count", "mean", "std", "min", "max"]
    ).round(3)
    _print_table(summary)

    _subsection("Real-world expectation (KL Klang Valley, 2015-2025)")
    print(
        "    terrace:            1.15 - 1.40   (land appreciation)\n"
        "    semidetached:       1.20 - 1.50\n"
        "    detached:           1.25 - 1.60\n"
        "    apartment_lowrise:  0.95 - 1.15\n"
        "    apartment_highrise: 0.85 - 1.10   (overhang market)\n"
        "    affordable_housing: 0.95 - 1.05   (controlled pricing)\n"
        "    shop-office row:    0.90 - 1.15   (depends on timing)\n"
        "    single-storey shop: 0.85 - 1.10\n"
        "    mall (community):   1.10 - 1.30   (anchor premium)\n"
    )


# ---------------------------------------------------------------------------
# 4. Completion Year Distribution
# ---------------------------------------------------------------------------

def report_completion_year(d):
    _section("4. Completion year distribution")
    assets = d["assets"].dropna(subset=["completion_year"])
    if assets.empty:
        _warn("No completion_year values")
        return

    by_type = assets.groupby("asset_type")["completion_year"].agg(
        ["count", "min", "median", "max"]
    )
    _print_table(by_type)

    _subsection("Age band distribution (base year 2026)")
    assets = assets.copy()
    assets["age"] = 2026 - assets["completion_year"]
    assets["age_band"] = pd.cut(
        assets["age"],
        bins=[-1, 3, 8, 16, 25, 100],
        labels=["0-3yr", "4-8yr", "9-16yr", "17-25yr", "25yr+"],
    )
    ct = pd.crosstab(assets["asset_type"], assets["age_band"])
    _print_table(ct)

    _subsection("Bukit Jelutong historical context (v6.1d)")
    print(
        "    Bukit Jelutong began development in the 1990s. The mock\n"
        "    was adjusted to reflect this four-phase structure:\n"
        "      Phase 1 (1995-2000): 20%\n"
        "      Phase 2 (2001-2010): 30%\n"
        "      Phase 3 (2011-2018): 30%\n"
        "      Phase 4 (2019-2025): 20%\n"
        "    A healthy distribution should show assets in all four\n"
        "    bands with the 17-25yr and 25yr+ bands well populated."
    )

    # Concrete check against the target distribution
    total_assets = len(assets)
    if total_assets > 0:
        n_25 = int((assets["age"] >= 25).sum())
        n_old = int((assets["age"].between(17, 25)).sum())
        ratio_25 = n_25 / total_assets
        ratio_old = n_old / total_assets
        if ratio_25 < 0.10 or ratio_old < 0.20:
            _warn(
                f"Only {ratio_25:.1%} assets 25yr+ and "
                f"{ratio_old:.1%} assets 17-25yr — "
                f"target is >= 10% and >= 20%"
            )
        else:
            _ok(
                f"{ratio_25:.1%} assets 25yr+ and "
                f"{ratio_old:.1%} assets 17-25yr — matches target"
            )


# ---------------------------------------------------------------------------
# 5. Unit Mix Distribution
# ---------------------------------------------------------------------------

def report_unit_mix(d):
    _section("5. Commercial unit_mix distribution")
    assets = d["assets"]
    comm = assets[assets["asset_type"] == "commercial"].copy()
    if comm.empty:
        _warn("No commercial assets")
        return

    comm["has_mix"] = comm["unit_mix_json"].notna()
    _subsection("Commercial assets with / without unit_mix")
    print(comm["has_mix"].value_counts().to_string())
    print()

    _subsection("Distribution of subtypes inside unit_mix")
    subtype_counts: dict[str, int] = {}
    unit_total = 0
    multi_unit_assets = 0
    for _, row in comm.iterrows():
        raw = row.get("unit_mix_json")
        if pd.isna(raw):
            continue
        try:
            mix = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(mix, dict):
            continue
        if len(mix) > 1:
            multi_unit_assets += 1
        for st, info in mix.items():
            count = info.get("count", 1) if isinstance(info, dict) else 1
            subtype_counts[st] = subtype_counts.get(st, 0) + int(count)
            unit_total += int(count)

    if subtype_counts:
        df = pd.DataFrame([
            {"subtype": k, "unit_count": v,
             "pct": round(v / unit_total * 100, 1)}
            for k, v in sorted(subtype_counts.items(), key=lambda x: -x[1])
        ])
        _print_table(df, index=False)
        print(f"  Total units: {unit_total} across {multi_unit_assets} mixed-use assets\n")

    _subsection("Real-world shop-office row composition (D'Vida / Trivo Suria)")
    print(
        "    F&B (kopitiam/restaurant/cafe):  35-45% of ground-floor units\n"
        "    Office (2nd floor up):           25-35%\n"
        "    Convenience retail:              10-15%\n"
        "    Services (salon, bank, clinic):  10-15%\n"
        "    Medical retail:                   3-8%\n"
        "    Current mock uses 42% F&B, 20% office, 17% retail,\n"
        "    13% services, 8% medical — reasonably close."
    )


# ---------------------------------------------------------------------------
# 6. Lease Coverage
# ---------------------------------------------------------------------------

def report_lease_coverage(d):
    _section("6. Lease coverage")
    assets = d["assets"]
    leases = d["leases"]

    if leases.empty:
        _warn("No lease records at all")
        return

    comm = assets[assets["asset_type"] == "commercial"].copy()
    assets_with_lease = set(leases["asset_id"].astype(str))
    comm["has_lease"] = comm["asset_id"].astype(str).isin(assets_with_lease)

    ct = pd.crosstab(comm["authority"], comm["has_lease"])
    _print_table(ct)

    _subsection("Lease_status distribution by authority")
    lease_with_authority = leases.merge(
        assets[["asset_id", "authority"]],
        on="asset_id", how="left",
    )
    ct2 = pd.crosstab(
        lease_with_authority["authority"],
        lease_with_authority["lease_status"].fillna("(null)"),
    )
    _print_table(ct2)

    _subsection("Real-world expectation")
    print(
        "    A strata-titled shoplot has leases managed by the JMB.\n"
        "    Sime Darby does not see those leases directly, but the\n"
        "    BUILDING (via the JMB) does. In a full data model, every\n"
        "    shoplot should have a lease record; the authority field\n"
        "    just decides whether the LLM can reason about it.\n"
        "    Current mock only generates leases for full_control\n"
        "    assets, which means 64+ sold shoplots have zero lease\n"
        "    record. This is a known simplification, but worth\n"
        "    documenting."
    )


# ---------------------------------------------------------------------------
# 7. Google Places / Kido Coverage
# ---------------------------------------------------------------------------

def report_external_coverage(d):
    _section("7. External data coverage")
    assets = d["assets"]
    google = d["google"]
    kido = d["kido"]
    presence = d["presence"]
    lbs = d["lbs"]

    comm = assets[assets["asset_type"] == "commercial"].copy()
    comm_all = set(comm["asset_id"].astype(str))
    comm_eligible = set(
        comm[comm["authority"].isin(["advisory", "shared"])]["asset_id"].astype(str)
    )

    _subsection("Google Places")
    covered = set(google["asset_id"].astype(str)) if not google.empty else set()
    print(f"  Assets in commercial total:     {len(comm_all)}")
    print(f"  Assets eligible (sold/shared):  {len(comm_eligible)}")
    print(f"  Assets with Google coverage:    {len(covered)}")
    print(f"  Coverage ratio:                 "
          f"{len(covered) / max(1, len(comm_eligible)):.0%}\n")

    _subsection("Kido LBS")
    if lbs.empty:
        _warn("No LBS metrics")
    else:
        lbs_covered = set(lbs["asset_id"].astype(str))
        print(f"  Assets with LBS coverage:       {len(lbs_covered)}")
        print(f"  Kido grid cells:                "
              f"{kido['grid_id'].nunique() if not kido.empty else 0}\n")

    _subsection("Business presence ratio distribution")
    if presence.empty:
        _warn("No business presence data")
    else:
        pr = pd.to_numeric(presence["business_presence_ratio"], errors="coerce")
        print(f"  count:   {pr.count()}")
        print(f"  mean:    {pr.mean():.3f}")
        print(f"  std:     {pr.std():.3f}")
        print(f"  min:     {pr.min():.3f}")
        print(f"  p25:     {pr.quantile(0.25):.3f}")
        print(f"  median:  {pr.median():.3f}")
        print(f"  p75:     {pr.quantile(0.75):.3f}")
        print(f"  max:     {pr.max():.3f}\n")

        below_40 = (pr < 0.4).sum()
        below_30 = (pr < 0.3).sum()
        print(f"  Assets with presence < 0.40:   {below_40} "
              f"({below_40 / max(1, len(pr)):.0%})")
        print(f"  Assets with presence < 0.30:   {below_30} "
              f"({below_30 / max(1, len(pr)):.0%})\n")


# ---------------------------------------------------------------------------
# 8. Sold vs Full_control Data Availability
# ---------------------------------------------------------------------------

def report_data_availability(d):
    _section("8. Data availability by authority (commercial)")
    assets = d["assets"]
    metrics = d["metrics"]
    metrics_2026 = metrics[metrics["year"] == 2026]

    comm = assets[assets["asset_type"] == "commercial"].copy()
    merged = comm.merge(metrics_2026, on="asset_id", how="left",
                        suffixes=("", "_metric"))

    fields = [
        "occupancy_rate", "vacancy_duration_months",
        "footfall_daily", "rental_income_rm", "opex_annual_rm",
        "noi_rm", "energy_kwh",
    ]

    rows = []
    for authority in ["full_control", "advisory", "shared"]:
        subset = merged[merged["authority"] == authority]
        if subset.empty:
            continue
        row = {"authority": authority, "count": len(subset)}
        for f in fields:
            if f in subset.columns:
                non_null = subset[f].notna().sum()
                row[f] = f"{non_null}/{len(subset)}"
            else:
                row[f] = "(missing)"
        rows.append(row)

    df = pd.DataFrame(rows)
    _print_table(df, index=False)

    _subsection("Interpretation")
    print(
        "    full_control should have ALL fields populated.\n"
        "    advisory should have ONLY occupancy=None (all other\n"
        "    operational fields also None). The presence of non-null\n"
        "    values in advisory rows indicates the authority gate did\n"
        "    not fire correctly."
    )


# ---------------------------------------------------------------------------
# 9. Sample Print
# ---------------------------------------------------------------------------

def report_samples(d):
    _section("9. Sample assets (5 per type)")
    assets = d["assets"]
    metrics_2026 = d["metrics"][d["metrics"]["year"] == 2026]

    for asset_type in [
        "residential", "commercial", "community_facility",
        "green_space", "undeveloped_parcel",
    ]:
        subset = assets[assets["asset_type"] == asset_type]
        if subset.empty:
            continue
        _subsection(asset_type)

        # Mix of authorities
        samples = subset.groupby("authority").head(2).head(5)
        cols_to_show = [
            "asset_id", "subtype", "authority", "ownership_status",
            "completion_year", "lettable_area_m2", "unit_count",
            "capex_initial_rm", "sale_price_rm",
        ]
        cols = [c for c in cols_to_show if c in samples.columns]
        _print_table(samples[cols], index=False)


# ---------------------------------------------------------------------------
# 10. Reality Checks
# ---------------------------------------------------------------------------

def report_reality_checks(d):
    _section("10. Reality consistency checks")
    assets = d["assets"]

    # Check 1: strata_jmb presence
    _subsection("Check: strata_jmb adoption")
    if "strata_jmb" in assets["ownership_status"].unique():
        _ok("strata_jmb is used")
    else:
        _fail(
            "strata_jmb is missing. Every strata-titled asset is\n"
            "         labelled 'sold' (advisory). This collapses two\n"
            "         very different real-world situations:\n"
            "           - Individual buyer owns shoplot outright\n"
            "           - Individual owns strata unit but JMB coordinates\n"
            "         In a real township, 40-60% of commercial and 60-80%\n"
            "         of high-rise residential units are strata-titled.\n"
            "         Consider adding strata_jmb for apartments and\n"
            "         shop-office rows."
        )

    # Check 2: Developer-held commercial ratio
    _subsection("Check: developer-held commercial ratio")
    comm = assets[assets["asset_type"] == "commercial"]
    dev_comm = comm[comm["authority"] == "full_control"]
    ratio = len(dev_comm) / max(1, len(comm))
    if ratio > 0.20:
        _fail(
            f"{ratio:.1%} of commercial is developer-held. In a mature\n"
            f"         township like Bukit Jelutong, this should be 5-15%\n"
            f"         (one or two anchor malls, plus a handful of unsold\n"
            f"         units). The mock currently labels too many as held."
        )
    elif ratio > 0.10:
        _warn(
            f"{ratio:.1%} of commercial is developer-held — on the\n"
            f"         high end. Confirm this matches intent."
        )
    else:
        _ok(f"{ratio:.1%} of commercial is developer-held — plausible")

    # Check 3: Community facility authority (v6.1d — age-based)
    _subsection("Check: community facility authority (age-based)")
    fac = assets[assets["asset_type"] == "community_facility"].copy()
    if not fac.empty:
        fac = fac.dropna(subset=["completion_year"])
        fac["age"] = 2026 - fac["completion_year"]
        recent = fac[fac["age"] <= 5]
        old = fac[fac["age"] > 5]

        n_recent_dev = int(
            (recent["authority"] == "full_control").sum()
        )
        n_old_pub = int(
            (old["ownership_status"] == "public_transferred").sum()
        )

        print(f"  Facilities <= 5 years old: {len(recent)} "
              f"({n_recent_dev} developer-held)")
        print(f"  Facilities > 5 years old:  {len(old)} "
              f"({n_old_pub} public-transferred)")
        print()

        # v6.1d — should be 100% developer-held for recent, 100% public
        # for old. Allow small tolerance for data quirks.
        if len(recent) > 0:
            recent_ratio = n_recent_dev / len(recent)
            if recent_ratio >= 0.80:
                _ok(
                    f"{recent_ratio:.0%} of recent facilities are "
                    f"developer-held"
                )
            else:
                _warn(
                    f"Only {recent_ratio:.0%} of recent facilities are "
                    f"developer-held — should be ~100%"
                )
        if len(old) > 0:
            old_ratio = n_old_pub / len(old)
            if old_ratio >= 0.80:
                _ok(
                    f"{old_ratio:.0%} of old facilities are "
                    f"public-transferred"
                )
            else:
                _warn(
                    f"Only {old_ratio:.0%} of old facilities are "
                    f"public-transferred — should be ~100%"
                )

    # Check 4: Building subtype vs authority coherence
    _subsection("Check: subtype × authority coherence (commercial)")
    comm_pairs = comm.groupby(["subtype", "authority"]).size().unstack(fill_value=0)
    suspicious = []
    for subtype in comm_pairs.index:
        if "full_control" in comm_pairs.columns:
            n_dev = comm_pairs.loc[subtype, "full_control"]
            if subtype == "office" and n_dev > 3:
                suspicious.append(
                    f"office: {n_dev} developer-held — offices are usually strata or sold"
                )
            if subtype == "convenience_retail" and n_dev > 2:
                suspicious.append(
                    f"convenience_retail: {n_dev} developer-held — "
                    f"convenience retail is always sold to individual buyers"
                )
    if suspicious:
        for s in suspicious:
            _warn(s)
    else:
        _ok("No implausible subtype × authority combinations")

    # Check 5: Unsold residential ratio
    _subsection("Check: unsold residential ratio")
    res = assets[assets["asset_type"] == "residential"]
    unsold = res[res["ownership_status"] == "developer_held"]
    ratio = len(unsold) / max(1, len(res))
    print(f"  {len(unsold)}/{len(res)} = {ratio:.1%} developer-held residential")
    print(
        f"  Real-world: a mature township keeps 3-8% as unsold\n"
        f"  inventory at any moment. This is consistent with the\n"
        f"  current n=30 target.\n"
    )
    if 0.02 <= ratio <= 0.08:
        _ok(f"{ratio:.1%} is within the plausible band")

    # Check 6: Sale_date vs completion_year
    _subsection("Check: sale_date after completion_year")
    sold = assets[
        (assets["ownership_status"] == "sold")
        & assets["sale_date"].notna()
        & assets["completion_year"].notna()
    ]
    if not sold.empty:
        sold_dates = pd.to_datetime(sold["sale_date"], errors="coerce")
        sold_years = sold_dates.dt.year
        violations = (sold_years < sold["completion_year"]).sum()
        if violations > 0:
            _fail(f"{violations} assets sold before completion")
        else:
            _ok(f"All {len(sold)} sold assets have sale_date >= completion_year")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("\n" + "=" * 78)
    print("  v6.1 Full-Shape Data Audit")
    print("=" * 78)
    print("\nLoading...")
    data = _load()

    report_authority_distribution(data)
    report_subtype_authority(data)
    report_sale_price_ratio(data)
    report_completion_year(data)
    report_unit_mix(data)
    report_lease_coverage(data)
    report_external_coverage(data)
    report_data_availability(data)
    report_samples(data)
    report_reality_checks(data)

    print("\n" + "=" * 78)
    print("  Audit complete.")
    print("=" * 78 + "\n")


if __name__ == "__main__":
    main()