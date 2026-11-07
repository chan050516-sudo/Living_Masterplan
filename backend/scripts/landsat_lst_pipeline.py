"""Create auditable Bukit Jelutong asset LST observations from Landsat 8 L2.

The pipeline exports a clear-pixel median composite from Earth Engine, then
uses GeoPandas footprints and rasterio for per-asset zonal statistics.
"""

import argparse
import json
import logging
import math
import os
import sys
import urllib.request
import warnings
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.mask import mask
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject
from rasterio.windows import Window, from_bounds
from shapely.geometry import mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config import load_paths  # noqa: E402


COLLECTION_ID = "LANDSAT/LC08/C02/T1_L2"
SCALE_METERS = 30
THERMAL_SCALE = 0.00341802
THERMAL_OFFSET_K = 149.0
KELVIN_TO_CELSIUS = 273.15
QA_PIXEL_BAD_BITS = (1 << 0) | (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4) | (1 << 5)
LOG = logging.getLogger("landsat_lst_pipeline")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build observed Landsat 8 Level-2 surface temperatures for Bukit Jelutong assets."
    )
    parser.add_argument(
        "--source",
        choices=("earth-engine", "planetary-computer"),
        default="earth-engine",
        help="Image catalog to read (default: Earth Engine). Planetary Computer uses public USGS COGs.",
    )
    parser.add_argument(
        "--start-date",
        default="2025-01-01",
        help="Inclusive acquisition-date start (default: 2025-01-01).",
    )
    parser.add_argument(
        "--end-date",
        default="2026-01-01",
        help="Exclusive acquisition-date end (default: 2026-01-01).",
    )
    parser.add_argument(
        "--max-cloud-cover",
        type=float,
        default=80.0,
        help="Scene-level CLOUD_COVER ceiling; QA_PIXEL still masks cloudy pixels (default: 80).",
    )
    parser.add_argument(
        "--ee-project",
        default=os.environ.get("EARTHENGINE_PROJECT"),
        help="Google Cloud project registered for Earth Engine; defaults to EARTHENGINE_PROJECT.",
    )
    return parser.parse_args()


def _validate_dates(start_date, end_date):
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("Dates must use YYYY-MM-DD format.") from exc
    if start >= end:
        raise ValueError("--start-date must be earlier than the exclusive --end-date.")
    return start, end


