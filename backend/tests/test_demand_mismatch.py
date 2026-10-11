"""Tests for demographic mismatch."""

from app.derived.demand_mismatch import demographic_mismatch


def test_all_targets_no_mismatch():
    profile = {"total": 1000, "age_0_14": 100, "age_15_64": 800, "age_65_plus": 100}
    assert demographic_mismatch(profile, ["all"]) == 0.0


def test_seniors_in_senior_area():
    profile = {"total": 1000, "age_0_14": 50, "age_15_64": 400, "age_65_plus": 550}
    mismatch = demographic_mismatch(profile, ["seniors"])
    assert mismatch == 0.0


def test_seniors_in_child_area():
    profile = {"total": 1000, "age_0_14": 400, "age_15_64": 550, "age_65_plus": 50}
    mismatch = demographic_mismatch(profile, ["seniors"])
    assert mismatch > 0.9


def test_young_families_in_child_area():
    profile = {"total": 1000, "age_0_14": 300, "age_15_64": 650, "age_65_plus": 50}
    assert demographic_mismatch(profile, ["young_families"]) == 0.0