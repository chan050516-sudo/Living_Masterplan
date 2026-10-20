"""Geometry validation report for the OSM pipeline outputs.

Run after osm_pipeline.py. Prints a data-quality report covering:
  - Per-layer geometry validity, bounds plausibility, and CRS.
  - Field-level completeness (null counts, value distributions).
  - Enum compliance against the current schemas.
  - Topological checks (duplicate IDs, isolated nodes, components).
  - Cross-layer referential integrity (buildings↔parcels, etc).

The output is designed to be pasted verbatim into a conversation so
that a reviewer can assess data quality without seeing the raw files.

Exits with code 1 if any HARD check fails.
"""

import sys
import math
import json
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd

# ----------------------------------------------------------------
# Config
# ----------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GEOM_DIR = REPO_ROOT / "bukit_jelutong" / "processed" / "geometry"

COMPUTE_CRS = "EPSG:32647"
STORAGE_CRS = "EPSG:4326"

LAYERS = ["parcels", "buildings", "green_blue", "network_edges", "amenities"]

# Malaysia bounding box (lat/lon) for plausibility.
MY_BOUNDS = (99.0, 0.5, 120.0, 8.0)   # (min_lon, min_lat, max_lon, max_lat)

# Recognised value sets. Mirrors the current schemas plus what the
# updated pipeline emits.
ALLOWED_LAND_USE = {
    "residential", "commercial", "community_facility", "mixed_use",
    "green_space", "undeveloped", "infrastructure", "unknown",
}
ALLOWED_BUILDING_TYPE = {
    "residential", "commercial", "community_facility",
    "industrial", "mixed_use", "unknown",
}
ALLOWED_GREEN_TYPE = {
    "park", "pocket_park", "green_corridor", "canopy",
    "water_body", "drainage", "public_space",
}
ALLOWED_AMENITY_TYPE = {
    "transit_station", "bus_stop", "school", "clinic", "hospital",
    "place_of_worship", "community_centre", "library",
    "arts_centre", "theatre", "cinema", "marketplace",
    "fuel", "parking", "other",
}
ALLOWED_ACCESS_TYPE = {"public", "private", "restricted"}


# ----------------------------------------------------------------
# Reporting primitives
# ----------------------------------------------------------------

_FAILURES = []
_WARNINGS = []


def _section(title, width=72):
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def _sub(title, width=72):
    print()
    print("-" * width)
    print(f"  {title}")
    print("-" * width)


def _ok(label, detail=""):
    print(f"  [OK]   {label:<50s} {detail}")


def _warn(label, detail=""):
    print(f"  [WARN] {label:<50s} {detail}")
    _WARNINGS.append(f"{label}: {detail}")


def _fail(label, detail=""):
    print(f"  [FAIL] {label:<50s} {detail}")
    _FAILURES.append(f"{label}: {detail}")


def _info(label, detail=""):
    print(f"         {label:<50s} {detail}")


# ----------------------------------------------------------------
# Loaders
# ----------------------------------------------------------------

def load_layer(geom_dir, name):
    path = geom_dir / f"{name}_bj.geojson"
    if not path.exists():
        return None
    try:
        gdf = gpd.read_file(path)
    except Exception as e:
        _fail(f"Load {name}.geojson", str(e))
        return None
    if gdf.crs is None:
        gdf = gdf.set_crs(STORAGE_CRS)
    return gdf


# ----------------------------------------------------------------
# Common per-layer checks
# ----------------------------------------------------------------