def _load_inputs(paths):
    base_dir = REPO_ROOT / paths["base"]
    parcels_path = base_dir / paths["geometry"]["parcels"]
    buildings_path = base_dir / paths["geometry"]["buildings"]
    green_path = base_dir / paths["geometry"]["green_blue"]
    assets_path = base_dir / paths["business"]["assets"]
    parcels = gpd.read_file(parcels_path)
    buildings = gpd.read_file(buildings_path)
    green = gpd.read_file(green_path)
    if parcels.crs is None:
        raise ValueError(f"Parcel layer has no CRS: {parcels_path}")
    assets = pd.read_csv(
        assets_path, usecols=["asset_id", "asset_type", "parcel_id", "building_id"]
    )
    asset_ids = assets["asset_id"].dropna().astype(str).drop_duplicates().tolist()
    if assets["asset_id"].dropna().astype(str).duplicated().any():
        raise ValueError("Asset table contains duplicate asset_id values.")

    if buildings.crs is None or green.crs is None:
        raise ValueError("Building and green-blue layers must have a defined CRS.")
    buildings = buildings.to_crs(parcels.crs)
    green = green.to_crs(parcels.crs)

    def geometries_by_key(frame, key):
        if key not in frame.columns:
            return {}
        selected = frame[frame[key].notna() & frame.geometry.notna()].copy()
        selected[key] = selected[key].astype(str)
        selected = selected[~selected.geometry.is_empty]
        return {
            str(value): group.geometry.union_all()
            for value, group in selected.groupby(key, sort=False)
        }

    building_by_id = geometries_by_key(buildings, "building_id")
    green_by_asset = geometries_by_key(green, "asset_id")
    parcel_by_id = geometries_by_key(parcels, "parcel_id")
    parcel_by_asset = geometries_by_key(parcels, "asset_id")

    def text_key(value):
        if value is None or pd.isna(value):
            return None
        value = str(value).strip()
        return value or None

    records = []
    missing = []
    for row in assets.to_dict(orient="records"):
        asset_id = str(row["asset_id"])
        asset_type = text_key(row.get("asset_type"))
        building_id = text_key(row.get("building_id"))
        parcel_id = text_key(row.get("parcel_id"))
        geometry = None
        footprint_source = None

        if asset_type == "green_space":
            geometry = green_by_asset.get(asset_id)
            if geometry is not None:
                footprint_source = "green_blue"
        if geometry is None and building_id:
            geometry = building_by_id.get(building_id)
            if geometry is not None:
                footprint_source = "building"
        if geometry is None and parcel_id:
            geometry = parcel_by_id.get(parcel_id)
            if geometry is not None:
                footprint_source = "parcel"
        if geometry is None:
            geometry = parcel_by_asset.get(asset_id)
            if geometry is not None:
                footprint_source = "parcel"
        if geometry is None or geometry.is_empty:
            missing.append(asset_id)
            continue
        if not geometry.is_valid:
            geometry = geometry.make_valid()
        records.append(
            {
                "asset_id": asset_id,
                "asset_type": asset_type,
                "footprint_source": footprint_source,
                "geometry": geometry,
            }
        )

    if missing:
        raise ValueError(
            f"No valid footprint found for {len(missing)} assets: "
            f"{', '.join(missing[:20])}"
        )
    footprints = gpd.GeoDataFrame(records, geometry="geometry", crs=parcels.crs)
    source_counts = footprints["footprint_source"].value_counts().to_dict()
    geometry_paths = {
        "parcels": str(parcels_path.relative_to(REPO_ROOT)),
        "buildings": str(buildings_path.relative_to(REPO_ROOT)),
        "green_blue": str(green_path.relative_to(REPO_ROOT)),
    }
    return asset_ids, footprints, source_counts, geometry_paths, assets_path


def _earth_engine_composite(footprints, start_date, end_date, max_cloud_cover, project):
    try:
        import ee
    except ImportError as exc:
        raise RuntimeError(
            "Earth Engine Python API is missing. Install backend/requirements.txt first."
        ) from exc

    if not project:
        raise RuntimeError(
            "Set EARTHENGINE_PROJECT or pass --ee-project to select the registered Earth Engine project."
        )
    try:
        ee.Initialize(project=project)
    except Exception as exc:
        raise RuntimeError(
            "Earth Engine initialization failed. Authenticate this account with "
            "`earthengine authenticate` and confirm the project has Earth Engine access."
        ) from exc

    footprints_wgs84 = footprints.to_crs("EPSG:4326")
    min_x, min_y, max_x, max_y = footprints_wgs84.total_bounds
    region = ee.Geometry.Rectangle([min_x, min_y, max_x, max_y], proj="EPSG:4326", geodesic=False)
    collection = (
        ee.ImageCollection(COLLECTION_ID)
        .filterDate(start_date, end_date)
        .filterBounds(region)
        .filter(ee.Filter.eq("PROCESSING_LEVEL", "L2SP"))
        .filter(ee.Filter.lte("CLOUD_COVER", max_cloud_cover))
        .sort("system:time_start")
    )
    image_count = int(collection.size().getInfo())
    if image_count == 0:
        raise RuntimeError(
            "No L2SP Landsat 8 scenes matched the area, date range, and scene cloud-cover ceiling."
        )

    indices = collection.aggregate_array("system:index").getInfo()
    times = collection.aggregate_array("system:time_start").getInfo()
    cloud_cover = collection.aggregate_array("CLOUD_COVER").getInfo()
    scene_inventory = [
        {
            "system_index": index,
            "acquired_utc": datetime.fromtimestamp(
                timestamp / 1000, tz=timezone.utc
            ).isoformat(),
            "scene_cloud_cover_pct": float(cloud) if cloud is not None else None,
        }
        for index, timestamp, cloud in zip(indices, times, cloud_cover)
    ]

    def clear_surface_temperature(image):
        image = ee.Image(image)
        qa = image.select("QA_PIXEL")
        clear = qa.bitwiseAnd(QA_PIXEL_BAD_BITS).eq(0)
        temperature_c = (
            image.select("ST_B10")
            .multiply(THERMAL_SCALE)
            .add(THERMAL_OFFSET_K)
            .subtract(KELVIN_TO_CELSIUS)
            .rename("lst_c")
        )
        return temperature_c.updateMask(clear).copyProperties(
            image, ["system:time_start", "system:index"]
        )

    composite = collection.map(clear_surface_temperature).median().toFloat()
    composite = composite.unmask(-9999).clip(region)
    return composite, region, scene_inventory


