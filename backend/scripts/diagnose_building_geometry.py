"""Diagnose geometric redundancy in the processed Bukit Jelutong layers.

Run from repo root:
    python backend/scripts/diagnose_buildings_geometry.py

Outputs (per section):
  1. Layer overview
  2. Exact-duplicate polygons (geometry 100% equal)
  3. Containment pairs (one polygon fully inside another)
  4. Amenity <-> building geometric clones
  5. Area distribution by subtype (strip detection)
  6. Micro-building (< 40 m2) audit vs assets.csv
  7. Building ID gaps
  8. Summary and recommended cleanup actions

The script is read-only. It never writes to any file.
"""

import json
import math
import sys
from collections import Counter
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely import wkb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import load_paths


# ------------------------------------------------------------------
# Small helpers
# ------------------------------------------------------------------


def _hdr(title, width=72):
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)


def _sub(title):
    print(f"\n  ── {title} " + "─" * max(0, 66 - len(title)))


def _wkb_key(geom):
    """Deterministic binary key for exact geometry comparison.

    Uses normalize() so that the same physical shape described
    with different ring ordering still hashes equally.
    """
    try:
        return wkb.dumps(geom.normalize(), hex=True)
    except Exception:
        return None


def _area_ratio(inner, outer):
    """Fraction of `outer`'s area covered by `inner`."""
    try:
        ao = float(outer.area)
        if ao <= 0:
            return 0.0
        return float(inner.area) / ao
    except Exception:
        return 0.0


# ------------------------------------------------------------------
# Section 1 — Overview
# ------------------------------------------------------------------


def section_overview(buildings, amenities, assets):
    _hdr("1. Layer overview")

    print(f"  buildings rows:   {len(buildings)}")
    print(f"  amenities rows:   {len(amenities)}")
    print(f"  assets rows:      {len(assets) if not assets.empty else 0}")

    if "subtype" in buildings.columns:
        valid = buildings[buildings["subtype"].notna()]
        print(f"  buildings with subtype:  {len(valid)}")
        print(f"  buildings without:       {len(buildings) - len(valid)}")
        print(f"  subtype distribution:")
        for st, n in valid["subtype"].value_counts().items():
            print(f"    {st:<24} {n}")

    if not assets.empty and "asset_type" in assets.columns:
        print(f"\n  assets by type:")
        for at, n in assets["asset_type"].value_counts().items():
            print(f"    {at:<24} {n}")


# ------------------------------------------------------------------
# Section 2 — Exact duplicates
# ------------------------------------------------------------------


def section_exact_duplicates(buildings):
    _hdr("2. Exact-duplicate building polygons")

    keys = {}
    for idx, row in buildings.iterrows():
        k = _wkb_key(row.geometry)
        if k is None:
            continue
        keys.setdefault(k, []).append(row.get("building_id"))

    dup_groups = {k: v for k, v in keys.items() if len(v) > 1}

    if not dup_groups:
        print("  none")
        return 0

    total_dup = sum(len(g) for g in dup_groups.values())
    print(f"  duplicate groups: {len(dup_groups)}")
    print(f"  duplicated rows:  {total_dup}  (redundant: {total_dup - len(dup_groups)})")

    print(f"\n  sample (first 10 groups):")
    for k, members in list(dup_groups.items())[:10]:
        print(f"    {sorted(members)}")

    return total_dup - len(dup_groups)


# ------------------------------------------------------------------
# Section 3 — Containment
# ------------------------------------------------------------------


