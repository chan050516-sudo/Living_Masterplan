"""Commercial asset derived metrics.

Phase 11 additions:
  - Energy sub-system split.
  - Productive vs stranded carbon.
  - Life-cycle carbon (embodied amortised + maintenance).
  - UHI surface temperature proxy.

Phase B.2 — per-subtype breakdown
  - Reads `unit_mix_json` from the asset row.
  - Computes per-subtype DSR, occupancy, energy, carbon.
  - Emits `*_by_subtype_json` fields alongside the aggregate
    total, which remains unchanged for backwards compatibility.
  - Falls back to a single-subtype treatment when the asset has no
    unit_mix (small shoplots under 600 m² lettable).
"""

import json
import math
from .. import __version__
from .context import DerivationContext
from ..taxonomy import (
    get_subtype_or_default,
    default_subtype_for,
    get_energy_intensity,
)
from .demand_mismatch import demographic_mismatch
from .environmental import (
    energy_from_subtype,
    operational_carbon,
    shade_proxy_score_from_canopy,
    breakdown_energy,
    apply_canopy_hvac_relief,
    productive_stranded_carbon,
    embodied_amortised,
    maintenance_carbon_annual,
    calculate_surface_temp_delta,
    MATERIAL_INTENSITY_NEW_BUILD,
    MATERIAL_INTENSITY_REPURPOSE,
    embodied_amortised_for_subtype,
    canopy_growth,
)