def _download_raster(composite, region, raster_path):
    raster_path.parent.mkdir(parents=True, exist_ok=True)
    url = composite.getDownloadURL(
        {
            "name": raster_path.stem,
            "region": region,
            "scale": SCALE_METERS,
            "crs": "EPSG:32647",
            "format": "GEO_TIFF",
        }
    )
    with urllib.request.urlopen(url, timeout=180) as response:
        data = response.read()
    if len(data) < 256:
        raise RuntimeError("Earth Engine returned an unexpectedly small GeoTIFF download.")
    temporary = raster_path.with_suffix(raster_path.suffix + ".tmp")
    temporary.write_bytes(data)
    with rasterio.open(temporary, "r+") as dst:
        dst.set_band_description(
            1, "Landsat 8 Collection 2 Level-2 ST_B10 surface temperature (Celsius)"
        )
        dst.update_tags(
            provenance="Observed (Landsat 8 L2)",
            source_catalog="Google Earth Engine",
            collection_id=COLLECTION_ID,
            source_band="ST_B10",
            conversion="(DN * 0.00341802 + 149.0) - 273.15",
            qa_band="QA_PIXEL",
            masked_qa_bits="fill,dilated_cloud,cirrus,cloud,cloud_shadow,snow",
        )
    temporary.replace(raster_path)


def _pc_signed_href(href, token):
    token = token.lstrip("?")
    separator = "&" if "?" in href else "?"
    return f"{href}{separator}{token}"