def report_geometry(name, gdf):
    _sub(f"{name}: geometry")
    n = len(gdf)
    _info("features", n)
    if n == 0:
        _fail(f"{name}: empty layer")
        return

    # Geometry types.
    geom_types = gdf.geometry.type.value_counts().to_dict()
    _info("geometry types", json.dumps(geom_types))

    # Empty geometry.
    n_empty = int(gdf.geometry.is_empty.sum())
    if n_empty > 0:
        _warn(f"{name}: empty geometries", f"{n_empty}/{n}")
    else:
        _ok(f"{name}: no empty geometries")

    # Validity.
    n_invalid = int((~gdf.geometry.is_valid).sum())
    if n_invalid > 0:
        _warn(f"{name}: invalid geometries", f"{n_invalid}/{n}")
    else:
        _ok(f"{name}: all geometries valid")

    # Bounds plausibility (in EPSG:4326).
    g4326 = gdf.to_crs(STORAGE_CRS)
    minx, miny, maxx, maxy = g4326.total_bounds
    _info("bounds (4326)", f"lon [{minx:.4f}, {maxx:.4f}]  lat [{miny:.4f}, {maxy:.4f}]")
    in_my = (
        MY_BOUNDS[0] <= minx <= MY_BOUNDS[2] and
        MY_BOUNDS[1] <= miny <= MY_BOUNDS[3] and
        MY_BOUNDS[0] <= maxx <= MY_BOUNDS[2] and
        MY_BOUNDS[1] <= maxy <= MY_BOUNDS[3]
    )
    if in_my:
        _ok(f"{name}: bounds within Malaysia")
    else:
        _warn(f"{name}: bounds outside Malaysia", f"got ({minx},{miny},{maxx},{maxy})")

    # Span size.
    span_km = math.hypot(maxx - minx, maxy - miny) * 111.0  # rough
    _info("study area diagonal", f"{span_km:.2f} km")


def report_fields(name, gdf, fields):
    _sub(f"{name}: fields")
    n = len(gdf)
    for f in fields:
        if f not in gdf.columns:
            _warn(f"{name}.{f}", "column missing")
            continue
        nn = int(gdf[f].notna().sum())
        pct = 100.0 * nn / n if n else 0.0
        _info(f"{name}.{f}", f"{nn}/{n} ({pct:.1f}% non-null)")


def report_numeric(name, gdf, cols):
    _sub(f"{name}: numeric distributions")
    for c in cols:
        if c not in gdf.columns:
            continue
        vals = pd.to_numeric(gdf[c], errors="coerce").dropna()
        if len(vals) == 0:
            _info(c, "(all null)")
            continue
        stats = {
            "n": int(len(vals)),
            "min": float(vals.min()),
            "p25": float(vals.quantile(0.25)),
            "median": float(vals.median()),
            "p75": float(vals.quantile(0.75)),
            "p90": float(vals.quantile(0.90)),
            "max": float(vals.max()),
            "mean": float(vals.mean()),
        }
        line = (
            f"n={stats['n']:>5d}  "
            f"min={stats['min']:.2f}  "
            f"p25={stats['p25']:.2f}  "
            f"med={stats['median']:.2f}  "
            f"p75={stats['p75']:.2f}  "
            f"p90={stats['p90']:.2f}  "
            f"max={stats['max']:.2f}  "
            f"mean={stats['mean']:.2f}"
        )
        _info(c, line)


def report_categorical(name, gdf, col, top=15):
    if col not in gdf.columns:
        return
    vc = gdf[col].astype(str).value_counts().head(top)
    _info(f"{col} (top {top})", "")
    for k, v in vc.items():
        print(f"           {k:<40s} {v:>6d}")


def report_enum(name, gdf, col, allowed):
    if col not in gdf.columns:
        return
    actual = set(gdf[col].dropna().astype(str).unique())
    bad = actual - allowed
    if bad:
        _warn(f"{name}.{col}: values outside schema",
              f"{sorted(bad)}")
    else:
        _ok(f"{name}.{col}: all values within schema")


def report_duplicate_ids(name, gdf, id_col):
    if id_col not in gdf.columns:
        return
    dups = gdf[id_col].duplicated().sum()
    if dups > 0:
        _fail(f"{name}.{id_col}: duplicate ids", f"{int(dups)}")
    else:
        _ok(f"{name}.{id_col}: unique")


# ----------------------------------------------------------------
# Buildings
# ----------------------------------------------------------------

