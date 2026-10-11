"""Taxonomy loader and helpers.

Provides subtype-level access to benchmarks defined in taxonomy.yml.
This module is the single source of truth for asset subtype classification
across B3, B4, B5, and B6.
"""

from functools import lru_cache
from pathlib import Path
from typing import Optional
import yaml

from .config import CONFIG_DIR


# ---------------------------------------------------------------
# Loader
# ---------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_taxonomy() -> dict:
    path = CONFIG_DIR / "taxonomy.yml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_taxonomy() -> dict:
    """Return the whole taxonomy dict."""
    return _load_taxonomy()


def get_subtype(subtype_name: str) -> Optional[dict]:
    """
    Return the subtype definition, or None if the subtype does not exist.
    """
    tax = _load_taxonomy()
    return tax.get("subtypes", {}).get(subtype_name)


def get_subtype_or_default(subtype_name: Optional[str]) -> dict:
    """
    Convenience wrapper for derivers. Returns a safe default
    (empty dict) when subtype is None or unknown, so callers can use
    .get() safely without crashing.
    """
    if subtype_name is None:
        return {}
    return get_subtype(subtype_name) or {}


def get_subtypes_for_class(asset_class: str) -> list:
    """Return list of subtype names matching the given asset class."""
    tax = _load_taxonomy()
    return [
        name for name, defn in tax.get("subtypes", {}).items()
        if defn.get("asset_class") == asset_class
    ]


def get_asset_class(subtype_name: str) -> Optional[str]:
    """Return the asset_class that the subtype belongs to."""
    defn = get_subtype(subtype_name)
    return defn.get("asset_class") if defn else None


def is_core_amenity(subtype_name: str) -> bool:
    """Check if the subtype is listed as a core amenity."""
    return subtype_name in (_load_taxonomy().get("core_amenities") or [])


def get_core_amenities() -> list:
    """Return the list of core amenity subtypes."""
    return list(_load_taxonomy().get("core_amenities") or [])


def get_benchmark(subtype_name: str, key: str, default=None):
    """
    Return a specific benchmark value for a subtype.

    Examples:
        get_benchmark("clinic", "utilisation_benchmark")  # -> 0.65
        get_benchmark("office", "energy_intensity_kwh_m2_year")  # -> 150
    """
    defn = get_subtype(subtype_name)
    if defn is None:
        return default
    return defn.get(key, default)


def get_energy_intensity(subtype_name: str) -> Optional[float]:
    """
    Energy intensity in kWh/m²/year for the subtype.
    Returns None if the subtype has no defined intensity (e.g. green space).
    """
    return get_benchmark(subtype_name, "energy_intensity_kwh_m2_year")


def get_competition_radius_m(subtype_name: str) -> Optional[float]:
    """
    Radius (in metres) within which the subtype competes for demand.
    Used by Huff gravity to filter which supply nodes compete.
    Returns None if the subtype does not compete for demand.
    """
    return get_benchmark(subtype_name, "competition_radius_m")


def get_target_demographics(subtype_name: str) -> list:
    """Return the list of demographic groups this subtype targets."""
    return get_benchmark(subtype_name, "target_demographics", default=[]) or []


def get_occupancy_benchmark(subtype_name: str) -> Optional[float]:
    """Occupancy benchmark for commercial subtypes."""
    return (
        get_benchmark(subtype_name, "occupancy_benchmark")
        or get_benchmark(subtype_name, "utilisation_benchmark")
    )