def _planetary_computer_composite(
    footprints, start_date, end_date, max_cloud_cover, raster_path,
):
    """Fetch public USGS Landsat C2 L2 COGs and build a clear-pixel composite."""
    wgs84 = footprints.to_crs("EPSG:4326")
    min_x, min_y, max_x, max_y = wgs84.total_bounds
    search_body = json.dumps(
        {
            "collections": ["landsat-c2-l2"],
            "bbox": [min_x, min_y, max_x, max_y],
            "datetime": f"{start_date}T00:00:00Z/{end_date}T00:00:00Z",
            "limit": 250,
        }
    ).encode("utf-8")
    search_request = urllib.request.Request(
        "https://planetarycomputer.microsoft.com/api/stac/v1/search",
        data=search_body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "LivingMasterplan-LandsatLST/1.0",
        },
    )
    try:
        with urllib.request.urlopen(search_request, timeout=60) as response:
            search_result = json.load(response)
    except Exception as exc:
        raise RuntimeError("Public Planetary Computer STAC search failed.") from exc

    scenes = []
    for item in search_result.get("features", []):
        item_id = str(item.get("id", ""))
        props = item.get("properties", {})
        if not item_id.startswith("LC08_L2SP_") or not item_id.endswith("_T1"):
            continue
        cloud = props.get("eo:cloud_cover")
        if cloud is None or float(cloud) > max_cloud_cover:
            continue
        if "lwir11" not in item.get("assets", {}) or "qa_pixel" not in item.get("assets", {}):
            continue
        scenes.append(item)
    scenes.sort(key=lambda item: item.get("properties", {}).get("datetime", ""))
    if not scenes:
        raise RuntimeError(
            "No Landsat 8 L2SP Tier 1 scenes matched the area, dates, and "
            "scene cloud-cover ceiling in the public catalog."
        )

    try:
        token_request = urllib.request.Request(
            "https://planetarycomputer.microsoft.com/api/sas/v1/token/landsat-c2-l2",
            headers={"User-Agent": "LivingMasterplan-LandsatLST/1.0"},
        )
        with urllib.request.urlopen(token_request, timeout=30) as response:
            sas_token = json.load(response)["token"]
    except Exception as exc:
        raise RuntimeError("Could not obtain a public read token for Landsat COGs.") from exc

    projected = footprints.to_crs("EPSG:32647")
    min_x, min_y, max_x, max_y = projected.total_bounds
    left = math.floor(min_x / SCALE_METERS) * SCALE_METERS
    bottom = math.floor(min_y / SCALE_METERS) * SCALE_METERS
    right = math.ceil(max_x / SCALE_METERS) * SCALE_METERS
    top = math.ceil(max_y / SCALE_METERS) * SCALE_METERS
    width = int(round((right - left) / SCALE_METERS))
    height = int(round((top - bottom) / SCALE_METERS))
    target_transform = from_origin(left, top, SCALE_METERS, SCALE_METERS)
    target_crs = rasterio.crs.CRS.from_epsg(32647)
    temperature_scenes = []
    scene_inventory = []

    def read_asset_window(src, fill_value):
        requested = from_bounds(left, bottom, right, top, src.transform)
        requested = requested.round_offsets().round_lengths()
        col_start = max(0, int(requested.col_off))
        row_start = max(0, int(requested.row_off))
        col_end = min(src.width, int(requested.col_off + requested.width))
        row_end = min(src.height, int(requested.row_off + requested.height))
        if col_end <= col_start or row_end <= row_start:
            return np.full((height, width), fill_value, dtype=np.uint16)
        window = Window(
            col_start, row_start, col_end - col_start, row_end - row_start
        )
        data = src.read(1, window=window)
        destination = np.full((height, width), fill_value, dtype=np.uint16)
        reproject(
            source=data,
            destination=destination,
            src_transform=src.window_transform(window),
            src_crs=src.crs,
            src_nodata=src.nodata,
            dst_transform=target_transform,
            dst_crs=target_crs,
            dst_nodata=fill_value,
            resampling=Resampling.nearest,
        )
        return destination

    raster_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".TIF,.tif",
    ):
        for item in scenes:
            assets = item["assets"]
            st_url = _pc_signed_href(assets["lwir11"]["href"], sas_token)
            qa_url = _pc_signed_href(assets["qa_pixel"]["href"], sas_token)
            with rasterio.open("/vsicurl/" + st_url) as st_src, rasterio.open(
                "/vsicurl/" + qa_url
            ) as qa_src:
                lst_dn = read_asset_window(st_src, 0)
                qa_pixel = read_asset_window(qa_src, 1)
            clear = (qa_pixel & QA_PIXEL_BAD_BITS) == 0
            clear &= lst_dn != 0
            temperature = (
                lst_dn.astype("float32") * THERMAL_SCALE
                + THERMAL_OFFSET_K
                - KELVIN_TO_CELSIUS
            )
            temperature[~clear] = np.nan
            temperature_scenes.append(temperature)
            props = item.get("properties", {})
            scene_inventory.append(
                {
                    "system_index": item["id"],
                    "acquired_utc": props.get("datetime"),
                    "scene_cloud_cover_pct": float(props["eo:cloud_cover"]),
                    "scene_cloud_cover_land_pct": props.get(
                        "landsat:cloud_cover_land"
                    ),
                    "wrs_path": props.get("landsat:wrs_path"),
                    "wrs_row": props.get("landsat:wrs_row"),
                    "collection_category": props.get(
                        "landsat:collection_category"
                    ),
                }
            )
            LOG.info(
                "Read %s (scene cloud cover %.2f%%).",
                item["id"], float(props["eo:cloud_cover"]),
            )

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="All-NaN slice encountered")
        composite = np.nanmedian(np.stack(temperature_scenes, axis=0), axis=0)
    valid = np.isfinite(composite)
    if not valid.any():
        raise RuntimeError("The selected scenes have no clear valid LST pixels over the area.")
    composite = np.where(valid, composite, -9999).astype("float32")
    profile = {
        "driver": "GTiff",
        "width": width,
        "height": height,
        "count": 1,
        "dtype": "float32",
        "crs": target_crs,
        "transform": target_transform,
        "nodata": -9999,
        "compress": "deflate",
        "predictor": 3,
    }
    temporary = raster_path.with_suffix(raster_path.suffix + ".tmp")
    with rasterio.open(temporary, "w", **profile) as dst:
        dst.write(composite, 1)
        dst.set_band_description(1, "Landsat 8 ST_B10 surface temperature (Celsius)")
    temporary.replace(raster_path)
    return scene_inventory


