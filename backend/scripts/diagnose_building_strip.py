"""Distinguish true geometric overlap from boundary-touching.

Run from repo root:
    python backend/scripts/diagnose_asset_overlap_breakdown.py

For every asset pair that `intersects`, compute the intersection area
ratio. Then bucket:

  TRUE_OVERLAP     ratio > 0.10  — one asset significantly covers another
  PARTIAL          ratio 0.01-0.10 — geometric drift
  BOUNDARY         ratio < 0.01  — shared boundary, benign

Also resolves the strip occupancy analysis (fixes the path bug in the
previous script by reading paths.yml correctly).
"""

import math
import sys
from pathlib import Path
from collections import Counter

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import load_paths


def _hdr(t):
    print("\n" + "=" * 72)
    print(f"  {t}")
    print("=" * 72)


def _build_assets_geo(assets_df, buildings, amenities, green_blue, parcels):
    b_idx = {str(r["building_id"]): r.geometry
             for _, r in buildings.iterrows()} if not buildings.empty else {}
    a_idx = {str(r["amenity_id"]): r.geometry
             for _, r in amenities.iterrows()} if not amenities.empty else {}
    g_idx = {str(r["green_id"]): r.geometry
             for _, r in green_blue.iterrows()} if not green_blue.empty else {}
    p_idx = {str(r["parcel_id"]): r.geometry
             for _, r in parcels.iterrows()} if not parcels.empty else {}

    recs = []
    for _, a in assets_df.iterrows():
        aid = str(a["asset_id"])
        geom = None
        if aid.startswith("A-"):
            geom = a_idx.get(aid)
        elif aid.startswith("BLD-"):
            geom = b_idx.get(aid)
        elif aid.startswith("G-"):
            geom = g_idx.get(aid)
        elif aid.startswith("P-"):
            pid = str(a.get("parcel_id") or aid)
            geom = p_idx.get(pid) or p_idx.get(aid)
        recs.append({
            "asset_id": aid,
            "asset_type": a.get("asset_type"),
            "subtype": a.get("subtype"),
            "geometry": geom,
        })
    return gpd.GeoDataFrame(recs, geometry="geometry", crs=buildings.crs)


def _bucket(ratio):
    if ratio > 0.10:
        return "TRUE_OVERLAP"
    if ratio > 0.01:
        return "PARTIAL"
    return "BOUNDARY"