def derive_commercial(ctx: DerivationContext) -> dict:
    asset = ctx.asset
    year = ctx.year
    assumptions = ctx.assumptions

    subtype = asset.get("subtype") or default_subtype_for(asset.get("asset_type"))
    subtype_cfg = get_subtype_or_default(subtype)

    raw = _get_metric_row(ctx, asset["asset_id"], year)

    def _get(col):
        v = raw.get(col) if raw is not None else None
        if v is None:
            return None
        try:
            if math.isnan(float(v)):
                return None
        except (TypeError, ValueError):
            return None
        return float(v)

    # --- Occupancy / vacancy ---
    occupancy = _get("occupancy_rate")
    vacancy_rate = (1.0 - occupancy) if occupancy is not None else None
    vacancy_duration = _get("vacancy_duration_months")

    # --- Maintenance surge ---
    completion_year = asset.get("completion_year")
    maintenance_base = asset.get("maintenance_annual_rm")
    maintenance_surge = None
    if maintenance_base is not None and completion_year is not None and not _isnan(maintenance_base):
        alpha = assumptions.get("asset_aging", {}).get("alpha", 0.03)
        years_old = max(0, year - int(completion_year))
        maintenance_surge = float(maintenance_base) * (1.0 + alpha) ** years_old
    ctx_maintenance = maintenance_surge or maintenance_base

    # --- NOI ---
    rental_income = _get("rental_income_rm")
    opex = asset.get("opex_annual_rm")
    noi = None
    if rental_income is not None and opex is not None and ctx_maintenance is not None:
        try:
            noi = rental_income - float(opex) - float(ctx_maintenance)
        except (TypeError, ValueError):
            noi = None

    capex = asset.get("capex_initial_rm")
    noi_yield = None
    if noi is not None and capex is not None and float(capex) > 0:
        noi_yield = noi / float(capex)

    # --- Per-subtype structure (Phase B.2) ---
    unit_mix = _parse_unit_mix(asset.get("unit_mix_json"))
    huff_by_subtype = ctx.huff_by_subtype or {}
    total_demand_m2 = (
        sum(huff_by_subtype.values())
        if huff_by_subtype
        else ctx.huff_effective_demand_m2
    )
    effective_supply = asset.get("lettable_area_m2")

    dsr = None
    if (total_demand_m2 is not None
            and effective_supply is not None
            and float(effective_supply) > 0):
        dsr = total_demand_m2 / float(effective_supply)

    demand_by_subtype_json = None
    if huff_by_subtype:
        demand_by_subtype_json = json.dumps(
            {k: round(v, 4) for k, v in huff_by_subtype.items()}
        )

    # DSR per subtype: uses each subtype's own area, not the whole
    # lettable. A mall's supermarket and F&B shops are competing in
    # independent Huff pools with different competition radii, so
    # their DSRs are not comparable to each other.
    dsr_by_subtype = _compute_dsr_by_subtype(
        unit_mix, huff_by_subtype, subtype, effective_supply,
    )

    # Occupancy per subtype: prefer the observed values from
    # asset_metrics occupancy_by_subtype_json; fall back to the
    # aggregate occupancy split deterministically.
    occupancy_by_subtype = _resolve_occupancy_by_subtype(
        unit_mix, occupancy, subtype,
        observed_json=_get_str("occupancy_by_subtype_json", raw),
    )

    # --- Rental income per visit (proxy) ---
    footfall = _get("footfall_daily")
    rental_income_per_visit = None
    if rental_income is not None and footfall and footfall > 0:
        rental_income_per_visit = rental_income / (footfall * 365.0)

    # --- Accessibility ---
    walking = ctx.walking_profile or {}
    driving = ctx.driving_profile or {}

    # --- Shade proxy ---
    shade = shade_proxy_score_from_canopy(ctx.canopy_coverage)

    # --- Energy / carbon (Phase B.2 — per-subtype) ---
    floor_area = float(asset.get("floor_area_m2") or 0.0)

    energy_by_subtype = _compute_energy_by_subtype(
        unit_mix, subtype, floor_area,
    )

    # Apply energy breakdown + canopy HVAC relief per subtype, then
    # recombine. The breakdown shares are asset_type-level
    # ("commercial"), so every subtype uses the same split — only
    # the base kWh differ.
    emission_factor = assumptions.get("environmental", {}).get(
        "emission_factor_energy", 0.58,
    )

    energy_kwh_adjusted = 0.0
    energy_hvac_total = 0.0
    energy_lighting_total = 0.0
    energy_base_total = 0.0
    carbon_total = 0.0
    carbon_by_subtype = {}

    for st, st_energy in energy_by_subtype.items():
        bd = breakdown_energy(st_energy, "commercial", assumptions)
        hvac_adj = apply_canopy_hvac_relief(
            bd["hvac_kwh"], ctx.canopy_coverage,
        )
        st_energy_adj = (
            hvac_adj
            + bd["lighting_equipment_kwh"]
            + bd["base_load_kwh"]
        )
        st_carbon = operational_carbon(st_energy_adj, emission_factor)

        energy_kwh_adjusted += st_energy_adj
        energy_hvac_total += hvac_adj
        energy_lighting_total += bd["lighting_equipment_kwh"]
        energy_base_total += bd["base_load_kwh"]
        carbon_total += st_carbon
        carbon_by_subtype[st] = round(st_carbon, 4)

    # If no unit_mix (small shop), this loop still runs with one
    # subtype key, so the totals are identical to the pre-B.2 logic.
    carbon = carbon_total
    hvac_adj = energy_hvac_total
    breakdown = {
        "hvac_kwh": energy_hvac_total,
        "lighting_equipment_kwh": energy_lighting_total,
        "base_load_kwh": energy_base_total,
    }

    # Phase 11 — productive vs stranded (total-level, unchanged)
    split = productive_stranded_carbon(carbon, occupancy)

    # Phase 11 — life-cycle (subtype-level; uses primary subtype)
    amortised = embodied_amortised_for_subtype(floor_area, subtype)
    maint_carbon = maintenance_carbon_annual(amortised["embodied_carbon_total_tco2e"])

    # Phase 11 — UHI proxy with OSM-data fallback
    from .environmental import effective_canopy_for_uhi
    canopy_for_uhi = effective_canopy_for_uhi(ctx.canopy_coverage, "commercial")
    uhi = calculate_surface_temp_delta(
        canopy_coverage_ratio=canopy_for_uhi,
        is_hard_surface=True,
    )

    # --- Demographic mismatch ---
    mismatch = None
    if ctx.catchment_population_profile:
        target_demographics = subtype_cfg.get("target_demographics", []) or []
        mismatch = demographic_mismatch(ctx.catchment_population_profile, target_demographics)

    diversity = ctx.neighborhood_diversity

    return {
        "asset_id": asset["asset_id"],
        "year": year,
        "subtype": subtype,
        "occupancy_rate": occupancy,
        "vacancy_rate": vacancy_rate,
        "vacancy_duration_months": vacancy_duration,
        "footfall_daily": footfall,
        "rental_income_per_visit_proxy": rental_income_per_visit,
        "rental_income_rm": rental_income,
        "noi_rm": noi,
        "noi_yield": noi_yield,
        "maintenance_surge_rm": maintenance_surge,
        "effective_demand": ctx.huff_effective_demand,
        "effective_demand_m2": total_demand_m2,
        "effective_demand_by_subtype_json": demand_by_subtype_json,
        "effective_supply": effective_supply,
        "dsr": dsr,
        "dsr_by_subtype_json": _json_or_none(dsr_by_subtype),
        "occupancy_by_subtype_calc_json": _json_or_none(occupancy_by_subtype),
        "energy_by_subtype_json": _json_or_none(energy_by_subtype),
        "carbon_by_subtype_json": _json_or_none(carbon_by_subtype),
        "shade_proxy_score": shade,
        "energy_kwh": energy_kwh_adjusted,
        "energy_kwh_hvac": hvac_adj,
        "energy_kwh_lighting_equipment": breakdown["lighting_equipment_kwh"],
        "energy_kwh_base_load": breakdown["base_load_kwh"],
        "carbon_operational_tco2e": carbon,
        "carbon_productive_tco2e": split["carbon_productive_tco2e"],
        "carbon_stranded_tco2e": split["carbon_stranded_tco2e"],
        "stranded_carbon_ratio": split["stranded_carbon_ratio"],
        "embodied_carbon_total_tco2e": amortised["embodied_carbon_total_tco2e"],
        "embodied_carbon_amortised_tco2e": amortised["embodied_carbon_amortised_tco2e"],
        "maintenance_carbon_tco2e": maint_carbon,
        "surface_temp_delta_c": uhi,
        "demographic_mismatch": mismatch,
        "neighborhood_diversity": diversity,
        "accessibility_score": ctx.accessibility_score,
        "metric_source": "derived",
        "model_version": __version__,
    }


