"""Tests for residential derived metrics."""

import pandas as pd
from app.derived.residential import derive_residential
from app.derived.context import DerivationContext


def _make_ctx():
    asset = pd.Series({
        "asset_id": "R-01",
        "asset_type": "residential",
        "subtype": "terrace",
        "floor_area_m2": 42000,
        "opex_annual_rm": 3_200_000,
        "maintenance_annual_rm": 800_000,
    })
    metrics_df = pd.DataFrame([{
        "asset_id": "R-01", "year": 2026,
        "occupancy_rate": 0.92, "energy_kwh": None, "rental_income_rm": 5_000_000,
    }])
    return DerivationContext(
        asset=asset,
        business={"asset_metrics": metrics_df, "assets": pd.DataFrame()},
        geometry={},
        benchmarks={},
        assumptions={},
        accessibility_score=50.0,
        huff_effective_demand=None,
        huff_effective_demand_m2=None,
        maintenance_surge_rm=None,
        graph=None,
        year=2026,
    )


def test_residential_energy_falls_back_to_taxonomy():
    r = derive_residential(_make_ctx())
    assert r["subtype"] == "terrace"
    # terrace intensity = 60 kWh/m²/year
    assert r["energy_kwh"] == 42000 * 60


def test_residential_noi_deducts_both_costs():
    r = derive_residential(_make_ctx())
    assert r["noi_rm"] == 5_000_000 - 3_200_000 - 800_000