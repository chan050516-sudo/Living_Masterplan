"""Residential asset derived metrics — R-01."""

import math
from .context import DerivationContext


def derive_residential(ctx: DerivationContext) -> dict:
    asset = ctx.asset
    year = ctx.year

    metrics = ctx.business["asset_metrics"]
    row = metrics[
        (metrics["asset_id"] == asset["asset_id"]) &
        (metrics["year"] == year)
    ]
    if row.empty:
        occupancy = None
        energy_kwh = None
    else:
        raw = row.iloc[0]
        occupancy = _num(raw.get("occupancy_rate"))
        energy_kwh = _num(raw.get("energy_kwh"))

    floor_area = asset.get("floor_area_m2")
    energy_intensity = None
    if energy_kwh is not None and floor_area and float(floor_area) > 0:
        energy_intensity = energy_kwh / float(floor_area)

    # NOI
    rental_income = None
    if not row.empty:
        rental_income = _num(row.iloc[0].get("rental_income_rm"))
    opex = _num(asset.get("opex_annual_rm"))
    noi = None
    if rental_income is not None and opex is not None:
        noi = rental_income - opex

    return {
        "asset_id": asset["asset_id"],
        "year": year,
        "occupancy_rate": occupancy,
        "energy_intensity_kwh_m2": energy_intensity,
        "noi_rm": noi,
        "accessibility_score": ctx.accessibility_score,
        "metric_source": "derived",
        "model_version": "0.3.0",
    }


def _num(v):
    if v is None:
        return None
    try:
        f = float(v)
        if math.isnan(f):
            return None
        return f
    except (TypeError, ValueError):
        return None