def report_buildings(gdf):
    _section("BUILDINGS")
    report_geometry("buildings", gdf)
    report_fields("buildings", gdf, [
        "building_id", "parcel_id", "asset_id", "building_type",
        "building_raw", "floors", "footprint_m2", "gfa_m2",
        "geometry_source",
    ])
    report_duplicate_ids("buildings", gdf, "building_id")

    report_categorical("buildings", gdf, "building_type", top=10)
    report_categorical("buildings", gdf, "geometry_source", top=5)
    report_enum("buildings", gdf, "building_type", ALLOWED_BUILDING_TYPE)

    report_numeric("buildings", gdf, ["footprint_m2", "gfa_m2", "floors"])

    # Floors distribution
    if "floors" in gdf.columns:
        floors = pd.to_numeric(gdf["floors"], errors="coerce").dropna()
        if len(floors) > 0:
            _info("floors present", f"{len(floors)}/{len(gdf)} ({100*len(floors)/len(gdf):.1f}%)")
            _info("floors unique values", sorted(floors.unique().tolist())[:10])

    # GFA consistency
    if "footprint_m2" in gdf.columns and "gfa_m2" in gdf.columns:
        fp = pd.to_numeric(gdf["footprint_m2"], errors="coerce")
        gfa = pd.to_numeric(gdf["gfa_m2"], errors="coerce")
        fl = pd.to_numeric(gdf.get("floors"), errors="coerce").fillna(1)
        expected = fp * fl
        # Where floors is null, gfa should equal footprint.
        diff = (gfa - expected).abs()
        n_bad = int((diff > 1.0).sum())
        if n_bad > 0:
            _warn("buildings: gfa != footprint * floors", f"{n_bad}/{len(gdf)}")
        else:
            _ok("buildings: gfa = footprint * floors")

    # Unlinked asset_id
    if "asset_id" in gdf.columns:
        n_unlinked = gdf["asset_id"].astype(str).str.startswith("unlinked-").sum()
        _info("asset_id unlinked", f"{n_unlinked}/{len(gdf)}")

    # Unassigned parcel
    if "parcel_id" in gdf.columns:
        n_unassigned = (gdf["parcel_id"] == "P-UNASSIGNED").sum()
        if n_unassigned > 0:
            _warn("buildings: parcel_id = P-UNASSIGNED", f"{n_unassigned}/{len(gdf)}")
        else:
            _ok("buildings: all buildings assigned to a parcel")


# ----------------------------------------------------------------
# Parcels
# ----------------------------------------------------------------

def report_parcels(gdf):
    _section("PARCELS")
    report_geometry("parcels", gdf)
    report_fields("parcels", gdf, [
        "parcel_id", "asset_id", "land_use", "area_m2",
        "geometry_source", "geometry_confidence",
    ])
    report_duplicate_ids("parcels", gdf, "parcel_id")

    report_categorical("parcels", gdf, "land_use", top=10)
    report_enum("parcels", gdf, "land_use", ALLOWED_LAND_USE)

    report_numeric("parcels", gdf, ["area_m2"])

    # Area vs geometry.area consistency.
    if "area_m2" in gdf.columns:
        gdf_proj = gdf.to_crs(COMPUTE_CRS)
        computed = gdf_proj.geometry.area
        reported = pd.to_numeric(gdf["area_m2"], errors="coerce")
        rel_err = ((reported - computed).abs() / computed.replace(0, np.nan))
        n_bad = int((rel_err > 0.01).sum())
        if n_bad > 0:
            _warn("parcels: area_m2 != geometry.area", f"{n_bad}/{len(gdf)}")
        else:
            _ok("parcels: area_m2 matches geometry")

    # Sanity check on parcel scale.
    if "area_m2" in gdf.columns:
        areas = pd.to_numeric(gdf["area_m2"], errors="coerce").dropna()
        n_huge = int((areas > 50000).sum())   # > 5 ha
        n_tiny = int((areas < 100).sum())     # < 100 m²
        if n_huge > 0:
            _warn("parcels: suspiciously large (> 5 ha)", f"{n_huge}/{len(areas)}")
        if n_tiny > 0:
            _warn("parcels: suspiciously small (< 100 m2)", f"{n_tiny}/{len(areas)}")


# ----------------------------------------------------------------
# Green / Blue
# ----------------------------------------------------------------

def report_green_blue(gdf):
    _section("GREEN / BLUE")
    report_geometry("green_blue", gdf)
    report_fields("green_blue", gdf, [
        "green_id", "asset_id", "green_type", "green_type_raw",
        "area_m2", "canopy_m2", "geometry_source",
    ])
    report_duplicate_ids("green_blue", gdf, "green_id")

    report_categorical("green_blue", gdf, "green_type", top=10)
    report_enum("green_blue", gdf, "green_type", ALLOWED_GREEN_TYPE)

    report_numeric("green_blue", gdf, ["area_m2", "canopy_m2"])

    if "canopy_m2" in gdf.columns:
        n_canopy = int(gdf["canopy_m2"].notna().sum())
        _info("canopy_m2 present", f"{n_canopy}/{len(gdf)}")