def section_containment(buildings):
    _hdr("3. Containment pairs (one polygon inside another)")

    if len(buildings) == 0:
        print("  no buildings to check")
        return 0

    b = buildings[["building_id", "geometry"]].copy()
    b = b.reset_index(drop=True)

    # sjoin with predicate="contains" yields (outer, inner) pairs.
    pairs = gpd.sjoin(
        b.rename(columns={"building_id": "outer_id"}),
        b.rename(columns={"building_id": "inner_id"})
         .reset_index().rename(columns={"index": "inner_idx"}),
        how="inner",
        predicate="contains",
    )

    # Drop self-pairs; note that "contains" is asymmetric so outer != inner
    pairs = pairs[pairs["outer_id"] != pairs["inner_id"]]

    if pairs.empty:
        print("  none")
        return 0

    # Each (outer, inner) pair: report how many sub-buildings live
    # inside each large container.
    per_outer = pairs.groupby("outer_id")["inner_id"].apply(list)
    print(f"  containment groups: {len(per_outer)}")
    print(f"  total pairs:        {len(pairs)}")

    # Compute area of each outer so we can order by "biggest complex"
    b_area = b.set_index("building_id").geometry.area.to_dict()

    print(f"\n  top 10 containers by number of nested buildings:")
    ranked = sorted(
        per_outer.items(),
        key=lambda kv: (-len(kv[1]), -b_area.get(kv[0], 0)),
    )
    for outer_id, inner_ids in ranked[:10]:
        outer_area = b_area.get(outer_id, 0)
        inner_area = sum(b_area.get(x, 0) for x in inner_ids)
        ratio = inner_area / outer_area if outer_area > 0 else 0.0
        print(
            f"    {outer_id} ({outer_area:>9,.1f} m²) "
            f"contains {len(inner_ids)} "
            f"({inner_area:>8,.1f} m² nested, {ratio * 100:>5.1f}%)"
        )
        for iid in inner_ids[:5]:
            print(f"        - {iid}  ({b_area.get(iid, 0):>8,.1f} m²)")
        if len(inner_ids) > 5:
            print(f"        ... and {len(inner_ids) - 5} more")

    return len(pairs)


# ------------------------------------------------------------------
# Section 4 — Amenity <-> building clones
# ------------------------------------------------------------------


def section_amenity_building_clones(buildings, amenities):
    _hdr("4. Amenity <-> building geometric clones")

    if len(buildings) == 0 or len(amenities) == 0:
        print("  one of the layers is empty")
        return 0

    # Exact geometry match
    b_keys = {}
    for idx, row in buildings.iterrows():
        k = _wkb_key(row.geometry)
        if k is None:
            continue
        b_keys.setdefault(k, []).append(row.get("building_id"))

    exact = []
    for idx, row in amenities.iterrows():
        k = _wkb_key(row.geometry)
        if k is None:
            continue
        if k in b_keys:
            exact.append(
                (row.get("amenity_id"), b_keys[k][0], row.get("amenity_type")),
            )

    print(f"  exact-geometry matches: {len(exact)}")
    if exact:
        print(f"  sample (first 15):")
        for aid, bid, atype in exact[:15]:
            print(f"    {aid} ({atype:<20}) == {bid}")

    # Near-match: amenity is fully contained in a building
    # (common when the amenity is a point on a building polygon,
    # or a small polygon inside the building footprint).
    a = amenities[["amenity_id", "geometry"]].copy().reset_index(drop=True)
    b = buildings[["building_id", "geometry"]].copy().reset_index(drop=True)

    contains = gpd.sjoin(
        a.rename(columns={"amenity_id": "amenity_id"}).reset_index(),
        b.reset_index().rename(columns={"index": "bidx"}),
        how="inner",
        predicate="within",
    )
    contains = contains.drop_duplicates(subset=["amenity_id", "bidx"])

    n_within = contains["amenity_id"].nunique() if not contains.empty else 0
    print(f"  amenity polygons fully within a building: {n_within}")
    if not contains.empty:
        print(f"  sample (first 10):")
        for _, r in contains.head(10).iterrows():
            print(
                f"    {r['amenity_id']} within {r['building_id']}"
            )

    return len(exact) + n_within


# ------------------------------------------------------------------
# Section 5 — Area distribution and strip detection
# ------------------------------------------------------------------


