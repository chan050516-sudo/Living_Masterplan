"""Tests for green space derived metrics."""

import pandas as pd
from app.derived.green import derive_green
from app.derived.context import DerivationContext


def _make_ctx():
    asset = pd.Series({
        "asset_id": "G-01",
        "asset_type": "green_space",
        "subtype": "park",
        "land_area_m2": 5200,
    })
    return DerivationContext(
        asset=asset,
        business={"asset_metrics": pd.DataFrame(), "assets": pd.DataFrame()},
        geometry={"green_blue": {"analysis": None}},
        benchmarks={},
        assumptions={},
        accessibility_score=50.0,
        huff_effective_demand=None,
        huff_effective_demand_m2=None,
        maintenance_surge_rm=None,
        graph=None,
        year=2026,
        canopy_coverage=0.08,
        walking_profile={"reachable_population": 1000.0},
        driving_profile={},
        neighborhood_diversity=0.0,
    )


def test_green_returns_subtype_benchmark():
    r = derive_green(_make_ctx())
    assert r["subtype"] == "park"
    assert r["canopy_ratio_benchmark"] == 0.35
    assert abs(r["shade_proxy_score"] - 8.0) < 0.01