# ----------------------------------------------------------------
# Network
# ----------------------------------------------------------------

def report_network(gdf):
    _section("NETWORK EDGES")
    report_geometry("network_edges", gdf)
    report_fields("network_edges", gdf, [
        "edge_id", "edge_type", "highway_raw", "walk_ok", "drive_ok",
        "from_node", "to_node", "length_m", "walk_speed_kmh",
        "access_type", "canopy_coverage_ratio",
    ])
    report_duplicate_ids("network_edges", gdf, "edge_id")

    report_categorical("network_edges", gdf, "edge_type", top=20)
    report_categorical("network_edges", gdf, "access_type", top=5)

    report_numeric("network_edges", gdf, ["length_m", "canopy_coverage_ratio"])

    # walk_ok / drive_ok coverage.
    if "walk_ok" in gdf.columns:
        n_walk = int(gdf["walk_ok"].fillna(False).sum())
        _info("walk_ok True", f"{n_walk}/{len(gdf)}")
    if "drive_ok" in gdf.columns:
        n_drive = int(gdf["drive_ok"].fillna(False).sum())
        _info("drive_ok True", f"{n_drive}/{len(gdf)}")

    # Self-loops.
    if "from_node" in gdf.columns and "to_node" in gdf.columns:
        n_selfloop = int((gdf["from_node"] == gdf["to_node"]).sum())
        if n_selfloop > 0:
            _warn("network_edges: self-loops", f"{n_selfloop}")

    # Length vs geometry consistency.
    if "length_m" in gdf.columns:
        gdf_proj = gdf.to_crs(COMPUTE_CRS)
        computed = gdf_proj.geometry.length
        reported = pd.to_numeric(gdf["length_m"], errors="coerce")
        rel_err = ((reported - computed).abs() / computed.replace(0, np.nan))
        n_bad = int((rel_err > 0.02).sum())
        if n_bad > 0:
            _warn("network_edges: length_m != geometry.length", f"{n_bad}/{len(gdf)}")
        else:
            _ok("network_edges: length_m matches geometry")

    # Connectivity for each mode.
    for mode, flag in (("walking", "walk_ok"), ("driving", "drive_ok")):
        if flag not in gdf.columns:
            continue
        sub = gdf[gdf[flag].fillna(False)]
        if len(sub) == 0:
            _warn(f"network_edges: {mode} subgraph empty")
            continue
        G = nx.Graph()
        for _, row in sub.iterrows():
            u, v = row["from_node"], row["to_node"]
            if pd.isna(u) or pd.isna(v):
                continue
            G.add_edge(u, v)
        comps = list(nx.connected_components(G))
        sizes = sorted((len(c) for c in comps), reverse=True)[:5]
        _info(f"{mode}: nodes", f"{G.number_of_nodes()}")
        _info(f"{mode}: edges", f"{G.number_of_edges()}")
        _info(f"{mode}: components", f"{len(comps)}  top sizes={sizes}")
        if len(comps) > 1 and sizes[0] < 0.8 * G.number_of_nodes():
            _warn(f"network_edges: {mode} fragmented",
                  f"largest component = {sizes[0]}/{G.number_of_nodes()}")

    # Canopy coverage distribution.
    if "canopy_coverage_ratio" in gdf.columns:
        cc = pd.to_numeric(gdf["canopy_coverage_ratio"], errors="coerce").dropna()
        n_nonzero = int((cc > 0).sum())
        _info("edges with canopy > 0", f"{n_nonzero}/{len(cc)}")
        if n_nonzero == 0:
            _warn("network_edges: no canopy coverage anywhere")


# ----------------------------------------------------------------
# Amenities
# ----------------------------------------------------------------

def report_amenities(gdf):
    _section("AMENITIES")
    report_geometry("amenities", gdf)
    report_fields("amenities", gdf, [
        "amenity_id", "amenity_type", "amenity_type_raw", "capacity",
    ])
    report_duplicate_ids("amenities", gdf, "amenity_id")

    report_categorical("amenities", gdf, "amenity_type", top=15)
    report_categorical("amenities", gdf, "amenity_type_raw", top=15)
    report_enum("amenities", gdf, "amenity_type", ALLOWED_AMENITY_TYPE)

    # amenity_type == other ratio.
    if "amenity_type" in gdf.columns:
        n_other = int((gdf["amenity_type"] == "other").sum())
        pct = 100.0 * n_other / len(gdf) if len(gdf) else 0
        if pct > 50:
            _warn("amenities: >50% classified as other", f"{n_other}/{len(gdf)} ({pct:.0f}%)")