def section_breakdown(assets_geo):
    _hdr("1. Overlap breakdown: TRUE_OVERLAP / PARTIAL / BOUNDARY")

    valid = assets_geo[assets_geo["geometry"].notna()].reset_index(drop=True)

    left = valid[["asset_id", "asset_type", "geometry"]].copy()
    right = valid[["asset_id", "asset_type", "geometry"]].copy().rename(
        columns={"asset_id": "other_id", "asset_type": "other_type"},
    )

    pairs = gpd.sjoin(
        left.reset_index(drop=True),
        right.reset_index(drop=True),
        how="inner",
        predicate="intersects",
    )
    pairs = pairs[pairs["asset_id"] < pairs["other_id"]]

    # Intersection area per pair
    geom_map = dict(zip(valid["asset_id"], valid["geometry"]))
    area_map = {aid: g.area for aid, g in geom_map.items()}

    rows = []
    for _, r in pairs.iterrows():
        a, b = r["asset_id"], r["other_id"]
        try:
            inter = geom_map[a].intersection(geom_map[b]).area
        except Exception:
            inter = 0.0
        denom = min(area_map[a], area_map[b])
        ratio = inter / denom if denom > 0 else 0.0
        rows.append({
            "a": a, "a_type": r["asset_type"],
            "b": b, "b_type": r["other_type"],
            "inter_area": inter,
            "ratio": ratio,
            "bucket": _bucket(ratio),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        print("  no overlapping pairs")
        return df

    print(f"  total pairs: {len(df)}")
    for bucket in ("TRUE_OVERLAP", "PARTIAL", "BOUNDARY"):
        n = (df["bucket"] == bucket).sum()
        print(f"    {bucket:<14} {n}")

    _hdr("2. TRUE_OVERLAP pairs by type combination")
    t = df[df["bucket"] == "TRUE_OVERLAP"].copy()
    if t.empty:
        print("  none")
    else:
        combos = Counter(
            tuple(sorted([r["a_type"], r["b_type"]]))
            for _, r in t.iterrows()
        )
        for c, n in combos.most_common():
            print(f"  {c[0]:<22} x {c[1]:<22} {n}")

        print(f"\n  top 30 TRUE_OVERLAP pairs by ratio:")
        for _, r in t.sort_values("ratio", ascending=False).head(30).iterrows():
            print(
                f"    ratio={r['ratio']:>5.2f}  "
                f"{r['a']:<14} ({r['a_type']:<20}) <-> "
                f"{r['b']:<14} ({r['b_type']:<20})  "
                f"inter={r['inter_area']:>9,.1f} m²"
            )
    return df


def section_amenity_double_count(assets_df, assets_geo):
    _hdr("3. Amenity assets that are ALSO present as building assets")

    # Find amenity assets whose building_id column was populated but
    # the same building id ALSO exists as an asset row.
    if "building_id" not in assets_df.columns:
        print("  no building_id column in assets.csv")
        return

    a_assets = assets_df[assets_df["asset_id"].astype(str).str.startswith("A-")]
    b_assets = assets_df[assets_df["asset_id"].astype(str).str.startswith("BLD-")]
    b_ids = set(b_assets["asset_id"].astype(str))

    dup = a_assets[a_assets["building_id"].notna() &
                   a_assets["building_id"].astype(str).isin(b_ids)]

    print(f"  amenity assets with building_id present: "
          f"{a_assets['building_id'].notna().sum()}")
    print(f"  amenity assets whose building_id is ALSO an asset: {len(dup)}")

    if not dup.empty:
        print(f"\n  the double-counted pairs:")
        for _, r in dup.iterrows():
            print(
                f"    {r['asset_id']:<10} (building_id={r['building_id']})  "
                f"subtype={r.get('subtype')}"
            )

    # Also check: amenity assets with NULL building_id that still
    # overlap a building asset geometrically. That means the sjoin
    # in process_amenities_geometry FAILED to link them.
    a_null = a_assets[a_assets["building_id"].isna()]
    print(f"\n  amenity assets with NULL building_id: {len(a_null)}")

    if not a_null.empty and not b_assets.empty:
        # Spatial test: for each null-building amenity, is it within
        # a building asset?
        a_geo = assets_geo[
            assets_geo["asset_id"].isin(a_null["asset_id"].astype(str))
        ].dropna(subset=["geometry"])
        b_geo = assets_geo[
            assets_geo["asset_id"].isin(b_assets["asset_id"].astype(str))
        ].dropna(subset=["geometry"])

        if not a_geo.empty and not b_geo.empty:
            inside = gpd.sjoin(
                a_geo[["asset_id", "geometry"]].reset_index(drop=True),
                b_geo[["asset_id", "geometry"]]
                    .reset_index(drop=True)
                    .rename(columns={"asset_id": "bid"}),
                how="inner",
                predicate="intersects",
            )
            inside = inside.drop_duplicates(subset=["asset_id", "bid"])
            print(f"  of those NULL-building amenities, "
                  f"{inside['asset_id'].nunique()} actually intersect a "
                  f"building asset (sjoin failure)")
            for _, r in inside.head(15).iterrows():
                print(f"    {r['asset_id']} intersects {r['bid']}")


def section_strip_occupancy(assets_geo, buildings, base):
    _hdr("4. Strip residential — occupancy and hidden dead units")

    b = buildings.copy()
    b["_area"] = b.geometry.area

    strips = []
    for _, row in b.iterrows():
        if row.get("subtype") not in ("terrace", "semidetached", "detached"):
            continue
        if row["_area"] < 2000:
            continue
        try:
            mrr = row.geometry.minimum_rotated_rectangle
            corners = list(mrr.exterior.coords)[:4]
            sides = [math.dist(corners[i], corners[i + 1])
                     for i in range(len(corners) - 1)]
            ratio = max(sides) / min(sides) if min(sides) > 0 else 0
        except Exception:
            continue
        if ratio > 3:
            strips.append({
                "building_id": row["building_id"],
                "subtype": row["subtype"],
                "area_m2": row["_area"],
            })

    if not strips:
        print("  no strip-like residential")
        return

    strip_df = pd.DataFrame(strips)
    unit_fp = {"terrace": 140.0, "semidetached": 220.0, "detached": 400.0}
    strip_df["est_units"] = strip_df.apply(
        lambda r: max(1, round(r["area_m2"] / unit_fp.get(r["subtype"], 150))),
        axis=1,
    )

    print(f"  strips:                  {len(strip_df)}")
    print(f"  total strip area:        {strip_df['area_m2'].sum():,.0f} m²")
    print(f"  estimated real units:    {int(strip_df['est_units'].sum())}")

    metrics_path = base / "business" / "asset_metrics_enriched.csv"
    if not metrics_path.exists() or metrics_path.stat().st_size == 0:
        print(f"\n  asset_metrics_enriched.csv not found at {metrics_path}")
        print("  run backend/scripts/run_phase1.py first to generate it")
        return

    metrics = pd.read_csv(metrics_path)
    if "year" in metrics.columns:
        metrics = metrics[metrics["year"] == 2026]

    occ_map = dict(zip(
        metrics["asset_id"].astype(str),
        metrics["occupancy_rate"],
    ))
    strip_df["occupancy"] = strip_df["building_id"].astype(str).map(occ_map)
    valid = strip_df[strip_df["occupancy"].notna()].copy()

    if valid.empty:
        print("  no occupancy data for strip assets")
        return

    print(f"\n  occupancy distribution across {len(valid)} strips:")
    bins = [(0.0, 0.05), (0.05, 0.30), (0.30, 0.50),
            (0.50, 0.75), (0.75, 0.85), (0.85, 1.01)]
    for lo, hi in bins:
        n = int(((valid["occupancy"] >= lo) & (valid["occupancy"] < hi)).sum())
        pct = n / len(valid) * 100
        print(f"    occ [{lo:.2f}, {hi:.2f}): {n:>3} ({pct:>5.1f}%)")

    valid["dead_units"] = valid.apply(
        lambda r: max(0, int(r["est_units"]) - int(round(r["est_units"] * r["occupancy"]))),
        axis=1,
    )
    total_dead = int(valid["dead_units"].sum())
    total_units = int(valid["est_units"].sum())

    print(f"\n  hidden dead units inside strips:")
    print(f"    total units: {total_units}")
    print(f"    dead units:  {total_dead}")
    print(f"    dead rate:   {total_dead / total_units * 100:.1f}%")

    print(f"\n  top 15 strips by hidden dead units:")
    for _, r in valid.sort_values("dead_units", ascending=False).head(15).iterrows():
        print(
            f"    {r['building_id']:<10} {r['subtype']:<14} "
            f"area={r['area_m2']:>8,.0f}  units≈{int(r['est_units']):>2}  "
            f"occ={r['occupancy']:.2f}  dead={int(r['dead_units'])}"
        )


def main():
    repo_root = Path(__file__).resolve().parents[2]
    paths = load_paths()
    base = repo_root / paths["base"]

    assets_df = pd.read_csv(base / "business" / "assets.csv")
    buildings = gpd.read_file(base / "geometry" / "buildings_bj.geojson").to_crs(32647)

    amen_path = base / "geometry" / "amenities_bj.geojson"
    green_path = base / "geometry" / "green_blue_bj.geojson"
    parc_path = base / "geometry" / "parcels_bj.geojson"

    amenities = (gpd.read_file(amen_path).to_crs(32647)
                 if amen_path.exists() else gpd.GeoDataFrame())
    green_blue = (gpd.read_file(green_path).to_crs(32647)
                  if green_path.exists() else gpd.GeoDataFrame())
    parcels = (gpd.read_file(parc_path).to_crs(32647)
               if parc_path.exists() else gpd.GeoDataFrame())

    assets_geo = _build_assets_geo(
        assets_df, buildings, amenities, green_blue, parcels,
    )
    print(f"assets with geometry: {assets_geo['geometry'].notna().sum()}")

    section_breakdown(assets_geo)
    section_amenity_double_count(assets_df, assets_geo)
    section_strip_occupancy(assets_geo, buildings, base)


if __name__ == "__main__":
    main()