def section_area_distribution(buildings):
    _hdr("5. Area distribution and strip-like residential")

    if "subtype" not in buildings.columns:
        print("  no subtype column; skipping")
        return 0

    valid = buildings[buildings["subtype"].notna()].copy()
    if valid.empty:
        print("  no valid subtypes")
        return 0

    valid["_area"] = valid.geometry.area

    _sub("Area percentiles per subtype")
    header = f"    {'subtype':<22} {'n':>4}  {'p25':>10}  {'p50':>10}  {'p75':>10}  {'max':>10}"
    print(header)
    for st in sorted(valid["subtype"].unique()):
        sub = valid[valid["subtype"] == st]
        a = sub["_area"].dropna()
        if a.empty:
            continue
        print(
            f"    {st:<22} {len(sub):>4}  "
            f"{a.quantile(0.25):>10,.1f}  "
            f"{a.quantile(0.50):>10,.1f}  "
            f"{a.quantile(0.75):>10,.1f}  "
            f"{a.max():>10,.1f}"
        )

    _sub("Strip-like residential (likely merged terraces)")
    residential = valid[
        valid["subtype"].isin(
            ["terrace", "semidetached", "detached"]
        )
    ].copy()
    if residential.empty:
        print("    none")
        return 0

    # A strip is a residential polygon whose long:short axis ratio
    # exceeds 3 AND whose area exceeds 2000 m². A single-house
    # footprint is typically under 800 m² with ratio under 2.5.
    strips = []
    for idx, row in residential.iterrows():
        area = row["_area"]
        if area < 2000:
            continue
        try:
            mrr = row.geometry.minimum_rotated_rectangle
            corners = list(mrr.exterior.coords)[:4]
            sides = [
                math.dist(corners[i], corners[i + 1])
                for i in range(len(corners) - 1)
            ]
            if len(sides) < 2:
                continue
            long_side = max(sides)
            short_side = min(sides)
            ratio = long_side / short_side if short_side > 0 else 0
        except Exception:
            continue
        if ratio > 3:
            strips.append((row["building_id"], row["subtype"], area, ratio))

    print(f"    strip-like rows: {len(strips)}")
    for bid, st, area, ratio in sorted(strips, key=lambda x: -x[2])[:15]:
        print(
            f"      {bid}  {st:<14} area={area:>9,.1f}  "
            f"ratio={ratio:>5.2f}"
        )
    if len(strips) > 15:
        print(f"      ... and {len(strips) - 15} more")

    return len(strips)


# ------------------------------------------------------------------
# Section 6 — Micro buildings vs assets
# ------------------------------------------------------------------


def section_micro_buildings(buildings, assets, deadspace_ids):
    _hdr("6. Micro-building audit")

    if "subtype" not in buildings.columns:
        print("  no subtype column; skipping")
        return

    buildings = buildings.copy()
    buildings["_area"] = buildings.geometry.area

    micro = buildings[buildings["_area"] < 40.0]
    print(f"  buildings < 40 m² in processed layer: {len(micro)}")

    if not assets.empty and "asset_id" in assets.columns:
        asset_ids = set(assets["asset_id"].dropna().astype(str))
        micro_in_assets = [
            bid for bid in micro["building_id"].astype(str)
            if bid in asset_ids
        ]
        print(f"  of those, present in assets.csv:      {len(micro_in_assets)}")
        if micro_in_assets:
            print(f"    (this is a bug — MIN_BUILDING_FOOTPRINT_M2 should exclude them)")
            for bid in micro_in_assets[:10]:
                print(f"      {bid}")

    if deadspace_ids:
        micro_in_deadspace = [
            bid for bid in micro["building_id"].astype(str)
            if bid in deadspace_ids
        ]
        print(f"  of those, present in deadspace_2026:  {len(micro_in_deadspace)}")
        if micro_in_deadspace:
            for bid in micro_in_deadspace[:10]:
                print(f"      {bid}")

    # Distribution of sizes below 40 m²
    if not micro.empty:
        _sub("Micro-building size distribution")
        bins = [(0, 10), (10, 20), (20, 30), (30, 40)]
        for lo, hi in bins:
            n = int(((micro["_area"] >= lo) & (micro["_area"] < hi)).sum())
            print(f"    {lo:>2}-{hi:<3} m²   {n}")


# ------------------------------------------------------------------
# Section 7 — ID gaps
# ------------------------------------------------------------------


