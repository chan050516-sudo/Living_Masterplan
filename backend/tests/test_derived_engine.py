"""End-to-end test of Phase 1 on the mock township."""

import pandas as pd
from app.derived.engine import compute_derived_metrics


def test_b03_commercial_derived():
    df = compute_derived_metrics(year=2026)
    b03 = df[df["asset_id"] == "B-03"]
    assert not b03.empty

    row = b03.iloc[0]
    # From mock asset_metrics
    assert row["occupancy_rate"] == 0.21
    assert abs(row["vacancy_rate"] - 0.79) < 0.001
    assert row["vacancy_duration_months"] == 14

    # NOI = rental_income - opex - maintenance_surge
    # Mock B-03: rental_income=960k, opex=820k, maintenance_surge≈190k
    # → NOI ≈ -50k (negative, distress signal)
    assert "noi_rm" in row.index
    assert "accessibility_score" in row.index
    assert row["accessibility_score"] is not None
    assert 0 <= row["accessibility_score"] <= 100


def test_f02_facility_derived():
    df = compute_derived_metrics(year=2026)
    f02 = df[df["asset_id"] == "F-02"]
    assert not f02.empty
    row = f02.iloc[0]
    assert row["utilisation_rate"] == 0.22


def test_g01_green_derived():
    df = compute_derived_metrics(year=2026)
    g01 = df[df["asset_id"] == "G-01"]
    assert not g01.empty
    row = g01.iloc[0]
    # green_coverage = 5200 / 5200 = 1.0
    assert abs(row["green_coverage"] - 1.0) < 0.001


def test_p05_parcel_derived():
    df = compute_derived_metrics(year=2026)
    p05 = df[df["asset_id"] == "P-05"]
    assert not p05.empty
    row = p05.iloc[0]
    # developable = 3600 - 0 = 3600; potential_gfa = 3600 * 1.5 = 5400
    assert abs(row["developable_area_m2"] - 3600) < 1
    assert abs(row["potential_gfa_m2"] - 5400) < 1

def test_b03_has_walking_profile():
    df = compute_derived_metrics(year=2026)
    b03 = df[df["asset_id"] == "B-03"]
    assert not b03.empty
    row = b03.iloc[0]

    assert "coverage_ratio_5min_walk" in row.index
    assert "coverage_ratio_10min_walk" in row.index
    assert "coverage_ratio_10min_drive" in row.index
    assert "mean_walk_distance_m" in row.index

    # Deprecated bridge still present
    assert "accessibility_score" in row.index


def test_all_assets_returned():
    df = compute_derived_metrics(year=2026)
    assert set(df["asset_id"]) == {"B-03", "F-02", "G-01", "P-05", "R-01"}