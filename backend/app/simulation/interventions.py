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

    elif itype == "renovation":
        _apply_renovation(new_asset, params, intervention)

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
    # Phase B.2c — partial repurpose.
    # If subtype_changes is present, we convert only specific
    # subtypes of a mixed-use asset, preserving the healthy ones.
    if params.get("subtype_changes"):
        _apply_partial_repurpose(
            asset, params["subtype_changes"], intervention,
        )
        return

    # ---- Existing full-repurpose path ----
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

    # Phase B.2b — full repurpose clears the old mix.
    asset["unit_mix_json"] = None

    delta = intervention.get("opex_delta_rm") or 0
    if _is_number(asset.get("opex_annual_rm")):
        asset["opex_annual_rm"] = float(asset["opex_annual_rm"]) + float(delta)


def _apply_partial_repurpose(
    asset: dict, changes: list, intervention: dict,
) -> None:
    """
    Convert a subset of a mixed-use asset's subtypes in place.

    Example: a 2,500 m² mall with unit_mix
        {"supermarket": 800, "f_and_b": 600,
         "services": 400, "medical_retail": 200}
    and a dead F&B floor. The plan says
        subtype_changes: [{from: "f_and_b", to: "clinic"}]

    Result:
        {"supermarket": 800, "clinic": 600,
         "services": 400, "medical_retail": 200}
    The primary subtype stays "supermarket" (largest area).
    asset_type remains "commercial" (validator guarantees this).

    B4 on the activation year re-reads unit_mix_json, sees the new
    mix, and builds supply nodes with the updated subtype
    breakdown. The Huff pool for "f_and_b" no longer receives
    this asset's 600 m², and the "clinic" pool now does. The
    aggregate Huff demand for the asset therefore shifts.

    Limitation (middle-ground design): occupancy is computed
    from the asset's AGGREGATE demand-to-supply ratio. There is
    no per-subtype occupancy. The justification must describe
    the change in aggregate terms.
    """
    raw = asset.get("unit_mix_json")
    if not raw:
        log.warning(
            "Partial repurpose on asset %s with no unit_mix; "
            "no-op.",
            asset.get("asset_id"),
        )
        return
    try:
        mix = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (json.JSONDecodeError, TypeError):
        log.warning(
            "Could not parse unit_mix_json on %s; partial repurpose "
            "skipped.",
            asset.get("asset_id"),
        )
        return
    if not isinstance(mix, dict) or not mix:
        return

    working = {}
    for st, info in mix.items():
        if not isinstance(info, dict):
            continue
        working[st] = {
            "area_m2": float(info.get("area_m2") or 0.0),
            "count": int(info.get("count") or 1),
        }

    for ch in changes:
        if not isinstance(ch, dict):
            continue
        from_st = ch.get("from_subtype")
        to_st = ch.get("to_subtype")
        if not from_st or not to_st or from_st not in working:
            continue
        if to_st == from_st:
            continue

        from_area = working[from_st]["area_m2"]
        from_count = working[from_st]["count"]
        if from_area <= 0:
            continue

        requested = ch.get("area_m2")
        if requested is None:
            converted_area = from_area
        else:
            try:
                req = float(requested)
            except (TypeError, ValueError):
                req = from_area
            converted_area = min(max(0.0, req), from_area)

        if converted_area <= 0:
            continue

        ratio = converted_area / from_area
        converted_count = max(
            0, int(round(from_count * ratio)),
        ) if ratio < 1.0 else from_count
        if converted_area > 0 and converted_count == 0:
            converted_count = 1  # always at least one unit of the target

        working[from_st]["area_m2"] = from_area - converted_area
        working[from_st]["count"] = from_count - converted_count

        if to_st not in working:
            working[to_st] = {"area_m2": 0.0, "count": 0}
        working[to_st]["area_m2"] += converted_area
        working[to_st]["count"] += converted_count

    # Drop empty entries.
    cleaned = {
        st: info for st, info in working.items()
        if info["area_m2"] > 0.5 and info["count"] > 0
    }
    if not cleaned:
        return

    primary = max(cleaned, key=lambda k: cleaned[k]["area_m2"])

    out = {
        st: {
            "area_m2": round(info["area_m2"], 1),
            "count": int(info["count"]),
        }
        for st, info in cleaned.items()
    }
    asset["unit_mix_json"] = json.dumps(out)
    asset["subtype"] = primary
    # asset_type is preserved — the validator rejects any change
    # that would flip the primary subtype's asset_class.

    delta = intervention.get("opex_delta_rm") or 0
    if _is_number(asset.get("opex_annual_rm")):
        asset["opex_annual_rm"] = (
            float(asset["opex_annual_rm"]) + float(delta)
        )


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


def _apply_renovation(asset: dict, params: dict, intervention: dict) -> None:
    """
    Same-class subtype change. No structural demolition,
    no change of asset_type, no clearing of unit_mix or
    floor area. Used for terrace → affordable_housing,
    convenience_retail → f_and_b, community_hall → library.

    The asset's physical shell is unchanged; what changes
    is the target demographic and the operational profile.
    """
    new_subtype = params.get("to_subtype")
    if new_subtype is None:
        return
    subtype_def = get_subtype(new_subtype)
    if subtype_def is None:
        return
    # Only change subtype — leave asset_type, capacity,
    # floor_area, lettable_area, unit_mix, unit_count intact.
    asset["subtype"] = new_subtype
    delta = intervention.get("opex_delta_rm") or 0
    if _is_number(asset.get("opex_annual_rm")):
        asset["opex_annual_rm"] = (
            float(asset["opex_annual_rm"]) + float(delta)
        )


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