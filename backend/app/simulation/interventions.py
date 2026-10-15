"""Apply interventions to an asset row, producing a transformed asset.

Phase 6 changes:
  - Repurpose reads `to_subtype` (a taxonomy key) from parameters.
    Falls back to mapping `to` (asset_type) to a default subtype.
  - Capacity / floor area / opex updates follow the subtype.

Phase 11 changes:
  - `interim_solar_farm` marks the asset with `_is_interim` and sets
    its effective subtype to `solar_farm`. The B4 engine detects this
    marker and computes a negative carbon offset instead of a
    positive operational load.
"""

import json
import logging
import math

from ..taxonomy import get_subtype, DEFAULT_SUBTYPE_BY_ASSET_TYPE

log = logging.getLogger(__name__)


def apply_intervention(asset: dict, intervention: dict) -> dict:
    """Returns a copy of asset with intervention state applied."""
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
        # Spatial-layer interventions modify the walking network.
        pass

    elif itype in ("new_development", "delay_development"):
        # Handled by the supply model.
        pass

    elif itype == "interim_solar_farm":
        # Phase 11 — marker only. B4 reads `_is_interim` and
        # `subtype == "solar_farm"` to emit a negative carbon row.
        new_asset["subtype"] = "solar_farm"
        new_asset["asset_type"] = "undeveloped_parcel"
        new_asset["_is_interim"] = True

    return new_asset


def _apply_repurpose(asset: dict, params: dict, intervention: dict) -> None:
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

    if "new_capacity" in params:
        asset["capacity"] = params["new_capacity"]

    delta = intervention.get("opex_delta_rm") or 0
    if _is_number(asset.get("opex_annual_rm")):
        asset["opex_annual_rm"] = float(asset["opex_annual_rm"]) + float(delta)


def _apply_retrofit(asset: dict, params: dict, intervention: dict) -> None:
    delta = intervention.get("capex_delta_rm") or 0
    if _is_number(asset.get("capex_initial_rm")):
        asset["capex_initial_rm"] = float(asset["capex_initial_rm"]) + float(delta)

    if _is_number(asset.get("maintenance_annual_rm")):
        asset["maintenance_annual_rm"] = float(asset["maintenance_annual_rm"]) * 0.8

    gain = 0.15
    try:
        if "energy_efficiency_gain" in params:
            gain = float(params["energy_efficiency_gain"])
    except (TypeError, ValueError):
        pass
    gain = max(0.0, min(0.90, gain))
    asset["_energy_efficiency_multiplier"] = 1.0 - gain


def apply_construction_state(asset: dict, status: str) -> dict:
    new_asset = dict(asset)
    new_asset["_construction_status"] = status
    return new_asset


def _is_number(v) -> bool:
    if v is None:
        return False
    try:
        return not math.isnan(float(v))
    except (TypeError, ValueError):
        return False