# ----------------------------------------------------------------
# Cross-layer checks
# ----------------------------------------------------------------

def report_cross_layer(layers):
    _section("CROSS-LAYER")

    buildings = layers.get("buildings")
    parcels = layers.get("parcels")
    green = layers.get("green_blue")
    network = layers.get("network_edges")

    # Buildings → parcels referential integrity.
    if buildings is not None and parcels is not None:
        if "parcel_id" in buildings.columns and "parcel_id" in parcels.columns:
            parcel_ids = set(parcels["parcel_id"].astype(str))
            building_parcels = buildings["parcel_id"].astype(str)
            missing = set(building_parcels) - parcel_ids - {"P-UNASSIGNED"}
            if missing:
                _warn("buildings → parcels: missing references",
                      f"{len(missing)} unmatched, e.g. {sorted(list(missing))[:5]}")
            else:
                _ok("buildings → parcels: all references resolve")

    # Buildings inside parcels spatially.
    if buildings is not None and parcels is not None:
        b = buildings.to_crs(COMPUTE_CRS)
        p = parcels.to_crs(COMPUTE_CRS)
        inside = gpd.sjoin(
            b[["geometry"]], p[["geometry"]],
            how="left", predicate="within",
        )
        n_outside = int(inside["index_right"].isna().sum())
        if n_outside > 0:
            _warn("buildings spatially outside parcels",
                  f"{n_outside}/{len(b)}")
        else:
            _ok("buildings spatially inside parcels")

    # Buildings × green overlap.
    if buildings is not None and green is not None:
        b = buildings.to_crs(COMPUTE_CRS)
        g = green.to_crs(COMPUTE_CRS)
        inter = gpd.sjoin(
            b[["geometry"]], g[["geometry"]],
            how="inner", predicate="intersects",
        )
        if len(inter) > 0:
            _info("buildings intersecting green areas", f"{len(inter)}")
        else:
            _ok("no building/green overlaps")

    # Network nodes vs buildings (rough proximity).
    if network is not None and buildings is not None:
        net = network.to_crs(COMPUTE_CRS)
        b = buildings.to_crs(COMPUTE_CRS)
        # How many buildings are within 20 m of some edge?
        net_union = net.geometry.union_all().buffer(20.0)
        b_pts = b.geometry.representative_point()
        near = b_pts.within(net_union).sum()
        pct = 100.0 * near / len(b) if len(b) else 0
        _info("buildings within 20 m of a network edge",
              f"{near}/{len(b)} ({pct:.0f}%)")
        if pct < 80:
            _warn("buildings poorly served by network", f"only {pct:.0f}% within 20 m")


# ----------------------------------------------------------------
# Main
# ----------------------------------------------------------------

def find_geom_dir():
    if len(sys.argv) > 1:
        p = Path(sys.argv[1])
        if p.exists():
            return p
    return DEFAULT_GEOM_DIR


def main():
    geom_dir = find_geom_dir()
    print(f"Geometry directory: {geom_dir}")
    if not geom_dir.exists():
        print("ERROR: directory does not exist.")
        sys.exit(1)

    layers = {}
    for name in LAYERS:
        gdf = load_layer(geom_dir, name)
        if gdf is None:
            print(f"[SKIP] {name}.geojson not found")
            continue
        layers[name] = gdf

    # Per-layer reports.
    if "buildings" in layers:
        report_buildings(layers["buildings"])
    if "parcels" in layers:
        report_parcels(layers["parcels"])
    if "green_blue" in layers:
        report_green_blue(layers["green_blue"])
    if "network_edges" in layers:
        report_network(layers["network_edges"])
    if "amenities" in layers:
        report_amenities(layers["amenities"])

    # Cross-layer.
    report_cross_layer(layers)

    # Summary.
    _section("SUMMARY")
    print(f"  Failures: {len(_FAILURES)}")
    for f in _FAILURES:
        print(f"    - {f}")
    print(f"  Warnings: {len(_WARNINGS)}")
    for w in _WARNINGS:
        print(f"    - {w}")

    if _FAILURES:
        sys.exit(1)


if __name__ == "__main__":
    main()