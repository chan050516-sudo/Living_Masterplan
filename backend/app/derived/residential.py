"""Residential asset derived metrics — subtype-aware.

Phase 4 changes:
  - Energy intensity benchmark from taxonomy by subtype.
  - NOI deducts maintenance in addition to opex, matching commercial.
  - Adds subtype to the output row.

FIX: NOI now applies the same aging-factor maintenance escalation
used by commercial.deriver, so NOI is comparable across asset types.
"""

import math
from .. import __version__
from .context import DerivationContext
from ..taxonomy import get_subtype_or_default, get_energy_intensity
from .environmental import operational_carbon


def derive_residential(ctx: DerivationContext) -> dict:
    asset = ctx.asset
    year = ctx.year
    assumptions = ctx.assumptions

    subtype = asset.get("subtype") or "terrace"
    subtype_cfg = get_subtype_or_default(subtype)  # noqa: F841 (kept for parity)

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

    # If energy_kwh is missing, derive from subtype intensity.
    if energy_kwh is None and floor_area:
        intensity_benchmark = get_energy_intensity(subtype)
        if intensity_benchmark is not None:
            energy_kwh = float(floor_area) * float(intensity_benchmark)

    energy_intensity = None
    if energy_kwh is not None and floor_area and float(floor_area) > 0:
        energy_intensity = energy_kwh / float(floor_area)

    # NOI: deduct both opex and maintenance, consistent with commercial.
    rental_income = None
    if not row.empty:
        rental_income = _num(row.iloc[0].get("rental_income_rm"))
    opex = _num(asset.get("opex_annual_rm"))

    # Apply the same aging factor that commercial uses.
    maintenance_base = _num(asset.get("maintenance_annual_rm"))
    completion_year = asset.get("completion_year")
    maintenance = maintenance_base
    if (
        maintenance_base is not None
        and completion_year is not None
        and not _isnan(completion_year)
    ):
        alpha = assumptions.get("asset_aging", {}).get("alpha", 0.03)
        years_old = max(0, year - int(completion_year))
        maintenance = maintenance_base * (1.0 + alpha) ** years_old

    noi = None
    if rental_income is not None:
        total_cost = (opex or 0.0) + (maintenance or 0.0)
        noi = rental_income - total_cost

    # --- Carbon ---
    energy_kwh_out = energy_kwh
    carbon = None
    if energy_kwh_out is not None:
        carbon = operational_carbon(
            energy_kwh_out,
            assumptions.get("environmental", {}).get("emission_factor_energy", 0.58),
        )

    return {
        "asset_id": asset["asset_id"],
        "year": year,
        "subtype": subtype,
        "occupancy_rate": occupancy,
        "energy_kwh": energy_kwh_out,
        "energy_intensity_kwh_m2": energy_intensity,
        "noi_rm": noi,
        "carbon_operational_tco2e": carbon,
        "accessibility_score": ctx.accessibility_score,  # deprecated bridge
        "metric_source": "derived",
        "model_version": __version__,
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


def _isnan(v) -> bool:
    try:
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return False