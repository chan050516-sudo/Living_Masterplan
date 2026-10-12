"""Apply interventions to an asset row, producing a transformed asset.

Phase 6 changes:
  - Repurpose reads `to_subtype` (a taxonomy key) from parameters.
    Falls back to mapping `to` (asset_type) to a default subtype.
  - Capacity / floor area / opex updates follow the subtype.
"""

import json
import logging

from ..taxonomy import get_subtype, get_asset_class

log = logging.getLogger(__name__)


# Default subtype when the intervention only specifies an asset_type.
# Used for backward compatibility with older parameters_json payloads.
DEFAULT_SUBTYPE_BY_ASSET_TYPE = {
    "commercial": "convenience_retail",
    "community_facility": "community_hall",
    "green_space": "park",
    "residential": "terrace",
    "undeveloped_parcel": "vacant",
}


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

    elif itype == "pedestrian_upgrade":
        # Handled in the spatial layer, not on the asset row.
        pass

    elif itype == "green_corridor":
        # Handled in the spatial layer.
        pass

    elif itype == "new_development":
        # Not applied to existing assets; handled by the supply model.
        pass

    elif itype == "delay_development":
        # Handled by the supply model.
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
    asset["land_use"] = asset["asset_type"]

    if "new_capacity" in params:
        asset["capacity"] = params["new_capacity"]

    delta = intervention.get("opex_delta_rm") or 0
    if asset.get("opex_annual_rm") is not None:
        asset["opex_annual_rm"] = float(asset["opex_annual_rm"]) + float(delta)


def _apply_retrofit(asset: dict, params: dict, intervention: dict) -> None:
    delta = intervention.get("capex_delta_rm") or 0
    if asset.get("capex_initial_rm") is not None:
        asset["capex_initial_rm"] = float(asset["capex_initial_rm"]) + float(delta)
    if asset.get("maintenance_annual_rm") is not None:
        asset["maintenance_annual_rm"] = float(asset["maintenance_annual_rm"]) * 0.8


def apply_construction_state(asset: dict, status: str) -> dict:
    """During construction: reduce metrics to reflect unavailable/partial state."""
    new_asset = dict(asset)
    new_asset["_construction_status"] = status
    return new_asset