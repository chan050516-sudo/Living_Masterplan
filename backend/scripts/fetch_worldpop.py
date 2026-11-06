"""Download WorldPop Malaysia 2026 and aggregate population to 400m cells.

The GeoTIFF is streamed to a temporary directory and removed after processing.
The derived CSV is stored under external_data_mock as an input to ingestion;
its rows are real WorldPop estimates, not synthetic mock records.

Run from the repository root:
    python backend/scripts/fetch_worldpop.py
"""

from __future__ import annotations

import argparse
import tempfile
import urllib.request
from pathlib import Path

import geopandas as gpd
import pandas as pd
import rasterio
from rasterio.mask import mask
from shapely.geometry import box, mapping

from generate_external_data_mocks import (
    BASE,
    GRID_CRS,
    GRID_SIZE_M,
    PATHS,
    _asset_geometry_points,
    _read_layer,
)

DEFAULT_URL = (
    "https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/"
    "2026/MYS/v1/100m/constrained/mys_pop_2026_CN_100m_R2025A_v1.tif"
)
WORLDPOP_SOURCE = "worldpop_global2"


def _download(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "LivingMasterplan-data-pipeline/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as output:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)


def _grid_geometry(grid_id: str):
    ix, iy = [int(part) for part in grid_id.split("-")[1:]]
    return box(ix * GRID_SIZE_M, iy * GRID_SIZE_M,
               (ix + 1) * GRID_SIZE_M, (iy + 1) * GRID_SIZE_M)


def _residential_capacity_by_grid() -> dict[str, float]:
    assets = pd.read_csv(BASE / PATHS["business"]["assets"])
    buildings = _read_layer(PATHS["geometry"]["buildings"])
    parcels = _read_layer(PATHS["geometry"]["parcels"])
    points, _ = _asset_geometry_points(assets, buildings, parcels)
    residential = assets[assets["asset_type"].eq("residential")]
    result: dict[str, float] = {}
    for _, row in residential.iterrows():
        point = points.get(str(row["asset_id"]))
        if point is None:
            continue
        projected = gpd.GeoSeries([point], crs="EPSG:4326").to_crs(GRID_CRS).iloc[0]
        grid_id = f"G-{int(projected.x // GRID_SIZE_M):04d}-{int(projected.y // GRID_SIZE_M):04d}"
        units = pd.to_numeric(pd.Series([row.get("unit_count", 1)]), errors="coerce").iloc[0]
        units = 1.0 if pd.isna(units) else max(0.0, float(units))
        # A conservative local capacity bound uses 3.5 residents per dwelling.
        result[grid_id] = result.get(grid_id, 0.0) + units * 3.5
    return result


def _population_sum(dataset, geom_utm) -> float:
    geom = gpd.GeoSeries([geom_utm], crs=GRID_CRS).to_crs(dataset.crs).iloc[0]
    try:
        values, _ = mask(dataset, [mapping(geom)], crop=True, filled=True, nodata=0)
    except ValueError:
        return 0.0
    array = values[0]
    nodata = dataset.nodata
    if nodata is not None:
        array = array[array != nodata]
    return float(array[array > 0].sum()) if array.size else 0.0


def build_worldpop_csv(raster_path: Path, output_path: Path) -> int:
    kido_path = BASE / PATHS["external_data"]["kido_grid"]
    if not kido_path.exists():
        raise FileNotFoundError(f"Generate Kido grid first: {kido_path}")
    grids = pd.read_csv(kido_path)[["grid_id", "grid_lat", "grid_lng"]].drop_duplicates("grid_id")
    capacity = _residential_capacity_by_grid()
    residential_grids = sorted(set(capacity))
    if not residential_grids:
        raise ValueError("No residential assets could be assigned to 400m cells")

    rows = []
    with rasterio.open(raster_path) as dataset:
        for row in grids[grids["grid_id"].isin(residential_grids)].itertuples(index=False):
            geom = _grid_geometry(row.grid_id)
            raw = max(0.0, _population_sum(dataset, geom))
            cap = max(0.0, capacity.get(row.grid_id, 0.0))
            rows.append({
                "grid_id": row.grid_id,
                "worldpop_raw_pop": round(raw, 2),
                "worldpop_effective_pop": round(min(raw, cap), 2),
                "residential_unit_capacity": round(cap, 2),
                "source": WORLDPOP_SOURCE,
                "dataset_year": 2026,
                "tier": "3a",
                "is_mock": False,
            })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output_path, index=False)
    print(f"Wrote {output_path} ({len(rows)} residential cells)")
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL, help="WorldPop GeoTIFF URL")
    parser.add_argument("--raster", type=Path, help="Use an already downloaded GeoTIFF")
    args = parser.parse_args()
    output_path = BASE / PATHS["external_data"]["worldpop_grid"]

    if args.raster:
        build_worldpop_csv(args.raster, output_path)
        return

    with tempfile.TemporaryDirectory(prefix="living-masterplan-worldpop-") as temp_dir:
        raster_path = Path(temp_dir) / "worldpop_mys_2026.tif"
        print(f"Downloading WorldPop raster: {args.url}")
        _download(args.url, raster_path)
        build_worldpop_csv(raster_path, output_path)


if __name__ == "__main__":
    main()