# ---------------------------------------------------------------
# Phase B.2 — helpers
# ---------------------------------------------------------------

def _parse_unit_mix(raw):
    """Parse `unit_mix_json` into a dict, or None when the asset has
    no mix."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw or None
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and obj:
            return obj
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return None


def _get_str(col, raw):
    """Read a string-valued column safely (NaN / None -> None)."""
    v = raw.get(col) if raw is not None else None
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    try:
        if not v:
            return None
    except (TypeError, ValueError):
        pass
    return str(v)


def _json_or_none(d):
    if not d:
        return None
    try:
        return json.dumps(d)
    except (TypeError, ValueError):
        return None


def _compute_dsr_by_subtype(unit_mix, huff_by_subtype, fallback_subtype,
                            effective_supply):
    """
    Compute per-subtype DSR.

    Each subtype's DSR uses its OWN area (not the whole lettable),
    because a mall's supermarket and F&B shops compete in independent
    Huff pools with different competition radii.
    """
    if not unit_mix:
        # Single-subtype asset — one DSR entry keyed by its own subtype.
        if huff_by_subtype and fallback_subtype:
            st_demand = huff_by_subtype.get(fallback_subtype)
            if st_demand is not None and effective_supply:
                try:
                    return {
                        fallback_subtype:
                            round(st_demand / float(effective_supply), 4)
                    }
                except (TypeError, ValueError, ZeroDivisionError):
                    pass
        return {}

    out = {}
    for st, info in unit_mix.items():
        st_area = float(info.get("area_m2") or 0)
        st_demand = huff_by_subtype.get(st)
        if st_area > 0 and st_demand is not None:
            out[st] = round(st_demand / st_area, 4)
    return out


def _resolve_occupancy_by_subtype(unit_mix, total_occupancy, subtype,
                                   observed_json=None):
    """
    Resolve per-subtype occupancy.

    Priority:
      1. Observed values (from asset_metrics occupancy_by_subtype_json).
      2. Derived from the total occupancy, with a deterministic spread
         across subtypes seeded on the subtype name.

    A single-subtype asset gets a one-entry dict keyed by its own
    subtype, equal to the aggregate occupancy.
    """
    if observed_json:
        try:
            obs = json.loads(observed_json)
            if isinstance(obs, dict) and obs:
                return {k: round(float(v), 4) for k, v in obs.items()}
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    if not unit_mix:
        if total_occupancy is not None:
            return {subtype: round(float(total_occupancy), 4)}
        return {}

    if total_occupancy is None:
        return {}

    out = {}
    base = float(total_occupancy)
    for st in unit_mix:
        h = sum(ord(c) for c in st) % 100
        offset = (h - 50) / 200.0  # in [-0.25, 0.25]
        v = max(0.0, min(1.0, base + offset))
        out[st] = round(v, 4)
    return out


def _compute_energy_by_subtype(unit_mix, subtype, floor_area):
    """
    Compute per-subtype raw energy (before breakdown / canopy relief).

    Each subtype uses its own energy intensity from taxonomy.yml.
    The unit_mix records lettable area, but energy intensity is
    defined per floor area (GFA). The mix area is scaled up to
    floor area so the total energy matches what the old single-
    subtype path computed from floor_area.
    """
    if not unit_mix:
        intensity = get_energy_intensity(subtype) or 120.0
        return {subtype: float(floor_area) * float(intensity)}

    total_mix_area = sum(
        float(info.get("area_m2") or 0) for info in unit_mix.values()
    )
    scale = 1.0
    if total_mix_area > 0 and floor_area and floor_area > 0:
        scale = float(floor_area) / total_mix_area

    out = {}
    for st, info in unit_mix.items():
        st_floor_area = float(info.get("area_m2") or 0) * scale
        if st_floor_area <= 0:
            continue
        intensity = get_energy_intensity(st) or 120.0
        out[st] = st_floor_area * float(intensity)
    return out


def _get_metric_row(ctx: DerivationContext, asset_id: str, year: int):
    metrics = ctx.business["asset_metrics"]
    row = metrics[
        (metrics["asset_id"] == asset_id) & (metrics["year"] == year)
    ]
    if row.empty:
        return None
    return row.iloc[0]


def _isnan(v) -> bool:
    try:
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return False