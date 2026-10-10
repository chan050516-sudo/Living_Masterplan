"""Apply interventions to an asset row, producing a transformed asset.

This is deterministic and does not touch scores directly.
Only modifies state attributes (asset_type, capacity, opex, energy, land use).
"""

import json
import logging

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
        target_type = params.get("to", "community_facility")
        new_asset["asset_type"] = target_type
        new_asset["land_use"] = target_type
        if "new_capacity" in params:
            new_asset["capacity"] = params["new_capacity"]
        # Opex shift
        delta = intervention.get("opex_delta_rm") or 0
        if new_asset.get("opex_annual_rm") is not None:
            new_asset["opex_annual_rm"] = float(new_asset["opex_annual_rm"]) + float(delta)

    elif itype == "retrofit":
        delta = intervention.get("capex_delta_rm") or 0
        if new_asset.get("capex_initial_rm") is not None:
            new_asset["capex_initial_rm"] = float(new_asset["capex_initial_rm"]) + float(delta)
        # Retrofit typically reduces maintenance by ~20%
        if new_asset.get("maintenance_annual_rm") is not None:
            new_asset["maintenance_annual_rm"] = float(new_asset["maintenance_annual_rm"]) * 0.8

    elif itype == "pedestrian_upgrade":
        # Handled in spatial layer, not on the asset row
        pass

    elif itype == "green_corridor":
        # Handled in spatial layer
        pass

    elif itype == "new_development":
        # Not applied to existing assets; handled by supply model
        pass

    elif itype == "delay_development":
        # Handled by supply model
        pass

    return new_asset


def apply_construction_state(asset: dict, status: str) -> dict:
    """
    During construction: reduce metrics to reflect unavailable/partial state.
    """
    new_asset = dict(asset)
    new_asset["_construction_status"] = status
    return new_asset