def section_id_gaps(buildings):
    _hdr("7. Building ID sequence")

    if "building_id" not in buildings.columns:
        print("  no building_id column; skipping")
        return

    ids = [
        s for s in buildings["building_id"].astype(str).tolist()
        if s.startswith("BLD-")
    ]
    try:
        nums = sorted(int(s.split("-")[1]) for s in ids)
    except (IndexError, ValueError):
        print("  could not parse numeric portion of IDs")
        return

    if not nums:
        print("  no BLD- IDs")
        return

    print(f"  total BLD- IDs:     {len(nums)}")
    print(f"  min / max numeric:  {nums[0]} / {nums[-1]}")
    print(f"  expected from min..max:  {nums[-1] - nums[0] + 1}")

    gaps = []
    prev = None
    for n in nums:
        if prev is not None and n > prev + 1:
            gaps.append((prev + 1, n - 1))
        prev = n

    if not gaps:
        print("  no gaps")
    else:
        print(f"  gaps ({len(gaps)}):")
        for lo, hi in gaps[:10]:
            print(f"    {lo} .. {hi}  ({hi - lo + 1} missing)")
        if len(gaps) > 10:
            print(f"    ... and {len(gaps) - 10} more")


# ------------------------------------------------------------------
# Section 8 — Summary
# ------------------------------------------------------------------


def section_summary(exact_dups, containment_pairs, amenity_clones, strips):
    _hdr("8. Summary and recommended next steps")

    print(f"  exact-duplicate building polygons:  {exact_dups}")
    print(f"  containment (outer, inner) pairs:   {containment_pairs}")
    print(f"  amenity <-> building clones:        {amenity_clones}")
    print(f"  strip-like residential rows:        {strips}")

    print("\n  Recommended cleanup, in order:")
    if exact_dups > 0:
        print(
            "    1. Deduplicate exact-geometry buildings (keep lowest "
            "building_id, mark the rest is_asset=False)."
        )
    if containment_pairs > 0:
        print(
            "    2. Resolve containment: keep the finer inner buildings as "
            "assets; mark the outer container is_asset=False unless the "
            "inner set is empty."
        )
    if amenity_clones > 0:
        print(
            "    3. amenity_to_asset_row should require that the "
            "amenity's building_id was found; otherwise refuse to create "
            "an asset (the building already carries the asset)."
        )
    if strips > 0:
        print(
            "    4. Split strip-like residential polygons by typical unit "
            "width (5-7 m for terrace, 10-12 m for semidetached) OR "
            "reclassify as apartment_lowrise."
        )
    print(
        "    5. After cleaning, re-run build_mock_data -> phase1 -> phase3."
    )


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------


def main():
    repo_root = Path(__file__).resolve().parents[2]
    paths = load_paths()
    base = repo_root / paths["base"]

    buildings_path = base / "geometry" / "buildings_bj.geojson"
    amenities_path = base / "geometry" / "amenities_bj.geojson"
    assets_csv = base / "business" / "assets.csv"
    deadspace_json = base / "business" / "deadspace_2026.json"

    print(f"repo_root: {repo_root}")
    print(f"base:      {base}")

    if not buildings_path.exists():
        print(f"\n  FATAL: buildings layer not found at {buildings_path}")
        return
    if not amenities_path.exists():
        print(f"\n  WARNING: amenities layer not found at {amenities_path}")
        amenities = gpd.GeoDataFrame()
    else:
        amenities = gpd.read_file(amenities_path)

    buildings = gpd.read_file(buildings_path)
    assets = pd.read_csv(assets_csv) if assets_csv.exists() else pd.DataFrame()

    deadspace_ids = set()
    if deadspace_json.exists():
        try:
            with open(deadspace_json, encoding="utf-8") as f:
                records = json.load(f)
            deadspace_ids = {r.get("asset_id") for r in records if r.get("asset_id")}
        except Exception as e:
            print(f"  (could not read deadspace: {e})")

    # Reproject to a metric CRS for area computation if not already
    if buildings.crs and buildings.crs.to_epsg() != 32647:
        buildings = buildings.to_crs(32647)
    if not amenities.empty and amenities.crs and amenities.crs.to_epsg() != 32647:
        amenities = amenities.to_crs(32647)

    section_overview(buildings, amenities, assets)
    exact_dups = section_exact_duplicates(buildings)
    containment_pairs = section_containment(buildings)
    amenity_clones = section_amenity_building_clones(buildings, amenities)
    strips = section_area_distribution(buildings)
    section_micro_buildings(buildings, assets, deadspace_ids)
    section_id_gaps(buildings)
    section_summary(exact_dups, containment_pairs, amenity_clones, strips)

    print("\n" + "=" * 72)
    print("  Diagnosis complete.")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    main()