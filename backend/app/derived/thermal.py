"""Read audited Landsat 8 Level-2 thermal observations."""

import math
from pathlib import Path

import pandas as pd


PROVENANCE_LABEL = "Observed (Landsat 8 L2)"
COLLECTION_ID = "LANDSAT/LC08/C02/T1_L2"
THERMAL_BAND = "ST_B10"
THERMAL_METRIC_FIELDS = (
    "t_asset_c",
    "t_township_c",
    "surface_temp_delta_c",
    "surface_temp_provenance",
    "surface_temp_collection_id",
    "surface_temp_band",
    "surface_temp_source_catalog",
    "surface_temp_valid_pixel_count",
    "surface_temp_period_start",
    "surface_temp_period_end",
    "surface_temp_source_image_count",
)


def load_thermal_observations(path: Path) -> dict:
    """Load per-asset LST values, returning an empty mapping if not generated.

    The delta is recomputed from the two source temperatures so the
    metric contract always remains T_asset - T_township.
    """
    path = Path(path)
    if not path.exists():
        return {}

    frame = pd.read_csv(path)
    required = {"asset_id", "t_asset_c", "t_township_c"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(
            f"Thermal observation file {path} is missing columns: "
            f"{', '.join(sorted(missing))}"
        )
    if frame["asset_id"].astype(str).duplicated().any():
        raise ValueError(f"Thermal observation file has duplicate asset_id values: {path}")

    records = {}
    for row in frame.to_dict(orient="records"):
        asset_id = str(row["asset_id"])
        t_asset = _finite_float(row.get("t_asset_c"))
        t_township = _finite_float(row.get("t_township_c"))
        delta = (
            round(t_asset - t_township, 4)
            if t_asset is not None and t_township is not None
            else None
        )
        records[asset_id] = {
            "t_asset_c": t_asset,
            "t_township_c": t_township,
            "surface_temp_delta_c": delta,
            "surface_temp_provenance": PROVENANCE_LABEL if t_township is not None else None,
            "surface_temp_collection_id": COLLECTION_ID if t_township is not None else None,
            "surface_temp_band": THERMAL_BAND if t_township is not None else None,
            "surface_temp_source_catalog": _optional_str(
                row.get("source_catalog")
            ),
            "surface_temp_valid_pixel_count": _optional_int(
                row.get("valid_pixel_count")
            ),
            "surface_temp_period_start": _optional_str(
                row.get("period_start")
            ),
            "surface_temp_period_end": _optional_str(
                row.get("period_end")
            ),
            "surface_temp_source_image_count": _optional_int(
                row.get("source_image_count")
            ),
        }
    return records


def empty_thermal_metrics() -> dict:
    """Return explicit null thermal fields when no observation is available."""
    return {field: None for field in THERMAL_METRIC_FIELDS}


def _finite_float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _optional_int(value):
    number = _finite_float(value)
    return int(number) if number is not None else None


def _optional_str(value):
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None
