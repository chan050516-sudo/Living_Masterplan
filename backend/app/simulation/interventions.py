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

    # Phase B.2b — repurpose changes what the asset IS. The old
    # unit_mix no longer describes it. Clear the mix so B4 does
    # not apply the old subtype structure to the new subtype.
    asset["unit_mix_json"] = None

    delta = intervention.get("opex_delta_rm") or 0
    if _is_number(asset.get("opex_annual_rm")):
        asset["opex_annual_rm"] = float(asset["opex_annual_rm"]) + float(delta)


def _apply_retrofit(asset: dict, params: dict, intervention: dict) -> None:
    """
    Apply a retrofit intervention.

    Supports two modes:

    1. Aggregate (legacy): `energy_efficiency_gain` applies a single
       multiplier to the whole building's energy.

    2. Per-subsystem (P1): `measure_breakdown` carries per-measure
       capex and energy gain, each mapped to one or more subsystems
       (hvac / lighting_equipment / base_load). The engine applies a
       per-subsystem multiplier.

    Capex resolution order:
      1. Sum of measure_breakdown[*].capex_rm
      2. params["capex_delta_rm"]
      3. intervention["capex_delta_rm"]
    """
    breakdown = params.get("measure_breakdown") or []

    # --- CAPEX ---
    capex_from_breakdown = 0.0
    if breakdown:
        for m in breakdown:
            try:
                capex_from_breakdown += float(m.get("capex_rm") or 0)
            except (TypeError, ValueError):
                continue

    if capex_from_breakdown > 0:
        capex_total = capex_from_breakdown
    else:
        capex_total = (
            params.get("capex_delta_rm")
            or intervention.get("capex_delta_rm")
            or 0.0
        )

    if _is_number(asset.get("capex_initial_rm")):
        asset["capex_initial_rm"] = (
            float(asset["capex_initial_rm"]) + float(capex_total)
        )

    # --- Maintenance reduction ---
    if _is_number(asset.get("maintenance_annual_rm")):
        asset["maintenance_annual_rm"] = (
            float(asset["maintenance_annual_rm"]) * 0.8
        )

    # --- Energy multipliers ---
    if breakdown:
        hvac_mult = 1.0
        lighting_mult = 1.0
        base_mult = 1.0

        for m in breakdown:
            gain = m.get("energy_gain")
            if gain is None:
                continue
            try:
                g = float(gain)
            except (TypeError, ValueError):
                continue
            g = max(0.0, min(0.9, g))

            affected = m.get("affected") or []
            if "hvac" in affected:
                hvac_mult *= (1.0 - g)
            if "lighting_equipment" in affected:
                lighting_mult *= (1.0 - g)
            if "base_load" in affected:
                base_mult *= (1.0 - g)

        asset["_hvac_multiplier"] = hvac_mult
        asset["_lighting_multiplier"] = lighting_mult
        asset["_base_multiplier"] = base_mult

        # Backward-compat aggregate (weighted by typical breakdown
        # shares: hvac 60%, lighting 25%, base 15%).
        asset["_energy_efficiency_multiplier"] = (
            0.60 * hvac_mult + 0.25 * lighting_mult + 0.15 * base_mult
        )
    else:
        gain = 0.15
        try:
            if "energy_efficiency_gain" in params:
                gain = float(params["energy_efficiency_gain"])
        except (TypeError, ValueError):
            pass
        gain = max(0.0, min(0.90, gain))
        asset["_energy_efficiency_multiplier"] = 1.0 - gain


def apply_construction_state(
    asset: dict,
    status: str,
    capacity_ratio: float = None,
) -> dict:
    """
    Marks the asset as under construction.

    This function does NOT modify occupancy. During construction the
    asset's operational capacity shrinks; the existing occupants do
    not disappear. The engine uses `_capacity_ratio` to constrain the
    effective service the asset can provide, while occupancy is
    tracked independently.

    Parameters
    ----------
    asset : dict
        The asset dict to clone and mark.
    status : str
        "unavailable" / "partial" / "operational".
    capacity_ratio : float | None
        Fraction of physical capacity usable during construction.
        When None, the caller has not supplied a value and the
        engine falls back to a status-only default (0.0 / 0.6 / 1.0).
    """
    new_asset = dict(asset)
    new_asset["_construction_status"] = status
    if capacity_ratio is not None:
        try:
            new_asset["_capacity_ratio"] = max(
                0.0, min(1.0, float(capacity_ratio))
            )
        except (TypeError, ValueError):
            pass
    return new_asset


def _is_number(v) -> bool:
    if v is None:
        return False
    try:
        return not math.isnan(float(v))
    except (TypeError, ValueError):
        return False