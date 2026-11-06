# Landsat 8 Level-2 land surface temperature

`backend/scripts/landsat_lst_pipeline.py` creates asset-level observed land
surface temperatures for Bukit Jelutong. It matches all asset rows to building,
green-blue, or parcel footprints, exports a clear-pixel composite from Earth
Engine, and calculates zonal means locally.

## Run

Install the repository and backend requirements, register the Google account
and Cloud project for Earth Engine, then authenticate once:

```powershell
earthengine authenticate
$env:EARTHENGINE_PROJECT = "natively-stt-490722"
python backend/scripts/landsat_lst_pipeline.py --start-date 2026-10-19 --end-date 2026-10-20 --max-cloud-cover 20
```

The end date is exclusive. `--max-cloud-cover` controls a scene-level screening
filter; pixel-level QA masking is applied independently.

The current generated observation used Google Earth Engine and scene
`LC08_127058_20261019`, acquired 2026-10-19 at 03:28 UTC (15.24% scene cloud
cover). It produced 916 asset rows; 679 have valid clear pixels and 237 have
no valid thermal pixels. The township baseline is 39.3318 °C for this
observation period.

If Earth Engine credentials are unavailable, the same script can read the
public USGS COGs through the Planetary Computer STAC catalog. For a clear
single-scene observation, the catalog currently lists a Tier 1 Landsat 8 scene
over Bukit Jelutong from 2026-10-19:

```powershell
python backend/scripts/landsat_lst_pipeline.py --source planetary-computer --start-date 2026-10-19 --end-date 2026-10-20 --max-cloud-cover 20
```

## Method

- Collection: `LANDSAT/LC08/C02/T1_L2`, Tier 1 scenes with `PROCESSING_LEVEL=L2SP`.
- Thermal conversion: `(ST_B10 * 0.00341802 + 149.0) - 273.15` to degrees Celsius.
- Cloud mask: exclude `QA_PIXEL` fill, dilated cloud, cirrus, cloud, cloud
  shadow, and snow bits. The Level-2 ST_B10 mask is also respected.
- Composite: median of valid clear-pixel observations in the requested period.
- Resolution and CRS: 30 m, EPSG:32647.
- The delivered grid is 30 m; thermal measurements have an approximately
  100 m native sensor footprint and are resampled in the Level-2 product.
  Small building footprints therefore reflect intersecting neighborhood-scale
  thermal pixels rather than independently resolved roof temperatures.
- Parcel statistic: arithmetic mean of valid raster cells intersecting each
  asset footprint (`all_touched=true`). The township baseline is currently the
  mean over the union of matched asset footprints, with overlapping geometry
  counted once. This is a mapped-asset-footprint baseline, not an official
  administrative township boundary; its scope is recorded in the manifest.
- Metric: `surface_temp_delta_c = t_asset_c - t_township_c`. Negative deltas
  are valid and mean the parcel was cooler than this baseline.

The statistic is a satellite surface-temperature observation, not air
temperature. It summarizes the selected date period and should be presented
with that period. Assets without clear valid pixels retain null temperatures;
no canopy proxy is substituted.

## Outputs and API provenance

- `bukit_jelutong/processed/thermal/landsat8_lst_composite_<start>_<end>.tif`:
  downloaded temperature composite for inspection and reproducibility.
- `bukit_jelutong/processed/business/thermal_observations.csv`: one row per
  asset, including parcel and township temperatures, delta, valid pixel count,
  period, and source-image count.
- `bukit_jelutong/processed/thermal/thermal_observations_manifest.json`:
  collection, scene inventory, QA mask, conversion, raster grid, zonal method,
  coverage counts, and data credit.

After producing the observations, regenerate the downstream metrics and API
profiles:

```powershell
python backend/scripts/run_phase1.py
python backend/scripts/run_phase3.py
python backend/scripts/build_profiles.py
python backend/scripts/run_phase4.py --current-only
```

Asset metric and profile payloads expose `t_asset_c`, `t_township_c`,
`surface_temp_delta_c`, `surface_temp_provenance`,
`surface_temp_collection_id`, `surface_temp_band`, and
`surface_temp_source_catalog`. The provenance label is `Observed (Landsat 8
L2)` when the township raster baseline is available.

The Earth Engine path is the default. `--source planetary-computer` is
available as a public catalog fallback when Earth Engine project credentials
are not configured; it uses the same USGS Collection 2 Level-2 scenes and QA
bands. The data access catalog is recorded separately from the Landsat source
collection in the manifest and API payload.
