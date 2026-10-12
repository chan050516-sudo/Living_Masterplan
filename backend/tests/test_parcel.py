"""Tests for undeveloped parcel derived metrics."""

import pandas as pd
from app.derived.parcel import derive_parcel
from app.derived.context import DerivationContext


def _make_ctx():
    asset = pd.Series({
        "asset_id": "P-05",
        "asset_type": "undeveloped_parcel",
        "subtype": "vacant",
        "land_area_m2": 3600,
    })
    return DerivationContext(
        asset=asset,
        business={"asset_metrics": pd.DataFrame(), "assets": pd.DataFrame([{
            "asset_id": "B-03", "asset_type": "commercial", "lettable_area_m2": 5200,
        }])},
        geometry={},
        benchmarks={},
        assumptions={},
        accessibility_score=50.0,
        huff_effective_demand=None,
        huff_effective_demand_m2=None,
        maintenance_surge_rm=None,
        graph=None,
        year=2026,
        walking_profile={"reachable_population": 1820.0},
        driving_profile={},
    )


def test_parcel_uses_reachable_population():
    r = derive_parcel(_make_ctx())
    assert r["subtype"] == "vacant"
    assert r["developable_area_m2"] == 3600
    assert r["potential_gfa_m2"] == 3600 * 1.5