def _zonal_mean(src, geometry):
    try:
        raster, _ = mask(
            src,
            [mapping(geometry)],
            indexes=1,
            crop=True,
            filled=False,
            all_touched=True,
        )
    except ValueError:
        return None, 0
    values = np.asarray(raster.data, dtype="float64")
    valid = ~np.ma.getmaskarray(raster) & np.isfinite(values) & (values != -9999)
    count = int(valid.sum())
    if count == 0:
        return None, 0
    return float(values[valid].mean()), count


def _aggregate(asset_ids, footprints, raster_path):
    projected = footprints.to_crs("EPSG:32647")
    projected_geometries = {}
    for asset_id, group in projected.groupby("asset_id", sort=False):
        projected_geometries[str(asset_id)] = group.geometry.union_all()
    township_geometry = projected.geometry.union_all()

    with rasterio.open(raster_path) as src:
        if src.crs is None:
            raise ValueError(f"Downloaded raster has no CRS: {raster_path}")
        if src.crs.to_epsg() != 32647:
            raise ValueError(
                f"Expected raster EPSG:32647, received {src.crs}; zonal aggregation stopped."
            )
        township_mean, township_count = _zonal_mean(src, township_geometry)
        if township_mean is None:
            raise RuntimeError("The composite has no valid clear LST pixels over asset footprints.")

        results = []
        for asset_id in asset_ids:
            geometry = projected_geometries.get(asset_id)
            t_asset, pixel_count = (
                _zonal_mean(src, geometry) if geometry is not None else (None, 0)
            )
            t_asset_rounded = round(t_asset, 4) if t_asset is not None else None
            township_rounded = round(township_mean, 4)
            results.append(
                {
                    "asset_id": asset_id,
                    "t_asset_c": t_asset_rounded,
                    "t_township_c": township_rounded,
                    "surface_temp_delta_c": (
                        round(t_asset_rounded - township_rounded, 4)
                        if t_asset_rounded is not None
                        else None
                    ),
                    "valid_pixel_count": pixel_count,
                }
            )
    return results, township_mean, township_count


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    start, end = _validate_dates(args.start_date, args.end_date)
    if not 0 <= args.max_cloud_cover <= 100:
        raise ValueError("--max-cloud-cover must be between 0 and 100.")

    paths = load_paths()
    asset_ids, footprints, footprint_source_counts, geometry_paths, assets_path = _load_inputs(paths)
    LOG.info(
        "Matched %d of %d assets to footprints (%s).",
        len(footprints), len(asset_ids), footprint_source_counts,
    )

    base_dir = REPO_ROOT / paths["base"]
    thermal_dir = base_dir / paths.get("thermal", {}).get("directory", "thermal")
    raster_name = f"landsat8_lst_composite_{start.isoformat()}_{end.isoformat()}.tif"
    raster_path = thermal_dir / raster_name

    if args.source == "earth-engine":
        composite, region, scene_inventory = _earth_engine_composite(
            footprints=footprints,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            max_cloud_cover=args.max_cloud_cover,
            project=args.ee_project,
        )
        _download_raster(composite, region, raster_path)
        source_catalog = "Google Earth Engine"
    else:
        scene_inventory = _planetary_computer_composite(
            footprints=footprints,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            max_cloud_cover=args.max_cloud_cover,
            raster_path=raster_path,
        )
        source_catalog = "Microsoft Planetary Computer STAC"

    results, township_mean, township_count = _aggregate(asset_ids, footprints, raster_path)
    for result in results:
        result.update(
            {
                "period_start": start.isoformat(),
                "period_end": end.isoformat(),
                "source_image_count": len(scene_inventory),
                "source_catalog": source_catalog,
                "provenance": "Observed (Landsat 8 L2)",
            }
        )

    observations_rel = paths.get("thermal", {}).get(
        "observations", "business/thermal_observations.csv"
    )
    observations_path = base_dir / observations_rel
    observations_path.parent.mkdir(parents=True, exist_ok=True)
    observations = pd.DataFrame(results)
    csv_temp = observations_path.with_suffix(observations_path.suffix + ".tmp")
    observations.to_csv(csv_temp, index=False)
    csv_temp.replace(observations_path)

    manifest_rel = paths.get("thermal", {}).get(
        "manifest", "thermal/thermal_observations_manifest.json"
    )
    manifest_path = base_dir / manifest_rel
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(raster_path) as downloaded_raster:
        raster_grid = {
            "width": int(downloaded_raster.width),
            "height": int(downloaded_raster.height),
            "transform": list(downloaded_raster.transform)[:6],
        }
    manifest = {
        "provenance": "Observed (Landsat 8 L2)",
        "collection_id": COLLECTION_ID,
        "source_catalog": source_catalog,
        "collection_tier": "Tier 1",
        "processing_level": "L2SP",
        "band": "ST_B10",
        "unit": "degrees Celsius",
        "conversion": "(DN * 0.00341802 + 149.0) - 273.15",
        "cloud_mask": {
            "qa_band": "QA_PIXEL",
            "masked_bits": ["fill", "dilated_cloud", "cirrus", "cloud", "cloud_shadow", "snow"],
            "scene_cloud_cover_max_pct": args.max_cloud_cover,
        },
        "composite": "per-pixel median of QA-masked clear LST observations",
        "period_start_inclusive": start.isoformat(),
        "period_end_exclusive": end.isoformat(),
        "spatial_resolution_m": SCALE_METERS,
        "raster_crs": "EPSG:32647",
        "zonal_statistic": "mean of valid 30m pixels intersecting each asset footprint (all_touched=true)",
        "township_baseline_scope": "union of all asset footprints; overlaps counted once",
        "township_mean_c": round(township_mean, 4),
        "township_valid_pixel_count": township_count,
        "asset_count": len(asset_ids),
        "asset_count_with_valid_pixels": sum(row["valid_pixel_count"] > 0 for row in results),
        "asset_count_without_valid_pixels": sum(row["valid_pixel_count"] == 0 for row in results),
        "source_geometry": geometry_paths,
        "footprint_source_counts": footprint_source_counts,
        "source_assets_table": str(assets_path.relative_to(REPO_ROOT)),
        "raster_path": str(raster_path.relative_to(REPO_ROOT)),
        "observations_path": str(observations_path.relative_to(REPO_ROOT)),
        "raster_grid": raster_grid,
        "source_scenes": scene_inventory,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_provider_credit": "Landsat 8 Collection 2 Level-2, courtesy of the U.S. Geological Survey.",
    }
    manifest_temp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    manifest_temp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    manifest_temp.replace(manifest_path)
    LOG.info(
        "Wrote %s rows (%d with valid pixels); township baseline %.2f C.",
        len(results), manifest["asset_count_with_valid_pixels"], township_mean,
    )
    LOG.info("Raster: %s", raster_path)
    LOG.info("Observations: %s", observations_path)
    LOG.info("Manifest: %s", manifest_path)


if __name__ == "__main__":
    main()
