"""Tests for community facility derived metrics."""

import pandas as pd
from app.derived.facility import derive_facility
from app.derived.context import DerivationContext


def _make_ctx():
    asset = pd.Series({
        "asset_id": "F-02",
        "asset_type": "community_facility",
        "subtype": "community_hall",
        "floor_area_m2": 1200,
        "capacity": 200,
        "opex_annual_rm": 280_000,
        "maintenance_annual_rm": 90_000,
    })
    metrics_df = pd.DataFrame([{
        "asset_id": "F-02", "year": 2026, "utilisation_rate": 0.22,
    }])
    business = {"asset_metrics": metrics_df, "assets": pd.DataFrame()}
    return DerivationContext(
        asset=asset,
        business=business,
        geometry={},
        benchmarks={},
        assumptions={"environmental": {"emission_factor_energy": 0.58}},
        accessibility_score=50.0,
        huff_effective_demand=None,
        huff_effective_demand_m2=None,
        maintenance_surge_rm=None,
        graph=None,
        year=2026,
        walking_profile={"coverage_ratio_10min": 0.65, "reachable_population": 1000.0},
        driving_profile={},
        catchment_population_profile={"total": 1000, "age_0_14": 200, "age_15_64": 700, "age_65_plus": 100},
        neighborhood_diversity=0.5,
    )


def test_facility_returns_subtype():
    r = derive_facility(_make_ctx())
    assert r["subtype"] == "community_hall"
    assert r["service_coverage"] == 0.65


def test_facility_carbon_subtype_aware():
    r = derive_facility(_make_ctx())
    # community_hall: 100 kWh/m²/year * 1200 m² * 0.58 / 1000
    expected = (1200 * 100 * 0.58) / 1000
    assert abs(r["carbon_operational_tco2e"] - expected) < 0.01