"""Tests for the taxonomy loader."""

from app.taxonomy import (
    get_subtype,
    get_subtypes_for_class,
    get_asset_class,
    is_core_amenity,
    get_core_amenities,
    get_energy_intensity,
    get_competition_radius_m,
    get_target_demographics,
)


def test_get_subtype():
    clinic = get_subtype("clinic")
    assert clinic is not None
    assert clinic["asset_class"] == "community_facility"


def test_get_unknown_subtype():
    assert get_subtype("no_such_subtype") is None


def test_get_subtypes_for_class():
    commercial = get_subtypes_for_class("commercial")
    assert "convenience_retail" in commercial
    assert "office" in commercial
    assert "clinic" not in commercial


def test_get_asset_class():
    assert get_asset_class("terrace") == "residential"
    assert get_asset_class("park") == "green_space"


def test_core_amenities():
    amenities = get_core_amenities()
    assert "clinic" in amenities
    assert "school" in amenities
    assert "office" not in amenities
    assert is_core_amenity("clinic") is True
    assert is_core_amenity("office") is False


def test_energy_intensity():
    assert get_energy_intensity("office") == 150
    assert get_energy_intensity("park") is None


def test_competition_radius():
    assert get_competition_radius_m("supermarket") == 3000
    assert get_competition_radius_m("clinic") is None or \
           get_competition_radius_m("clinic") == 1500


def test_target_demographics():
    assert "seniors" in get_target_demographics("clinic")
    assert "workers" in get_target_demographics("office")