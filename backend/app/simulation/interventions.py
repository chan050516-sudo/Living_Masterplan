"""Apply interventions to an asset row, producing a transformed asset.

Phase 6 changes:
  - Repurpose reads `to_subtype` (a taxonomy key) from parameters.
    Falls back to mapping `to` (asset_type) to a default subtype.
  - Capacity / floor area / opex updates follow the subtype.

FIX: NaN-safe numeric updates. Previously `value is not None` admitted
NaN, which then propagated through the arithmetic.
FIX: repurpose no longer overwrites `land_use` — that is a planning
attribute and must not be replaced with asset_type.
"""

import json
import logging
import math

from ..taxonomy import get_subtype, DEFAULT_SUBTYPE_BY_ASSET_TYPE

log = logging.getLogger(__name__)


def apply_intervention(asset: dict, intervention: dict) -> dict:
    """
    Returns a copy of asset with intervention state applied.
    Called only when phase == POST.
    """
    new_asset = dict(asset)
    itype = intervention["intervention_type"]

    try:
        params = json.loads(intervention.get("parameters_json") or "{}")
    except (json.JSONDecodeError, TypeError):
        params = {}

    if itype == "repurpose":
        _apply_repurpose(new_asset, params, intervention)

    elif itype == "retrofit":
        _apply_retrofit(new_asset, params, intervention)

    elif itype in ("pedestrian_upgrade", "green_corridor"):
        # Spatial-layer interventions modify the walking network
        # (canopy_coverage_ratio on target edges), not the asset row.
        # They are applied in simulation.spatial and picked up by B4's
        # network-version cache. No-op here.
        pass

    elif itype in ("new_development", "delay_development"):
        # Handled by the supply model (see supply.active_projects_in_year).
        pass

    return new_asset


def _apply_repurpose(asset: dict, params: dict, intervention: dict) -> None:
    """
    Mutates `asset` in place.

    Resolution order for the new subtype:
      1. `to_subtype` (explicit taxonomy key)
      2. `to` mapped through DEFAULT_SUBTYPE_BY_ASSET_TYPE
      3. current subtype (no change)
    """
    new_subtype = params.get("to_subtype")
    if new_subtype is None:
        target_asset_type = params.get("to", "community_facility")
        new_subtype = DEFAULT_SUBTYPE_BY_ASSET_TYPE.get(
            target_asset_type, "community_hall",
        )

    subtype_def = get_subtype(new_subtype)
    if subtype_def is None:
        log.warning(
            "Repurpose to unknown subtype %s; keeping current subtype.",
            new_subtype,
        )
        return

    asset["subtype"] = new_subtype
    asset["asset_type"] = subtype_def.get("asset_class", asset.get("asset_type"))
    # NOTE: `land_use` is a planning attribute (e.g. mixed_use) and must
    # not be overwritten with asset_type.

    if "new_capacity" in params:
        asset["capacity"] = params["new_capacity"]

    delta = intervention.get("opex_delta_rm") or 0
    if _is_number(asset.get("opex_annual_rm")):
        asset["opex_annual_rm"] = float(asset["opex_annual_rm"]) + float(delta)


def _apply_retrofit(asset: dict, params: dict, intervention: dict) -> None:
    """
    Retrofit raises CAPEX, reduces maintenance, and reduces operational
    energy intensity. The energy gain is expressed as a multiplier on
    the subtype's baseline intensity, read by the simulation engine when
    it computes `energy_kwh` and `carbon_operational_tco2e`.

    Default efficiency gain: 15%. It can be overridden by the
    intervention's parameters_json via an `energy_efficiency_gain`
    key (0-1), for future sensitivity work.
    """
    delta = intervention.get("capex_delta_rm") or 0
    if _is_number(asset.get("capex_initial_rm")):
        asset["capex_initial_rm"] = float(asset["capex_initial_rm"]) + float(delta)
    if _is_number(asset.get("maintenance_annual_rm")):
        asset["maintenance_annual_rm"] = float(asset["maintenance_annual_rm"]) * 0.8

    # Energy gain. `params["energy_efficiency_gain"]` is a fractional
    # reduction (0.15 → 15%). Falls back to 0.15 when absent.
    gain = 0.15
    try:
        if "energy_efficiency_gain" in params:
            gain = float(params["energy_efficiency_gain"])
    except (TypeError, ValueError):
        pass
    gain = max(0.0, min(0.90, gain))
    asset["_energy_efficiency_multiplier"] = 1.0 - gain


def apply_construction_state(asset: dict, status: str) -> dict:
    """During construction: reduce metrics to reflect unavailable/partial state."""
    new_asset = dict(asset)
    new_asset["_construction_status"] = status
    return new_asset


def _is_number(v) -> bool:
    """Return True if v is a real number (not None, not NaN)."""
    if v is None:
        return False
    try:
        return not math.isnan(float(v))
    except (TypeError, ValueError):
        return False