"""End-to-end test of B3 on the mock township."""

import pandas as pd
from app.derived.engine import compute_derived_metrics


def test_b03_has_subtype_and_profile():
    df = compute_derived_metrics(year=2026)
    b03 = df[df["asset_id"] == "B-03"]
    assert not b03.empty
    row = b03.iloc[0]

    assert row["subtype"] == "convenience_retail"
    assert "coverage_ratio_5min_walk" in row.index
    assert "coverage_ratio_10min_drive" in row.index
    assert "carbon_operational_tco2e" in row.index


def test_f02_has_subtype_and_carbon():
    df = compute_derived_metrics(year=2026)
    f02 = df[df["asset_id"] == "F-02"]
    assert not f02.empty
    row = f02.iloc[0]
    assert row["subtype"] == "community_hall"
    assert row["carbon_operational_tco2e"] is not None


def test_g01_uses_subtype_canopy_benchmark():
    df = compute_derived_metrics(year=2026)
    g01 = df[df["asset_id"] == "G-01"]
    assert not g01.empty
    row = g01.iloc[0]
    assert row["subtype"] == "park"
    assert row["canopy_ratio_benchmark"] == 0.35


def test_r01_subtype_is_terrace():
    df = compute_derived_metrics(year=2026)
    r01 = df[df["asset_id"] == "R-01"]
    assert not r01.empty
    assert r01.iloc[0]["subtype"] == "terrace"


def test_all_assets_returned():
    df = compute_derived_metrics(year=2026)
    assert set(df["asset_id"]) == {"B-03", "F-02", "G-01", "P-05", "R-01"}