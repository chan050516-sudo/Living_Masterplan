"""B4 — Future state simulation engine.

Phase 5 changes:
  - Uses per-subtype Huff (m2 demand) matching B3.
  - Carbon uses subtype-aware energy intensity from taxonomy.
  - Post-intervention facility occupancy is driven by the LLM
    expectation (expected_derived_json) when present, otherwise by the
    subtype utilisation benchmark.
  - Comparison metric keys are chosen per effective asset type
    (utilisation_rate for facilities, occupancy_rate for commercial).
  - Adds township-level metrics to the comparison block.

Phase 6 changes:
  - Uses the same entry-point pipeline as B3 (find_entry_point +
    insert_all_entries) so that base-year and simulated accessibility
    numbers are directly comparable.

Phase 7 changes:
  - Commercial assets without an activated intervention hold their
    previous occupancy instead of converging to a Huff-derived target.
  - Repurpose transitions clear type-exclusive fields so the
    comparison block shows N/A instead of a misleading zero.
  - write_scenario_result() sanitises NaN before serialising.

Phase 8 changes:
  - New development projects (development_projects.csv) are now
    first-class citizens of the simulation.
  - Township metrics report project carbon separately.
  - map_diff gains a "project_schedule" block.

Phase 9 changes:
  - simulate_scenario() accepts selected_ids.

Phase 10 (Circular & Planet fixes):
  - Integrates Avoided Embodied Carbon into the comparison block.
  - Carries observed Landsat 8 Level-2 surface temperatures into scenarios.
  - Supports interim_solar_farm for generating clean energy offsets.

Phase 11 (2026-10-16):
  - Productive vs stranded carbon split in every year's state row.
  - Energy sub-system breakdown (HVAC / lighting / base load) with
    canopy-based HVAC relief.
  - Parcel temperatures remain tied to the Landsat observation
    baseline; canopy changes do not manufacture temperature values.
  - _add_project_state records embodied carbon for new construction.
"""

import json
import logging
import math
from pathlib import Path

import networkx as nx
import pandas as pd

from .. import __version__
from ..config import load_paths, load_assumptions
from ..derived.engine import compute_derived_metrics
from ..derived.network_graph import (
    build_walk_graph,
    extract_nodes,
    find_entry_point,
    find_nearest_node,
    insert_all_entries,
)
from ..derived.huff import huff_gravity_by_subtype
from ..derived.environmental import (
    energy_from_subtype,
    operational_carbon,
    breakdown_energy,
    apply_canopy_hvac_relief,
    productive_stranded_carbon,
    embodied_amortised,
    maintenance_carbon_annual,
    interim_solar_generation,
    canopy_growth,
    embodied_carbon_for_subtype,
    MATERIAL_INTENSITY_NEW_BUILD,
    MATERIAL_INTENSITY_REPURPOSE,
    DEMOLITION_CARBON_INTENSITY,
)
from ..derived.thermal import THERMAL_METRIC_FIELDS
from ..taxonomy import (
    get_taxonomy,
    get_occupancy_benchmark,
    get_energy_intensity,
    default_subtype_for,
    get_subtype,
)
from .time_anchors import resolve_phase, interventions_for_asset, Phase
from .interventions import apply_intervention, apply_construction_state
from .population import project_population
from .occupancy import damped_occupancy, target_occupancy_from_dsr
from .supply import active_projects_in_year
from .spatial import (
    spatial_interventions_for_year,
    network_version_tag,
    apply_spatial_interventions,
)

log = logging.getLogger(__name__)


DEFAULT_YEARS = [2026, 2027, 2028, 2030, 2033]

# Prefix for project pseudo-entries in state_by_year.
PROJECT_ID_PREFIX = "PRJ::"

# The "do nothing" baseline scenario used for project schedule deltas.
BASELINE_SCENARIO_ID = "SC-CURRENT"


# ------------------------------------------------------------------
# Asset-type field ownership
# ------------------------------------------------------------------
_TYPE_EXCLUSIVE_FIELDS = {
    "commercial": frozenset({
        "occupancy_rate",
        "vacancy_rate",
        "vacancy_duration_months",
        "footfall_daily",
        "rental_income_per_visit_proxy",
        "rental_income_rm",
        "noi_rm",
        "noi_yield",
        "maintenance_surge_rm",
        "dsr",
        "effective_supply",
        # Phase 11 — carbon ledger fields owned by every type
        "energy_kwh_hvac",
        "energy_kwh_lighting_equipment",
        "energy_kwh_base_load",
        "carbon_productive_tco2e",
        "carbon_stranded_tco2e",
        "stranded_carbon_ratio",
        "embodied_carbon_total_tco2e",
        "embodied_carbon_amortised_tco2e",
        "maintenance_carbon_tco2e",
        "surface_temp_delta_c",
    }),
    "residential": frozenset({
        "occupancy_rate",
        "vacancy_rate",
        "noi_rm",
        "energy_intensity_kwh_m2",
        "energy_kwh_hvac",
        "energy_kwh_lighting_equipment",
        "energy_kwh_base_load",
        "carbon_productive_tco2e",
        "carbon_stranded_tco2e",
        "stranded_carbon_ratio",
        "embodied_carbon_total_tco2e",
        "embodied_carbon_amortised_tco2e",
        "maintenance_carbon_tco2e",
        "surface_temp_delta_c",
    }),
    "community_facility": frozenset({
        "utilisation_rate",
        "service_coverage",
        "cost_per_user_rm",
        "energy_kwh_hvac",
        "energy_kwh_lighting_equipment",
        "energy_kwh_base_load",
        "carbon_productive_tco2e",
        "carbon_stranded_tco2e",
        "stranded_carbon_ratio",
        "embodied_carbon_total_tco2e",
        "embodied_carbon_amortised_tco2e",
        "maintenance_carbon_tco2e",
        "surface_temp_delta_c",
    }),
    "green_space": frozenset({
        "green_coverage",
        "canopy_coverage",
        "canopy_ratio_benchmark",
        "green_per_capita_m2",
        "shade_proxy_score",
        "surface_temp_delta_c",
        "embodied_carbon_total_tco2e",
        "maintenance_carbon_tco2e",
    }),
    "undeveloped_parcel": frozenset({
        "developable_area_m2",
        "potential_gfa_m2",
        "demand_supply_gap",
        "infrastructure_cost_rm",
        "surface_temp_delta_c",
        "embodied_carbon_total_tco2e",
    }),
}

_ALL_TYPE_EXCLUSIVE_FIELDS = frozenset().union(*_TYPE_EXCLUSIVE_FIELDS.values())

_DEMAND_CHANGE_THRESHOLD = 0.05

# Absolute floor for the demand-change test.
#
# The relative threshold alone misfires on multi-year simulation gaps.
# The simulation year list is non-uniform: 2027→2028 is 1 year,
# 2030→2033 is 3 years. Population growth compounds across the gap,
# so a 3-year step easily produces a +6% demand shift on every asset
# — not because the market changed, but because the population grew.
# That false positive triggers Huff re-convergence for every
# commercial asset and collapses their occupancy.
#
# Require BOTH a relative change above the threshold AND an absolute
# change of at least this many m².
_DEMAND_CHANGE_ABSOLUTE_FLOOR_M2 = 100.0

# Default access-to-use conversion. Used when
# assumptions.huff.access_to_use_conversion is absent.
_DEFAULT_ACCESS_TO_USE_CONVERSION = 0.2

_SPATIAL_REFRESH_FIELDS = (
    "catchment_population_5min_walk",
    "catchment_population_10min_walk",
    "catchment_population_15min_walk",
    "coverage_ratio_5min_walk",
    "coverage_ratio_10min_walk",
    "coverage_ratio_15min_walk",
    "mean_walk_distance_m",
    "median_walk_distance_m",
    "p90_walk_distance_m",
    "reachable_population_walk",
    "total_catchment_population",
    "catchment_population_5min_drive",
    "catchment_population_10min_drive",
    "catchment_population_15min_drive",
    "coverage_ratio_5min_drive",
    "coverage_ratio_10min_drive",
    "coverage_ratio_15min_drive",
    "mean_drive_distance_m",
    "median_drive_distance_m",
    "p90_drive_distance_m",
    "reachable_population_drive",
    "accessibility_score",
    "service_coverage",
)


def _compute_distance_matrix(G, cutoff_m=5000.0):
    """
    All-pairs shortest path using effective_length_m, bounded by
    `cutoff_m`.

    Must use the same cutoff as `accessibility.compute_distance_matrix`
    so B3's baseline and B4's simulated states are directly
    comparable pair-for-pair. At a township scale every meaningful
    path is under 5 km; a pair whose actual path exceeds the cutoff
    falls back to the Huff FALLBACK_DISTANCE_M (1500 m) inside
    `huff_gravity_by_subtype`, which is a conservative overestimate
    and does not distort competition shares.
    """
    return dict(nx.all_pairs_dijkstra_path_length(
        G, cutoff=cutoff_m, weight="effective_length_m",
    ))


def _is_valid_number(v) -> bool:
    """True if v is a finite float (not None, not NaN)."""
    if v is None:
        return False
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    return not math.isnan(f)


def _seeded_uniform(key: str, lo: float, hi: float) -> float:
    """
    Deterministic pseudo-random float in [lo, hi].

    Phase D.2 — mirrors the seeded_uniform used by build_mock_data so
    the same key yields the same value. Keeps the sell-off rate per
    asset stable across repeated B4 runs of the same scenario.
    """
    import hashlib
    h = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16)
    u = (h % 10_000_000) / 10_000_000.0
    return lo + (hi - lo) * u


def _is_lease_active_at(lease, year):
    """
    True if the lease is still running at year Y, accounting for the
    tenant's RENEWAL probability.

    Phase D.2 fix — the model originally treated every expiring
    lease as "tenant leaves". A mall with six 2-5 year leases then
    cascaded from 0.86 occupancy to 0.15 over seven years, which is
    too pessimistic. In real townships 70-80% of commercial tenants
    renew.

    A lease that expired at year E is active at year Y if the tenant
    renewed every 3-year term from E to Y. Renewal probability is
    0.75 per term; the renewal decision is seeded on
    (lease_id, current_end) so it is stable across runs.
    """
    status = lease.get("lease_status")
    if status == "never_leased":
        return False

    end = lease.get("lease_end_year")
    if end is None:
        return status in ("active", "expired")
    try:
        end = int(end)
    except (TypeError, ValueError):
        return status in ("active", "expired")

    if year <= end:
        return status in ("active", "expired")

    # Lease has expired at `end`. Simulate the renewal chain
    # forward to see whether the tenant is still there at `year`.
    lease_id = lease.get("lease_id", "?")
    current_end = end
    term = 3
    for _ in range(10):  # safety cap
        if current_end >= year:
            return True
        u = _seeded_uniform(
            f"{lease_id}-renewal-{current_end}", 0.0, 1.0,
        )
        if u > 0.75:
            return False  # tenant did not renew this term
        current_end += term
    return True


def _compute_lease_target_occupancy(leases_df, asset_id, year):
    """
    Occupancy implied by the lease schedule for a given year.

    Each lease that is still active at `year` — accounting for
    renewal probability via `_is_lease_active_at` — contributes its
    floor area to the active total. The result is the fraction of
    the asset's leased area that can possibly be occupied. Huff
    decides where within this ceiling the actual occupancy sits.
    """
    if leases_df is None or leases_df.empty:
        return None
    asset_leases = leases_df[leases_df["asset_id"] == asset_id]
    if asset_leases.empty:
        return None

    total_area = 0.0
    active_area = 0.0
    for _, lease in asset_leases.iterrows():
        area = float(lease.get("floor_area_m2") or 0)
        if area <= 0:
            continue
        total_area += area
        if _is_lease_active_at(lease, year):
            active_area += area

    if total_area <= 0:
        return None
    return active_area / total_area


def _compute_developer_held_decay(asset_row, year, base_year):
    """
    Phase D.2 — simulate the developer selling off unsold inventory.

    Uses a cumulative decay formula, not an iterative one.

    Why: with 2 held units and a 0.15 sell rate, the iterative
    formula `round(remaining * (1 - rate))` computes
    round(2 * 0.85) = round(1.7) = 2 every year. The remainder
    never clears, so a 2-unit unsold inventory is indistinguishable
    from a 0-unit one after five years.

    The cumulative formula computes the total remaining after all
    years at once: 2 * 0.85^7 = 0.64, round(0.64) = 1 at year 7,
    round(0.32) = 0 at year 8. The inventory shrinks monotonically
    as it should.
    """
    base_held = asset_row.get("developer_held_units")
    if base_held is None:
        return 0, 0
    try:
        base_held = int(float(base_held))
    except (TypeError, ValueError):
        return 0, 0
    if base_held <= 0:
        return 0, 0

    years_since_base = max(0, year - base_year)
    if years_since_base <= 0:
        return base_held, 0

    aid = asset_row.get("asset_id", "?")
    sell_rate = _seeded_uniform(f"{aid}-sell", 0.10, 0.20)

    remaining = base_held * ((1.0 - sell_rate) ** years_since_base)
    remaining = int(round(remaining))
    if remaining < 0:
        remaining = 0
    if remaining > base_held:
        remaining = base_held

    return remaining, base_held - remaining


def _parse_unit_mix_engine(raw):
    """Parse unit_mix_json; NaN-safe."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw or None
    try:
        if pd.isna(raw):
            return None
    except (TypeError, ValueError):
        pass
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and obj:
            return obj
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return None


def _weak_coupling_occupancy(
    prev_occ,
    prev_demand,
    curr_demand,
    effective_supply,
    conversion=0.25,
):
    """
    Adjust occupancy by a fraction of the change in Huff share.

    The Huff gravity model is a zero-sum allocation: a fixed total
    demand is redistributed across competing assets according to
    attractiveness ÷ distance². When the walking network changes or a
    competitor delivers, the re-allocation is real, but the change in
    the asset's *accessibility* does not translate 1:1 into a change
    in its *occupancy*. Being easier to reach does not mean a
    customer will change their behaviour.

    Cervero (2002) and Ewing & Cervero (2010) show that a fractional
    change in accessibility converts to a much smaller fractional
    change in actual use — the meta-analytic range is 15-35%, with
    ~25% as the mid-point.

    This function therefore scales the occupancy response by
    `conversion`, so a +12.7% Huff share change becomes a +3.2%
    occupancy change, not a jump-to-target behaviour that collapses
    occupancy when the mock initial value differs from the Huff
    target.

    Parameters
    ----------
    prev_occ : float
        Occupancy before this year's adjustment.
    prev_demand : float | None
        Huff-assigned demand (m²) in the previous simulated year.
    curr_demand : float | None
        Huff-assigned demand (m²) in the current simulated year.
    effective_supply : float
        Lettable area or capacity used to normalise demand into a
        demand-to-supply ratio.
    conversion : float
        Fraction of the Huff share change that translates to an
        occupancy change. Default 0.25.

    Returns
    -------
    float : the new occupancy target, clipped to [0.05, 0.98].
    """
    if (prev_demand is None or curr_demand is None
            or float(prev_demand) <= 0
            or effective_supply is None
            or float(effective_supply) <= 0):
        return prev_occ
    try:
        prev_dsr = float(prev_demand) / float(effective_supply)
        curr_dsr = float(curr_demand) / float(effective_supply)
    except (TypeError, ValueError, ZeroDivisionError):
        return prev_occ
    if prev_dsr <= 0:
        return prev_occ

    share_change = (curr_dsr - prev_dsr) / prev_dsr
    new_occ = prev_occ * (1.0 + share_change * conversion)
    return max(0.05, min(0.98, new_occ))


def _recompute_commercial_financials(
    metric_row: dict,
    eff: dict,
    aid: str,
    year: int,
    new_occ: float,
    state_by_year: dict,
    base_year: int,
    assumptions: dict,
) -> None:
    """
    Mutates `metric_row` in place to reflect the current occupancy.

    Rental income and footfall scale linearly with the occupancy
    ratio. Maintenance is recomputed with the aging factor. NOI and
    NOI yield follow.
    """
    baseline = state_by_year.get(base_year, {}).get(aid, {})
    base_occ = baseline.get("occupancy_rate")
    base_rental = baseline.get("rental_income_rm")
    base_footfall = baseline.get("footfall_daily")

    if not _is_valid_number(base_occ) or float(base_occ) <= 0:
        return
    if not _is_valid_number(base_rental):
        return

    ratio = float(new_occ) / float(base_occ)
    scaled_rental = float(base_rental) * ratio
    metric_row["rental_income_rm"] = scaled_rental

    if _is_valid_number(base_footfall):
        scaled_footfall = float(base_footfall) * ratio
        metric_row["footfall_daily"] = scaled_footfall
        if scaled_footfall > 0:
            metric_row["rental_income_per_visit_proxy"] = (
                scaled_rental / (scaled_footfall * 365.0)
            )
        else:
            metric_row["rental_income_per_visit_proxy"] = None

    maintenance_base = eff.get("maintenance_annual_rm")
    completion_year = eff.get("completion_year")
    maintenance_current = None
    if _is_valid_number(maintenance_base):
        alpha = assumptions.get("asset_aging", {}).get("alpha", 0.03)
        if _is_valid_number(completion_year):
            years_old = max(0, year - int(completion_year))
        else:
            years_old = 0
        maintenance_current = float(maintenance_base) * (1.0 + alpha) ** years_old
    metric_row["maintenance_surge_rm"] = maintenance_current

    opex = eff.get("opex_annual_rm")
    opex_f = float(opex) if _is_valid_number(opex) else 0.0
    maint_f = maintenance_current if maintenance_current is not None else 0.0
    noi = scaled_rental - opex_f - maint_f
    metric_row["noi_rm"] = noi

    capex = eff.get("capex_initial_rm")
    if _is_valid_number(capex) and float(capex) > 0:
        metric_row["noi_yield"] = noi / float(capex)
    else:
        metric_row["noi_yield"] = None


def _synthesize_new_development_projects(
    scenario_interventions, assets_df, year,
) -> list:
    """
    Turn `new_development` interventions into virtual project entries.
    """
    if scenario_interventions is None or scenario_interventions.empty:
        return []

    synthesized = []
    for _, intv in scenario_interventions.iterrows():
        if intv.get("intervention_type") != "new_development":
            continue

        activation = intv.get("activation_year")
        if activation is None:
            continue
        try:
            if int(activation) > year:
                continue
        except (TypeError, ValueError):
            continue

        try:
            params = json.loads(intv.get("parameters_json") or "{}")
        except (json.JSONDecodeError, TypeError):
            params = {}

        gfa = params.get("target_gfa_m2") or params.get("new_gfa_m2")
        try:
            gfa = float(gfa or 0.0)
        except (TypeError, ValueError):
            gfa = 0.0
        if gfa <= 0:
            log.info(
                "new_development intervention %s has no target_gfa_m2; "
                "skipping project synthesis.",
                intv.get("intervention_id"),
            )
            continue

        target_asset = intv.get("target_asset_id")
        parcel_id = None
        if target_asset:
            match = assets_df[assets_df["asset_id"] == target_asset]
            if not match.empty:
                pid = match.iloc[0].get("parcel_id")
                if isinstance(pid, str) and pid:
                    parcel_id = pid

        to_subtype = params.get("to_subtype")
        if to_subtype:
            land_use = _subtype_to_land_use(to_subtype)
        else:
            land_use = params.get("to_land_use") or "commercial"

        project_id = intv.get("intervention_id") or f"NEWDEV-{target_asset or '?'}"

        synthesized.append({
            "project_id": project_id,
            "parcel_id": parcel_id,
            "asset_id": target_asset,
            "project_name": (
                f"LLM-proposed: {to_subtype or 'development'} on {target_asset}"
            ),
            "project_status": "proposed",
            "planned_start_year": int(activation),
            "planned_delivery_year": int(activation),
            "gfa_m2": gfa,
            "units": params.get("target_units"),
            "land_use": land_use,
            "capex_rm": intv.get("capex_delta_rm") or 0,
            "scenario_dependency": None,
            "subtype": to_subtype,
        })
    return synthesized


def _subtype_to_land_use(subtype: str) -> str:
    """Rough mapping from a taxonomy subtype to a land_use label."""
    defn = get_subtype(subtype)
    if defn is None:
        return "unknown"
    return defn.get("asset_class", "unknown")


def simulate_scenario(
    scenario_id: str,
    repo_root: Path = None,
    years: list = None,
    selected_ids: list = None,
    _shared_cache: dict = None,
) -> dict:
    """
    Returns a ScenarioResult dict per scenario_result.schema.json.

    If selected_ids is provided, the comparison block restricts to
    those assets. If None, every non-project asset is compared.

    Parameters
    ----------
    _shared_cache : dict, optional
        Cross-candidate cache. When multiple scenarios are simulated
        in the same run (e.g. the B7 multi-candidate pipeline), pass
        the same dict to every call. The heavy setup work — B3
        derived metrics, the geometry bundle, the walking pipeline —
        is computed once and reused. This is what makes N candidates
        affordable: N candidates pay one setup cost, not N.

        The cache is keyed on (repo_root, base_year). When either
        changes, the cache auto-invalidates and everything is
        recomputed.

        The cache is READ-ONLY with respect to the caller: it is
        populated on first use and reused thereafter. It is safe to
        keep alive across the whole run.

    Network versions
    ----------------
    A scenario may include spatial interventions (pedestrian_upgrade,
    green_corridor). These modify the walking network rather than any
    asset. B4 handles them by maintaining a per-run cache keyed on the
    set of active spatial interventions. Between candidate calls the
    cache is shared, so a network version built for one candidate is
    reused by any later candidate that uses the same interventions.
    """
    repo_root = repo_root or Path(__file__).resolve().parents[3]
    years = years or DEFAULT_YEARS
    base_year = years[0]

    # ---- Shared cache setup and validation ----
    if _shared_cache is None:
        _shared_cache = {}

    cache_key = (str(repo_root), base_year)
    if _shared_cache.get("_key") != cache_key:
        # Different repo_root or base_year — invalidate everything.
        _shared_cache.clear()
        _shared_cache["_key"] = cache_key

    paths = load_paths()
    assumptions = load_assumptions()
    taxonomy = get_taxonomy()
    subtypes_config = taxonomy.get("subtypes", {})

    base = repo_root / paths["base"]

    # ---- Cached: static CSV frames (assets / projects) ----
    if "assets_df" in _shared_cache and "projects_df" in _shared_cache:
        assets_df = _shared_cache["assets_df"]
        projects_df = _shared_cache["projects_df"]
    else:
        assets_df = pd.read_csv(base / "business" / "assets.csv")
        projects_df = pd.read_csv(base / "business" / "development_projects.csv")
        _shared_cache["assets_df"] = assets_df
        _shared_cache["projects_df"] = projects_df

    # Phase D.1 — lease schedule. Loaded once and cached across
    # scenarios. Empty DataFrame when the file is absent so the
    # lease-bound logic degenerates to a no-op.
    if "leases_df" in _shared_cache:
        leases_df = _shared_cache["leases_df"]
    else:
        lease_path = base / "business" / "asset_leases.csv"
        if lease_path.exists():
            leases_df = pd.read_csv(lease_path)
        else:
            leases_df = pd.DataFrame()
        _shared_cache["leases_df"] = leases_df

    # interventions_df is NOT cached: the orchestrator appends rows
    # between candidate calls, and each scenario_id must see the
    # latest file state.
    interventions_df = pd.read_csv(base / "business" / "interventions.csv")

    scenario_interventions = interventions_df[
        interventions_df["scenario_id"] == scenario_id
    ]

    # ---- Cached: geometry bundle ----
    if "geometry" in _shared_cache:
        geometry = _shared_cache["geometry"]
    else:
        from ..loaders.geometry_loader import load_geometry
        geometry = load_geometry(repo_root, paths)
        _shared_cache["geometry"] = geometry

    # ---- Cached: B3 derived metrics (段 A) ----
    if "base_derived" in _shared_cache:
        base_derived = _shared_cache["base_derived"]
        log.debug(
            "Reusing cached B3 derived metrics for year %d", base_year,
        )
    else:
        log.info(
            "Computing B3 derived metrics for year %d "
            "(first candidate in this run)", base_year,
        )
        base_derived = compute_derived_metrics(
            repo_root=repo_root, year=base_year,
        )
        _shared_cache["base_derived"] = base_derived

    # ---- Population config ----
    pop_cfg = assumptions["population"]
    g_rate = pop_cfg["growth_rate"]["medium"]
    base_pop = float(pop_cfg["base_population"])

    alpha = assumptions["huff"]["alpha"]
    beta = assumptions["huff"]["beta"]

    lambda_ = assumptions.get("occupancy_dynamics", {}).get("lambda", 0.35)
    critical = assumptions.get("occupancy_dynamics", {}).get("critical_threshold")
    kappa = assumptions.get("occupancy_dynamics", {}).get("kappa", 0.0)

    emission_factor = assumptions.get("environmental", {}).get(
        "emission_factor_energy", 0.58,
    )

    # ------------------------------------------------------------------
    # Network version cache — shared across candidates (段 B)
    # ------------------------------------------------------------------
    if "_pipeline_cache" not in _shared_cache:
        _shared_cache["_pipeline_cache"] = {}
    _pipeline_cache = _shared_cache["_pipeline_cache"]

    def _get_pipeline(tag: str, active_spatial: list) -> dict:
        """
        Build or return the walking pipeline for a network version.

        On cache miss:
          - modify the network with the active spatial interventions
          - run B3 with the modified network (network_override)
          - rebuild the graph, virtual nodes, and distance matrix
        On cache hit: return the stored result.
        """
        if tag in _pipeline_cache:
            return _pipeline_cache[tag]

        if tag == "base":
            modified_network = None
            derived = base_derived
        else:
            log.info(
                "Building pipeline for network version %s "
                "(spatial interventions active; this may take a few seconds).",
                tag,
            )
            modified_network = apply_spatial_interventions(
                geometry["network"]["analysis"],
                active_spatial,
                parcels_gdf=geometry["parcels"]["analysis"],
            )
            try:
                derived = compute_derived_metrics(
                    repo_root=repo_root,
                    year=base_year,
                    network_override=modified_network,
                )
            except Exception as e:
                log.warning(
                    "Spatial recompute failed for %s (%s); "
                    "falling back to the base network.",
                    tag, e,
                )
                modified_network = None
                derived = base_derived

        log.info("[pipeline %s] building walking graph...", tag)
        G, demand, supply, nodes, asset_entries = _build_graph_and_nodes(
            geometry, assets_df, assumptions, network_gdf=modified_network,
        )
        log.info("[pipeline %s] graph built: %d nodes, %d edges", tag, G.number_of_nodes(), G.number_of_edges())
        log.info("[pipeline %s] computing all-pairs Dijkstra (cutoff 5000m)...", tag)
        matrix = _compute_distance_matrix(G)
        log.info("[pipeline %s] Dijkstra complete: %d source nodes", tag, len(matrix))

        result = {
            "distance_matrix": matrix,
            "demand_nodes":    demand,
            "supply_nodes":    supply,
            "nodes_gdf":       nodes,
            "derived":         derived,
            "asset_entries":   asset_entries,
        }
        _pipeline_cache[tag] = result
        return result

    # ---- Prime the cache with the base network ----
    base_pipeline = _get_pipeline("base", [])
    current_tag = "base"
    current_pipeline = base_pipeline

    def _safe_num(v, default):
        try:
            f = float(v)
            if math.isnan(f):
                return default
            return f
        except (TypeError, ValueError):
            return default

    occupancy_prev = {}
    for _, asset in assets_df.iterrows():
        aid = asset["asset_id"]
        row = base_derived[base_derived["asset_id"] == aid]
        prev_value = 0.6
        if not row.empty:
            r = row.iloc[0]
            if asset["asset_type"] == "community_facility":
                prev_value = _safe_num(r.get("utilisation_rate"), 0.6)
            elif asset["asset_type"] in ("commercial", "residential"):
                prev_value = _safe_num(r.get("occupancy_rate"), 0.6)
        occupancy_prev[aid] = prev_value

    state_by_year = {}
    # Tracks the Huff-assigned demand for each asset from the previous
    # simulated year. Used to detect material demand-pool changes so
    # commercial assets without direct interventions can re-converge
    # when a competitor delivers or the network changes.
    year_demand_prev: dict = {}

    for year_idx, year in enumerate(years):
        # ---- Base year: use B3 output as-is ----
        if year == base_year:
            state_by_year[year] = _state_from_df(base_derived, assets_df)
            continue

        # ---- Check whether the network version changes this year ----
        active_spatial = spatial_interventions_for_year(
            scenario_interventions, year,
        )
        new_tag = network_version_tag(active_spatial)
        network_changed = (new_tag != current_tag)
        if network_changed:
            log.info(
                "Year %d: network version changed %s -> %s",
                year, current_tag, new_tag,
            )
            current_pipeline = _get_pipeline(new_tag, active_spatial)
            current_tag = new_tag

        distance_matrix = current_pipeline["distance_matrix"]
        pipeline_demand_nodes = current_pipeline["demand_nodes"]
        pipeline_supply_nodes = current_pipeline["supply_nodes"]
        pipeline_nodes_gdf = current_pipeline["nodes_gdf"]
        year_derived = current_pipeline["derived"]

        # ---- Resolve effective asset state ----
        effective_assets = {}
        activated_interventions = {}
        for _, asset in assets_df.iterrows():
            aid = asset["asset_id"]
            intvs = interventions_for_asset(aid, scenario_interventions)
            eff = asset.to_dict()
            activated = None
            for intv in intvs:
                p = resolve_phase(year, intv)
                if p == Phase.POST:
                    eff = apply_intervention(eff, intv)
                    itype = intv.get("intervention_type")
                    if itype == "repurpose":
                        activated = intv
                    elif itype == "renovation":
                        # A renovation to a residential rental
                        # subtype (affordable_housing,
                        # apartment_lowrise, apartment_highrise)
                        # activates the asset: developer-held
                        # unsold units become rentable stock. The
                        # occupancy trajectory changes, not just
                        # the energy profile.
                        try:
                            _p = json.loads(
                                intv.get("parameters_json") or "{}"
                            )
                            _to = _p.get("to_subtype")
                        except (json.JSONDecodeError, TypeError):
                            _to = None
                        if _to:
                            _defn = get_subtype(_to) or {}
                            if _defn.get("asset_class") == "residential":
                                activated = intv
                elif p == Phase.DURING:
                    status = intv.get("during_construction_status", "unavailable")
                    # Phase 14 — read the capacity_ratio the validator
                    # stashed in parameters_json. Falls back to None
                    # so apply_construction_state keeps whatever the
                    # engine can infer from `status` alone.
                    capacity_ratio = None
                    try:
                        _p = json.loads(intv.get("parameters_json") or "{}")
                        if "_capacity_ratio" in _p:
                            capacity_ratio = float(_p["_capacity_ratio"])
                    except (json.JSONDecodeError, TypeError, ValueError):
                        pass
                    eff = apply_construction_state(
                        eff, status, capacity_ratio,
                    )
            # Phase D.2 — residential developer-held inventory decays
            # over time. This is the sell-off: a 21-unit terrace row
            # built in 2024 with 5 units unsold in 2026 has 3 unsold
            # in 2028, 1 in 2030, 0 in 2032, at a per-asset seeded
            # 10-20% annual rate. The sold units become occupied.
            #
            # Skip this when the asset has an activated renovation
            # to a residential rental subtype: the held units are
            # no longer unsold inventory — they are rental stock,
            # and their occupancy is driven by the subtype
            # benchmark, not by the sell-off rate.
            if (
                year > base_year
                and eff.get("asset_type") == "residential"
                and activated is None
            ):
                remaining, sold = _compute_developer_held_decay(
                    eff, year, base_year,
                )
                base_held = asset.get("developer_held_units", 0)
                try:
                    base_held = int(float(base_held))
                except (TypeError, ValueError):
                    base_held = 0
                if base_held > 0:
                    eff["developer_held_units"] = remaining
                    eff["_sold_units"] = sold
                    if remaining == 0:
                        eff["ownership_status"] = "sold"
                        eff["authority"] = "advisory"

            effective_assets[aid] = eff
            activated_interventions[aid] = activated

        # ---- Population ----
        projected_pop = project_population(base_pop, base_year, year, g_rate)
        pop_factor = projected_pop / base_pop

        # ---- Supply nodes from effective commercial assets ----
        #
        # Phase B.4b — the effective state decides how each
        # commercial asset enters the Huff pools:
        #
        #   unit_mix still present (mall not repurposed):
        #     keep the per-subtype supply nodes that
        #     `_build_graph_and_nodes` generated. Each subtype
        #     competes in its own pool with its own area.
        #
        #   unit_mix absent (shoplot, or repurpose cleared the mix):
        #     collapse to ONE supply node with the effective
        #     subtype and the asset's total lettable area.
        #
        # The previous version overwrote every supply node's
        # subtype with the asset's PRIMARY subtype. For a mall
        # that meant the supermarket floor, the F&B floor and the
        # showroom floor all competed in the primary subtype's
        # pool. Huff saw one malformed super-competitor instead
        # of six correctly separated pools, and the mall's
        # effective_demand_m2 jumped by ~75% between 2026 (B3
        # baseline, correct) and 2027 (B4, malformed) — a false
        # signal driven by a silent model switch, not by any
        # real intervention.
        active_commercial_ids = {
            aid for aid, eff in effective_assets.items()
            if eff.get("asset_type") == "commercial"
        }

        pipeline_nodes_by_asset = {}
        for s in pipeline_supply_nodes:
            pipeline_nodes_by_asset.setdefault(s["asset_id"], []).append(s)

        year_supply_nodes = []
        for aid, nodes in pipeline_nodes_by_asset.items():
            if aid not in active_commercial_ids:
                continue

            eff = effective_assets[aid]
            eff_subtype = eff.get("subtype", "convenience_retail")
            eff_mix = _parse_unit_mix_engine(eff.get("unit_mix_json"))

            # Both branches below need the asset's virtual node.
            # A missing node means the asset could not be projected
            # onto the walking network, so it cannot participate in
            # any Huff pool.
            node_id = nodes[0]["node"] if nodes else None
            if node_id is None:
                continue

            if eff_mix is not None:
                # Phase B.2c — rebuild supply nodes from the
                # EFFECTIVE mix, not the pipeline's original mix.
                for st, m in eff_mix.items():
                    area = float(m.get("area_m2") or 0)
                    if area <= 0:
                        continue
                    year_supply_nodes.append({
                        "asset_id": aid,
                        "node": node_id,
                        "attractiveness": area,
                        "subtype": st,
                    })
            else:
                # Single-subtype asset (shoplot, or a mall that was
                # fully repurposed and had its mix cleared).
                year_supply_nodes.append({
                    "asset_id": aid,
                    "node": node_id,
                    "attractiveness": float(
                        eff.get("lettable_area_m2") or 0.0
                    ),
                    "subtype": eff_subtype,
                })

        # ---- New supply from delivered projects ----
        active_projects = active_projects_in_year(
            projects_df, year, scenario_id,
            interventions_df=scenario_interventions,
            assets_df=assets_df,
        )
        active_projects.extend(
            _synthesize_new_development_projects(
                scenario_interventions, assets_df, year,
            )
        )
        year_supply_nodes.extend(
            _new_project_supply_nodes(
                active_projects, geometry, pipeline_nodes_gdf,
                pipeline_supply_nodes,
            )
        )

        # ---- Huff (per-subtype) ----
        projected_demand_nodes = [
            {**d, "population": d["population"] * pop_factor}
            for d in pipeline_demand_nodes
        ]
        # Phase 15 — new residents from delivered residential projects
        # enter the Huff demand pool. Without this, `catchment_growth`
        # catalytic interventions have no observable effect on the
        # beneficiary's effective_demand_m2.
        #
        # P2-7 — the node map is returned explicitly and threaded
        # through to `_compute_project_reachable_population`.
        _project_demand_nodes, project_node_map = _new_project_demand_nodes(
            active_projects, geometry, pipeline_nodes_gdf,
        )
        projected_demand_nodes.extend(_project_demand_nodes)

        huff_m2 = huff_gravity_by_subtype(
            distance_matrix,
            projected_demand_nodes,
            year_supply_nodes,
            subtypes_config=subtypes_config,
            alpha=alpha,
            beta=beta,
        )

        # ---- Per-asset metrics ----
        year_state = {}
        for _, asset in assets_df.iterrows():
            aid = asset["asset_id"]
            eff = effective_assets[aid]
            activated = activated_interventions[aid]

            construction_status = eff.get("_construction_status")
            effective_type = eff.get("asset_type", asset["asset_type"])
            effective_subtype = eff.get("subtype", asset.get("subtype"))

            prev_occ = occupancy_prev.get(aid, 0.6)

            # ---- Target occupancy ----
            # Phase 14 — capacity_ratio replaces the automatic
            # occupancy=0. Construction reduces usable capacity, not
            # the number of people who live or work in the asset.
            capacity_ratio = eff.get("_capacity_ratio")
            if not _is_valid_number(capacity_ratio):
                if construction_status == "unavailable":
                    capacity_ratio = 0.0
                elif construction_status == "partial":
                    capacity_ratio = 0.60
                else:
                    capacity_ratio = 1.0
            try:
                capacity_ratio = max(0.0, min(1.0, float(capacity_ratio)))
            except (TypeError, ValueError):
                capacity_ratio = 1.0

            # ---- Target occupancy ----
            if capacity_ratio == 0.0:
                # Fully unavailable: no usable area this year.
                # The tenants/residents remain on record, but the
                # asset provides no serviced capacity in this period.
                new_occ = 0.0
                new_util = 0.0
            else:
                if effective_type == "commercial":
                    curr_demand = huff_m2.get(aid)
                    prev_demand = year_demand_prev.get(aid)

                    demand_delta_abs = (
                        abs(float(curr_demand) - float(prev_demand))
                        if (curr_demand is not None
                            and prev_demand is not None)
                        else 0.0
                    )
                    demand_changed = (
                        prev_demand is not None
                        and curr_demand is not None
                        and float(prev_demand) > 0
                        and abs(float(curr_demand) - float(prev_demand))
                            / float(prev_demand) > _DEMAND_CHANGE_THRESHOLD
                        and demand_delta_abs > _DEMAND_CHANGE_ABSOLUTE_FLOOR_M2
                    )

                    effective_supply = (
                        eff.get("lettable_area_m2")
                        or eff.get("capacity")
                        or 1.0
                    )
                    conversion = (
                        assumptions.get("huff", {})
                        .get("access_to_use_conversion",
                             _DEFAULT_ACCESS_TO_USE_CONVERSION)
                    )

                    if activated is not None:
                        demand_m2 = curr_demand
                        if (demand_m2 is not None
                                and effective_supply
                                and float(effective_supply) > 0):
                            dsr = float(demand_m2) / float(effective_supply)
                        else:
                            dsr = None
                        target_occ = target_occupancy_from_dsr(dsr)

                    elif demand_changed or network_changed:
                        target_occ = _weak_coupling_occupancy(
                            prev_occ=prev_occ,
                            prev_demand=prev_demand,
                            curr_demand=curr_demand,
                            effective_supply=effective_supply,
                            conversion=conversion,
                        )

                    else:
                        target_occ = prev_occ

                    # Phase D.1 — lease schedule bounds occupancy.
                    # Huff can PROMOTE occupancy via increased demand,
                    # but it cannot invent a tenant who has not
                    # renewed. When the lease schedule says a tenant
                    # left and was not replaced, that is a hard upper
                    # bound on the occupancy target.
                    lease_target = _compute_lease_target_occupancy(
                        leases_df, aid, year,
                    )
                    if lease_target is not None and lease_target < target_occ:
                        target_occ = lease_target

                elif effective_type == "community_facility":
                    if activated is None:
                        target_occ = prev_occ
                    else:
                        expected_util = None
                        try:
                            expected = json.loads(
                                activated.get("expected_derived_json") or "{}"
                            )
                            expected_util = expected.get("utilisation")
                        except (json.JSONDecodeError, TypeError):
                            pass

                        if expected_util is not None:
                            target_occ = float(expected_util)
                        else:
                            target_occ = (
                                get_occupancy_benchmark(effective_subtype) or prev_occ
                            )

                else:
                    target_occ = prev_occ

                year_gap = max(1, year - years[year_idx - 1])
                new_occ = prev_occ
                for _ in range(year_gap):
                    new_occ = damped_occupancy(
                        new_occ, target_occ, lambda_, year, critical, kappa,
                    )
                new_util = new_occ

            occupancy_prev[aid] = new_occ

            # -------------------------------------------------------------
            # Phase 11 — canopy extraction.
            # metric_row is only built AFTER the environmental block, so
            # anything that needs canopy must be resolved from the B3
            # frame here. If B3 returned None (OSM has no canopy polygon
            # for this parcel), the helpers fall back to class-typical
            # defaults.
            # -------------------------------------------------------------
            _yr_canopy_match = year_derived[year_derived["asset_id"] == aid]
            canopy_from_b3 = None
            if not _yr_canopy_match.empty:
                _cv = _yr_canopy_match.iloc[0].get("canopy_coverage")
                if _is_valid_number(_cv):
                    canopy_from_b3 = float(_cv)

            # Phase 11b — canopy grows over time.
            # Trees planted at the base year gain canopy area each
            # simulated year. Growth applies to all asset types (a
            # commercial lot's street trees also grow). The growth
            # model is geometric, saturating at the township ceiling.
            _canopy_cfg = assumptions.get("environmental", {})
            _growth_rate = _canopy_cfg.get("canopy_growth_rate_annual", 0.025)
            _ceiling = _canopy_cfg.get("canopy_ceiling_ratio", 0.60)
            _growth_start = _canopy_cfg.get("canopy_growth_start_year", base_year)
            _years_elapsed = max(0, year - _growth_start)

            if canopy_from_b3 is not None and _years_elapsed > 0:
                canopy_from_b3 = canopy_growth(
                    initial_canopy=canopy_from_b3,
                    years_elapsed=_years_elapsed,
                    growth_rate=_growth_rate,
                    ceiling=_ceiling,
                )

            # ---- Environmental (subtype-aware) ----
            floor_area = _safe_num(eff.get("floor_area_m2"), 0.0)

            # Phase 11 — interim solar farm: the asset generates rather
            # than consumes. Carbon is a negative offset.
            carbon_offset = 0.0
            is_interim_solar = (
                bool(eff.get("_is_interim"))
                and effective_subtype == "solar_farm"
            )

            if is_interim_solar:
                solar = interim_solar_generation(
                    float(eff.get("land_area_m2") or 0.0)
                )
                energy = 0.0
                carbon = -1.0 * operational_carbon(
                    solar["annual_kwh"], emission_factor
                )
                breakdown = {
                    "hvac_kwh": 0.0,
                    "lighting_equipment_kwh": 0.0,
                    "base_load_kwh": 0.0,
                }
                hvac_adj = 0.0
            else:
                # Phase B.2b — per-subtype energy when the asset has
                # a unit_mix and remains commercial after any
                # intervention. Matches B3's per-subtype energy
                # calculation, so 2026 (B3 baseline) and 2027+ (B4
                # simulated) are directly comparable.
                unit_mix = _parse_unit_mix_engine(eff.get("unit_mix_json"))
                if effective_type == "commercial" and unit_mix:
                    mix_total_area = sum(
                        float(m.get("area_m2") or 0)
                        for m in unit_mix.values()
                    )
                    scale = (
                        float(floor_area) / mix_total_area
                        if mix_total_area > 0 and floor_area > 0
                        else 1.0
                    )
                    energy_raw = 0.0
                    for st, m in unit_mix.items():
                        st_area = float(m.get("area_m2") or 0) * scale
                        if st_area <= 0:
                            continue
                        st_intensity = get_energy_intensity(st) or 120.0
                        energy_raw += st_area * st_intensity
                else:
                    energy_raw = energy_from_subtype(
                        effective_subtype or "vacant", floor_area
                    )

                breakdown_raw = breakdown_energy(
                    energy_raw, effective_type, assumptions
                )

                # Canopy relief applies only to HVAC
                canopy_for_hvac = (
                    canopy_from_b3 if canopy_from_b3 is not None else 0.0
                )
                hvac_after_canopy = apply_canopy_hvac_relief(
                    breakdown_raw["hvac_kwh"], canopy_for_hvac
                )

                # Per-subsystem retrofit multipliers (P1).
                # Fall back to aggregate multiplier when per-subsystem
                # values are absent (legacy retrofit).
                hvac_mult = eff.get("_hvac_multiplier")
                lighting_mult = eff.get("_lighting_multiplier")
                base_mult = eff.get("_base_multiplier")

                if (_is_valid_number(hvac_mult)
                        and _is_valid_number(lighting_mult)
                        and _is_valid_number(base_mult)):
                    hvac_mult = float(hvac_mult)
                    lighting_mult = float(lighting_mult)
                    base_mult = float(base_mult)
                else:
                    agg = eff.get("_energy_efficiency_multiplier")
                    if _is_valid_number(agg):
                        hvac_mult = lighting_mult = base_mult = float(agg)
                    else:
                        hvac_mult = lighting_mult = base_mult = 1.0

                hvac_adj = hvac_after_canopy * hvac_mult
                lighting_adj = (
                    breakdown_raw["lighting_equipment_kwh"] * lighting_mult
                )
                base_adj = breakdown_raw["base_load_kwh"] * base_mult

                energy_adjusted = hvac_adj + lighting_adj + base_adj

                # Rewrite breakdown so downstream reporting shows the
                # post-retrofit per-subsystem values.
                breakdown = {
                    "hvac_kwh": hvac_adj,
                    "lighting_equipment_kwh": lighting_adj,
                    "base_load_kwh": base_adj,
                }

                energy = energy_adjusted
                carbon = operational_carbon(energy_adjusted, emission_factor)

            # Phase 11 — productive vs stranded split
            if is_interim_solar:
                split = {
                    "carbon_productive_tco2e": carbon,
                    "carbon_stranded_tco2e": 0.0,
                    "stranded_carbon_ratio": 0.0,
                }
            else:
                if effective_type in ("commercial", "residential"):
                    rate = new_occ
                elif effective_type == "community_facility":
                    rate = new_util
                elif effective_type == "green_space":
                    rate = 1.0
                else:
                    rate = 0.0
                split = productive_stranded_carbon(carbon, rate)

            # P2-3 fix — align with B3: green_space has no energy
            # intensity and no operational carbon (B3's green deriver
            # does not compute `carbon_operational_tco2e`, so the
            # field is NaN in the 2026 baseline). B4 was writing 0,
            # which made the comparison block render "null → 0".
            # Force all three fields to None so the comparison key
            # is dropped cleanly by `_valid()` in `_build_comparison`.
            if effective_type == "green_space":
                carbon = None
                energy = None
                split = {
                    "carbon_productive_tco2e": None,
                    "carbon_stranded_tco2e": None,
                    "stranded_carbon_ratio": None,
                }

            # ---- Build metric row ----
            prev_metrics = _get_prev_metrics(state_by_year[years[year_idx - 1]], aid)
            metric_row = dict(prev_metrics)
            metric_row["asset_id"] = aid
            metric_row["year"] = year
            metric_row["subtype"] = effective_subtype

            _owned = _TYPE_EXCLUSIVE_FIELDS.get(effective_type, frozenset())
            for _field in _ALL_TYPE_EXCLUSIVE_FIELDS - _owned:
                metric_row[_field] = None

            # ---------------------------------------------------------
            # Canopy -> Temperature Coupling
            # ---------------------------------------------------------
            _thermal_rows = base_derived[base_derived["asset_id"] == aid]
            _coupled_temp = None
            
            if not _thermal_rows.empty and canopy_from_b3 is not None:
                base_canopy = _thermal_rows.iloc[0].get("canopy_coverage")
                base_temp = _thermal_rows.iloc[0].get("surface_temp_delta_c")
                
                if _is_valid_number(base_canopy) and _is_valid_number(base_temp):
                    delta_canopy = float(canopy_from_b3) - float(base_canopy)
                    
                    if abs(delta_canopy) > 0.01:
                        cfg = assumptions.get("environmental", {}).get("canopy_temperature_coupling", {})
                        slope = cfg.get("slope_celsius_per_unit", -3.272)
                        smooth_years = cfg.get("smoothing_years", 3.0)
                        
                        smoothing = min(1.0, max(0.0, _years_elapsed / smooth_years))
                        temp_shift = delta_canopy * slope * smoothing
                        _coupled_temp = float(base_temp) + temp_shift

            # These values describe the observed footprint and township
            # baseline. They are carried unchanged into scenarios unless
            # a canopy coupling is triggered.
            for _field in THERMAL_METRIC_FIELDS:
                if _thermal_rows.empty or _field not in _thermal_rows.columns:
                    metric_row[_field] = None
                else:
                    _value = _thermal_rows.iloc[0].get(_field)
                    
                    # Apply coupling results
                    if _field == "surface_temp_delta_c" and _coupled_temp is not None:
                        metric_row[_field] = _coupled_temp
                        continue
                        
                    if _value is None or pd.isna(_value):
                        metric_row[_field] = None
                    elif _field in (
                        "surface_temp_provenance",
                        "surface_temp_period_start",
                        "surface_temp_period_end",
                    ):
                        metric_row[_field] = str(_value)
                    elif _is_valid_number(_value):
                        metric_row[_field] = float(_value)
                    else:
                        metric_row[_field] = None

            # ---- Spatial refresh ----
            if not _yr_canopy_match.empty:
                fresh = _yr_canopy_match.iloc[0]
                for _field in _SPATIAL_REFRESH_FIELDS:
                    if _field not in fresh.index:
                        continue
                    val = fresh[_field]
                    if _is_valid_number(val):
                        metric_row[_field] = float(val)

            # ---- Driven value ----
            if effective_type == "community_facility":
                metric_row["utilisation_rate"] = new_util

                # Fallback: a repurpose target becomes a facility, but
                # B3 still sees it as its original class on disk (the
                # static assets.csv is unchanged). B3 therefore never
                # produces `service_coverage` for it — the commercial
                # deriver does not compute that field. Without this
                # fallback, SC-REPURPOSE would report service_coverage
                # as null for every year after activation, which is the
                # single most important social metric of the repurpose.
                #
                # The walking catchment's 10-minute coverage ratio is
                # available (B3 computes it for every asset regardless
                # of type) and equals service_coverage by construction.
                if metric_row.get("service_coverage") is None:
                    if not _yr_canopy_match.empty:
                        fresh_cov = _yr_canopy_match.iloc[0].get(
                            "coverage_ratio_10min_walk",
                        )
                        if _is_valid_number(fresh_cov):
                            metric_row["service_coverage"] = float(fresh_cov)
            elif effective_type == "commercial":
                metric_row["occupancy_rate"] = new_occ
                metric_row["vacancy_rate"] = 1.0 - new_occ
                _recompute_commercial_financials(
                    metric_row=metric_row,
                    eff=eff,
                    aid=aid,
                    year=year,
                    new_occ=new_occ,
                    state_by_year=state_by_year,
                    base_year=base_year,
                    assumptions=assumptions,
                )
                # P1-4 fix — refresh per-subtype occupancy so the
                # subunit breakdown reflects the new aggregate.
                _recompute_per_subtype_occupancy(
                    metric_row=metric_row,
                    eff=eff,
                    new_occ=new_occ,
                    prev_occ=prev_occ,
                )
            elif effective_type == "residential":
                if activated is not None:
                    # Renovation activated: the developer-held
                    # units are now rental stock. Occupancy
                    # converges to the subtype benchmark, not
                    # the sell-off curve.
                    #
                    # Use a hard convergence — a renovation to
                    # rental housing means the units are ready
                    # to lease, and their occupancy is
                    # determined by market demand for the
                    # subtype benchmark, not by a damped
                    # transition. The first year post-activation
                    # already shows the benchmark.
                    _bench = get_occupancy_benchmark(
                        effective_subtype,
                    )
                    if _bench is None:
                        _bench = 0.85
                    new_occ = float(_bench)
                    occupancy_prev[aid] = new_occ
                    eff["developer_held_units"] = 0
                    eff["_sold_units"] = 0
                    _uc = int(eff.get("unit_count") or 1)
                    metric_row["occupied_units"] = int(
                        round(_uc * new_occ)
                    )
                else:
                    # Phase D.2 — sold units become occupied.
                    # Base occupancy from 2026 is the starting
                    # point. Each year's cumulative sold units
                    # add to that base.
                    sold_units = eff.get("_sold_units", 0)
                    if sold_units > 0:
                        unit_count = int(eff.get("unit_count") or 1)
                        base_state = state_by_year.get(base_year, {})
                        base_occ_val = base_state.get(aid, {}).get(
                            "occupancy_rate", 0,
                        )
                        try:
                            base_occ_val = float(base_occ_val)
                        except (TypeError, ValueError):
                            base_occ_val = 0.0
                        base_occupied = base_occ_val * unit_count
                        new_occupied = min(
                            float(unit_count),
                            base_occupied + sold_units,
                        )
                        new_occ = new_occupied / max(1, unit_count)

                metric_row["occupancy_rate"] = new_occ
                metric_row["vacancy_rate"] = 1.0 - new_occ
                metric_row["developer_held_units"] = eff.get(
                    "developer_held_units",
                )

            # Phase E blocker fix — reachable_population_walk must
            # include residents from delivered residential projects.
            # See `_compute_project_reachable_population`.
            _base_reachable = 0.0
            if not _yr_canopy_match.empty:
                _rv = _yr_canopy_match.iloc[0].get("reachable_population_walk")
                if _is_valid_number(_rv):
                    _base_reachable = float(_rv)
            _project_reachable = _compute_project_reachable_population(
                active_projects,
                current_pipeline.get("asset_entries", {}).get(aid),
                distance_matrix,
                project_node_map=project_node_map,   # P2-7 fix
            )
            metric_row["reachable_population_walk"] = (
                _base_reachable + _project_reachable
            )

            metric_row["effective_demand_m2"] = huff_m2.get(aid)
            metric_row["carbon_operational_tco2e"] = carbon
            metric_row["energy_kwh"] = energy
            metric_row["energy_kwh_hvac"] = hvac_adj
            metric_row["energy_kwh_lighting_equipment"] = breakdown["lighting_equipment_kwh"]
            metric_row["energy_kwh_base_load"] = breakdown["base_load_kwh"]
            metric_row["carbon_productive_tco2e"] = split["carbon_productive_tco2e"]
            metric_row["carbon_stranded_tco2e"] = split["carbon_stranded_tco2e"]
            metric_row["stranded_carbon_ratio"] = split["stranded_carbon_ratio"]
            metric_row["canopy_coverage"] = canopy_from_b3
            metric_row["operational_capacity_ratio"] = capacity_ratio
            metric_row["floor_area_m2"] = eff.get("floor_area_m2")   # P1-3 fix
            metric_row["land_area_m2"] = eff.get("land_area_m2")     # sequestration
            metric_row["metric_source"] = "simulated"
            metric_row["model_version"] = __version__

            if effective_type == "community_facility":
                op = float(eff.get("opex_annual_rm") or 0)
                mt = float(eff.get("maintenance_annual_rm") or 0)
                cap = float(eff.get("capacity") or 0)
                util = float(metric_row.get("utilisation_rate") or 0)
                # Phase 14 — effective service bounded by capacity.
                # During construction the asset can only serve
                # min(utilisation, capacity_ratio) of its nominal
                # capacity.
                if capacity_ratio < 1.0:
                    effective_util = min(util, capacity_ratio)
                else:
                    effective_util = util
                annual_users = effective_util * cap * 365 if cap > 0 else 0
                metric_row["cost_per_user_rm"] = (
                    (op + mt) / annual_users if annual_users > 0 else None
                )

            metric_row["_state_kind"] = "asset"
            metric_row["_effective_asset_type"] = effective_type
            metric_row["_effective_capacity"] = eff.get("capacity")
            metric_row["_effective_lettable"] = eff.get("lettable_area_m2")
            year_state[aid] = metric_row

        # ---- Project pseudo-entries ----
        for proj in active_projects:
            _add_project_state(year_state, proj, year, emission_factor)

        # Remember this year's Huff output for every asset so that next
        # year's commercial loop can detect a material demand shift.
        for aid in assets_df["asset_id"].tolist():
            year_demand_prev[aid] = huff_m2.get(aid)

        state_by_year[year] = year_state

    # ---- Comparison ----
    comparison = _build_comparison(
        state_by_year, base_year, years[-1], assets_df,
        selected_ids=selected_ids,
        interventions_df=scenario_interventions,
    )
    comparison["township_metrics"] = _compute_township_metrics(
        state_by_year, years, base_year, years[-1],
    )

    map_diff = _build_map_diff(
        assets_df, interventions_df, projects_df, scenario_id,
    )

    # ---- Phase 4c — per-year deadspace diagnostics ----
    # Writes `scenarios/deadspace_{scenario_id}_{year}.json` for
    # every non-base simulated year. The base year is skipped
    # because run_phase3.py already writes the authoritative
    # business/deadspace_{base_year}.json, and the B4 state for the
    # base year is a verbatim copy of B3 (rewriting would produce
    # a subtly different file for no benefit).
    deadspace_by_year = _build_deadspace_by_year(
        state_by_year=state_by_year,
        assets_df=assets_df,
        base_derived=base_derived,
        assumptions=assumptions,
        years=years,
    )

    ds_dir = base / "business" / "scenarios"
    ds_dir.mkdir(parents=True, exist_ok=True)
    for ds_year, records in deadspace_by_year.items():
        if ds_year == base_year:
            continue
        # Scenario id in the filename so SC-CURRENT, SC-REPURPOSE,
        # and SC-DELAY do not overwrite each other. The frontend
        # defaults to SC-CURRENT for the year selector.
        ds_path = ds_dir / f"deadspace_{scenario_id}_{ds_year}.json"
        with open(ds_path, "w", encoding="utf-8") as f:
            json.dump(_json_safe(records), f, indent=2)
        log.info(
            "Wrote %d deadspace records for %s year %d -> %s",
            len(records), scenario_id, ds_year, ds_path.name,
        )

    return {
        "scenario_id": scenario_id,
        "scenario_name": _scenario_name(scenario_id),
        "interventions": scenario_interventions.to_dict("records"),
        "years": {
            str(y): {"assets": state_by_year.get(y, {})}
            for y in years
        },
        "comparison": comparison,
        "map_diff": map_diff,
        "model_version": __version__,
    }


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _add_project_state(year_state, proj, year, emission_factor):
    """
    Insert a delivered project as a virtual entry into year_state.

    Phase 11: records embodied carbon for new construction (materials
    + demolition) so the delay-vs-deliver comparison can quantify the
    avoided life-cycle carbon.

    Phase 16: embodied carbon is amortised over the SUBTYPE's
    structural lifespan from taxonomy.yml, not a global 50-year
    constant. A 30-year convenience retail and a 60-year terrace
    house do not amortise their locked-in carbon at the same rate.

    P1-3 / P1-5 fix: carries floor_area_m2, occupancy_rate,
    utilisation_rate, and noi_rm so the frontend summary card for a
    new_development asset shows the project's outcome instead of
    a wall of zeros.
    """
    pid = proj.get("project_id")
    if not pid:
        return

    key = f"{PROJECT_ID_PREFIX}{pid}"
    if key in year_state:
        return

    gfa = float(proj.get("gfa_m2") or 0.0)
    subtype = proj.get("subtype") or default_subtype_for(proj.get("land_use"))
    energy = energy_from_subtype(subtype, gfa)
    carbon = operational_carbon(energy, emission_factor)

    _ec = embodied_carbon_for_subtype(
        gfa, subtype, fallback_intensity=MATERIAL_INTENSITY_NEW_BUILD,
    )
    embodied_materials = _ec["embodied_carbon_total_tco2e"]
    demolition = gfa * DEMOLITION_CARBON_INTENSITY
    embodied_total = embodied_materials + demolition

    lifespan = _ec.get("structural_lifespan_years") or 50
    try:
        lifespan = int(lifespan)
    except (TypeError, ValueError):
        lifespan = 50
    if lifespan <= 0:
        lifespan = 50
    embodied_amortised = embodied_total / float(lifespan)

    maintenance_carbon = maintenance_carbon_annual(embodied_total)

    # ---- P1-5: derive occupancy / utilisation / NOI from subtype ----
    # A delivered project is a real asset from the moment it activates.
    # Its headline metrics (space utilisation, annual NOI) must be
    # non-zero on the frontend card.
    _subtype_defn = get_subtype(subtype) or {}
    _asset_class = _subtype_defn.get("asset_class")
    _bench_occ = get_occupancy_benchmark(subtype) or 0.85

    if _asset_class == "commercial":
        # Rough yield-on-cost: 5% NOI on a RM 3,500/m² build.
        # Scaled by occupancy so a half-let shop does not show
        # the same NOI as a fully-let one.
        _capex_per_m2 = 3500.0
        noi_rm = gfa * _capex_per_m2 * 0.05 * _bench_occ
        occupancy_rate = _bench_occ
        utilisation_rate = None
    elif _asset_class == "residential":
        noi_rm = None
        occupancy_rate = _bench_occ
        utilisation_rate = None
    elif _asset_class == "community_facility":
        noi_rm = None
        occupancy_rate = None
        utilisation_rate = _bench_occ
    else:
        noi_rm = None
        occupancy_rate = None
        utilisation_rate = None

    year_state[key] = {
        "asset_id": key,
        "year": year,
        "subtype": subtype,
        # ---- P1-3 / P1-5: fields the frontend card expects ----
        "floor_area_m2": gfa,
        "occupancy_rate": occupancy_rate,
        "utilisation_rate": utilisation_rate,
        "noi_rm": noi_rm,
        # ---- existing fields ----
        "carbon_operational_tco2e": carbon,
        "carbon_productive_tco2e": carbon,
        "carbon_stranded_tco2e": 0.0,
        "stranded_carbon_ratio": 0.0,
        "embodied_carbon_total_tco2e": embodied_total,
        "embodied_carbon_amortised_tco2e": embodied_amortised,
        "maintenance_carbon_tco2e": maintenance_carbon,
        "t_asset_c": None,
        "t_township_c": None,
        "surface_temp_delta_c": None,
        "surface_temp_provenance": None,
        "surface_temp_valid_pixel_count": None,
        "surface_temp_period_start": None,
        "surface_temp_period_end": None,
        "surface_temp_source_image_count": None,
        "energy_kwh": energy,
        "metric_source": "simulated",
        "model_version": __version__,
        "_state_kind": "project",
        "_project_id": pid,
        "_project_name": proj.get("project_name"),
        "_project_gfa_m2": gfa,
        "_project_delivery_year": year,
        "_project_land_use": proj.get("land_use"),
        "_project_target_asset_id": proj.get("asset_id"),
    }


def _build_graph_and_nodes(geometry, assets_df, assumptions, network_gdf=None):
    """
    Build the walking graph and demand/supply node lists for Huff.

    Supply nodes expand per-subtype for mixed-use commercial assets,
    matching B3's `_build_huff_supply_nodes`. A mall's F&B floor
    competes in the F&B pool with its F&B area, not in the primary
    subtype's pool with its whole lettable area.

    Without this expansion, B4's simulated year-2027+ Huff is
    computed with a single-subtype model while B3's year-2026
    baseline is per-subtype. The delta between them mixes a real
    intervention effect with a silent model switch.
    """
    if network_gdf is None:
        network_gdf = geometry["network"]["analysis"]

    gamma = assumptions.get("accessibility", {}).get("canopy_impedance_gamma", 0.3)
    G = build_walk_graph(network_gdf, gamma=gamma)

    all_entries = {}
    parcels_gdf = geometry["parcels"]["analysis"]

    for _, asset in assets_df.iterrows():
        aid = asset["asset_id"]
        geom = None

        # Primary: resolve through parcels.asset_id, the 1:1 map
        # written by build_mock_data.
        match = parcels_gdf[parcels_gdf["asset_id"] == aid]
        if not match.empty:
            geom = match.iloc[0].geometry
        else:
            # Fallback: resolve through the asset's own parcel_id.
            # Handles shared parcels and any asset whose parcel was
            # not assigned a 1:1 asset_id back-reference.
            #
            # B4 fix — without this fallback, assets whose parcel
            # only carries parcel_id (no asset_id back-reference)
            # are silently dropped from the B4 walking pipeline
            # while B3 includes them. The result is a smaller
            # commercial supply pool in B4 (44 vs 74) and a
            # spurious jump in effective_demand_m2 for the
            # surviving competitors on every simulated year.
            pid = asset.get("parcel_id")
            if pid is not None and not (
                isinstance(pid, float) and pd.isna(pid)
            ):
                pmatch = parcels_gdf[parcels_gdf["parcel_id"] == pid]
                if not pmatch.empty:
                    geom = pmatch.iloc[0].geometry

        if geom is None or geom.is_empty:
            continue
        p, off_d, eid = find_entry_point(geom, network_gdf, "walking")
        if p is None:
            continue
        all_entries[f"A::{aid}"] = (p, off_d, eid)

    pop_analysis = geometry["population"]["analysis"]
    for _, pop in pop_analysis.iterrows():
        pid = pop["population_id"]
        p, off_d, eid = find_entry_point(pop.geometry, network_gdf, "walking")
        if p is None:
            continue
        all_entries[f"D::{pid}"] = (p, off_d, eid)

    G_aug = G.copy()
    inserted = insert_all_entries(G_aug, network_gdf, all_entries)

    asset_entries = {}
    demand_entries_map = {}
    for key, val in inserted.items():
        if key.startswith("A::"):
            asset_entries[key[3:]] = val
        elif key.startswith("D::"):
            demand_entries_map[key[3:]] = val

    demand_nodes = []
    for _, pop in pop_analysis.iterrows():
        pid = pop["population_id"]
        info = demand_entries_map.get(pid)
        if info is None:
            continue
        demand_nodes.append({
            "population_id": pid,
            "node": info["virtual_node"],
            "population": float(pop["total_population"]),
        })

    # Supply nodes expand per subtype when a unit_mix is present.
    supply_nodes = []
    for _, asset in assets_df.iterrows():
        if asset["asset_type"] != "commercial":
            continue
        aid = asset["asset_id"]
        info = asset_entries.get(aid)
        if info is None:
            continue

        mix = _parse_unit_mix_engine(asset.get("unit_mix_json"))
        if mix:
            for st, m in mix.items():
                st_area = float(m.get("area_m2") or 0)
                if st_area <= 0:
                    continue
                supply_nodes.append({
                    "asset_id": aid,
                    "node": info["virtual_node"],
                    "attractiveness": st_area,
                    "subtype": st,
                })
        else:
            supply_nodes.append({
                "asset_id": aid,
                "node": info["virtual_node"],
                "attractiveness": float(asset.get("lettable_area_m2") or 0.0),
                "subtype": asset.get("subtype", "convenience_retail"),
            })

    nodes_gdf = extract_nodes(network_gdf)
    return G_aug, demand_nodes, supply_nodes, nodes_gdf, asset_entries


def _parse_unit_mix_engine(raw):
    """Parse unit_mix_json; NaN-safe. Mirrors the helper in
    derived/engine.py."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw or None
    try:
        if pd.isna(raw):
            return None
    except (TypeError, ValueError):
        pass
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and obj:
            return obj
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return None


def _new_project_supply_nodes(active_projects, geometry, nodes_gdf, existing_supply_nodes):
    """
    Virtual supply nodes for projects delivered this year.

    Only COMMERCIAL subtypes enter the Huff supply pool. A residential
    new_development delivers residents (handled by
    `_new_project_demand_nodes`), not a competing retail outlet. When
    `subtype` is absent, `land_use` is used to resolve the default
    subtype, and that subtype's asset_class decides membership.

    Previously any project with gfa_m2 > 0 was added as a supply node,
    which put residential developments into the Huff competition pool
    under a residential subtype and absorbed demand they should have
    been generating.
    """
    from ..derived.network_graph import find_nearest_node
    from ..taxonomy import get_subtype, default_subtype_for

    new_nodes = []

    for proj in active_projects:
        gfa = float(proj.get("gfa_m2") or 0)
        if gfa <= 0:
            continue

        pid = proj.get("parcel_id")
        if not pid:
            continue

        subtype = proj.get("subtype") or default_subtype_for(proj.get("land_use"))
        defn = get_subtype(subtype) or {}
        if defn.get("asset_class") != "commercial":
            # Residential, facility, green, and undeveloped projects
            # do not compete as commercial supply.
            continue

        parcels = geometry["parcels"]["analysis"]
        pmatch = parcels[parcels["parcel_id"] == pid]
        if pmatch.empty:
            continue

        try:
            proj_node = find_nearest_node(pmatch.iloc[0].geometry, nodes_gdf)
        except Exception:
            continue

        new_nodes.append({
            "asset_id": f"NEW-{proj.get('project_id', 'unknown')}",
            "node": proj_node,
            "attractiveness": gfa,
            "subtype": subtype,
        })

    return new_nodes


def _new_project_demand_nodes(active_projects, geometry, nodes_gdf):
    """
    Virtual demand nodes for residential projects delivered this year.

    A new_development of residential units delivers residents. Before
    this function existed, B4 recorded the project's carbon but never
    added its residents to the Huff demand pool — so `catchment_growth`
    catalytic interventions could not be measured.

    Population estimate:
      - if `units` is present: units * subtype avg_household_size
      - else: gfa * (1 / 50) — township-typical residential density

    Node location uses `find_nearest_node` (same convention as
    `_new_project_supply_nodes`) so the augmented distance matrix
    already contains the resolved node id.

    Only residential land use contributes demand nodes; commercial
    and facility projects contribute supply nodes via the sibling
    function.

    P2-7 fix — returns an explicit `project_id → node_id` map instead
    of stashing `_node_id` on each project dict. The previous design
    mutated the caller's `active_projects` list, which is safe only
    because the list is reconstructed per-year. Any caching or
    concurrent use of the list would have silently corrupted the
    node assignment.

    Returns
    -------
    (demand_nodes, project_node_map)
        demand_nodes       : list of Huff demand node dicts
        project_node_map   : {project_id: resolved_node_id}
    """
    from ..taxonomy import get_subtype, default_subtype_for

    out = []
    project_node_map: dict = {}
    for proj in active_projects:
        subtype = proj.get("subtype")
        if not subtype:
            subtype = default_subtype_for(proj.get("land_use"))
        defn = get_subtype(subtype) or {}
        if defn.get("asset_class") != "residential":
            continue

        gfa = float(proj.get("gfa_m2") or 0.0)
        units = proj.get("units")
        hh = defn.get("avg_household_size") or 3.5
        try:
            hh = float(hh)
        except (TypeError, ValueError):
            hh = 3.5

        if _is_valid_number(units):
            try:
                pop = float(units) * hh
            except (TypeError, ValueError):
                pop = 0.0
        else:
            pop = gfa * (1.0 / 50.0)

        if pop <= 0:
            continue

        pid = proj.get("parcel_id")
        if not pid:
            continue

        parcels = geometry["parcels"]["analysis"]
        pmatch = parcels[parcels["parcel_id"] == pid]
        if pmatch.empty:
            continue

        try:
            proj_node = find_nearest_node(pmatch.iloc[0].geometry, nodes_gdf)
        except Exception:
            continue

        project_id = proj.get("project_id") or "?"
        project_node_map[project_id] = proj_node

        out.append({
            "population_id": f"PRJ-POP-{project_id}",
            "node": proj_node,
            "population": pop,
        })
    return out, project_node_map


def _compute_project_reachable_population(
    active_projects, asset_entry, distance_matrix,
    project_node_map=None,
    max_distance_m=1200.0,
):
    """
    Phase E blocker fix — sum the resident population of delivered
    residential projects whose node falls within the asset's walking
    catchment.

    Why this exists
    ---------------
    B3 computes `reachable_population_walk` from base-year demand
    nodes only. A new_development that delivers 320 residents inside
    an asset's 15-minute walking radius is invisible to that metric —
    the count does not move even though the population does. As a
    result, `catchment_growth` catalytic interventions could never be
    verified (the primary metric was constant), and every catalytic
    claim was capped at `partially_verified`.

    This function fills the gap by walking the delivered projects,
    resolving each one's node via `project_node_map`, and summing
    the populations within max_distance_m of the asset's virtual node.

    max_distance_m defaults to 1200 m, matching B3's own catchment
    computation (`aggregate_catchment_profile(max_distance_m=1200.0)`).
    A project beyond that threshold is not inside the asset's walk
    catchment and must not count.

    P2-7 fix — the project → node mapping now arrives via an explicit
    parameter rather than a `_node_id` field stashed on the project
    dict by `_new_project_demand_nodes`.
    """
    if not active_projects or not asset_entry:
        return 0.0
    if project_node_map is None:
        project_node_map = {}
    asset_vn = asset_entry.get("virtual_node")
    if not asset_vn or asset_vn not in distance_matrix:
        return 0.0
    asset_off = float(asset_entry.get("off_distance") or 0.0)
    row = distance_matrix[asset_vn]

    from ..taxonomy import get_subtype, default_subtype_for

    total = 0.0
    for proj in active_projects:
        project_id = proj.get("project_id") or "?"
        proj_node = project_node_map.get(project_id)
        if not proj_node:
            continue
        d_net = row.get(proj_node)
        if d_net is None:
            continue
        if asset_off + d_net > max_distance_m:
            continue

        subtype = proj.get("subtype")
        if not subtype:
            subtype = default_subtype_for(proj.get("land_use"))
        defn = get_subtype(subtype) or {}
        if defn.get("asset_class") != "residential":
            continue

        units = proj.get("units")
        hh = defn.get("avg_household_size") or 3.5
        try:
            hh = float(hh)
        except (TypeError, ValueError):
            hh = 3.5

        if _is_valid_number(units):
            try:
                pop = float(units) * hh
            except (TypeError, ValueError):
                pop = 0.0
        else:
            gfa = float(proj.get("gfa_m2") or 0.0)
            pop = gfa * (1.0 / 50.0)

        total += pop
    return total


def _state_from_df(derived_df, assets_df):
    """Base-year state with the same _effective_* fields as later years."""
    state = {}
    for _, row in derived_df.iterrows():
        aid = row["asset_id"]
        row_dict = row.to_dict()
        asset_row = assets_df[assets_df["asset_id"] == aid]
        if not asset_row.empty:
            a = asset_row.iloc[0]
            row_dict["_effective_asset_type"] = a["asset_type"]
            row_dict["_effective_capacity"] = a.get("capacity")
            row_dict["_effective_lettable"] = a.get("lettable_area_m2")
            row_dict["floor_area_m2"] = a.get("floor_area_m2")   # P1-3 fix
            row_dict["land_area_m2"] = a.get("land_area_m2")     # sequestration
        row_dict["_state_kind"] = "asset"
        state[aid] = row_dict
    return state


def _get_prev_metrics(prev_state, asset_id):
    if asset_id in prev_state:
        return dict(prev_state[asset_id])
    return {}


# ------------------------------------------------------------------
# Comparison
# ------------------------------------------------------------------


# Metrics shown per asset in the comparison block. Order matters only
# for display; the dict preserves it.
_COMPARISON_METRICS = [
    ("occupancy_rate", "ratio"),
    ("utilisation_rate", "ratio"),
    ("developer_held_units", "count"),   # Phase D.2
    ("noi_rm", "RM"),
    ("maintenance_surge_rm", "RM"),
    ("noi_yield", "ratio"),
    ("effective_demand_m2", "m2"),
    ("coverage_ratio_5min_walk", "ratio"),
    ("coverage_ratio_10min_walk", "ratio"),
    ("coverage_ratio_10min_drive", "ratio"),
    ("reachable_population_walk", "count"),
    ("median_walk_distance_m", "m"),
    ("p90_walk_distance_m", "m"),
    ("carbon_operational_tco2e", "tCO2e"),
    ("carbon_productive_tco2e", "tCO2e"),
    ("carbon_stranded_tco2e", "tCO2e"),
    ("stranded_carbon_ratio", "ratio"),
    ("embodied_carbon_total_tco2e", "tCO2e"),
    ("embodied_carbon_amortised_tco2e", "tCO2e/yr"),
    ("maintenance_carbon_tco2e", "tCO2e/yr"),
    ("surface_temp_delta_c", "Celsius"),
    ("operational_capacity_ratio", "ratio"),
]


def _build_comparison(state_by_year, base_year, final_year, assets_df,
                      selected_ids=None, interventions_df=None):
    """
    Per-asset comparison between base year and final year.
    """
    before_state = state_by_year.get(base_year, {})
    after_state = state_by_year.get(final_year, {})

    def _valid(v):
        if v is None:
            return False
        try:
            f = float(v)
        except (TypeError, ValueError):
            return False
        return not math.isnan(f)

    def _num_or_zero(v):
        return float(v) if _valid(v) else 0.0

    if selected_ids is None:
        ids = [aid for aid in before_state if not aid.startswith(PROJECT_ID_PREFIX)]
    else:
        ids = [
            aid for aid in selected_ids
            if not aid.startswith(PROJECT_ID_PREFIX)
        ]

    def _compare_one(aid: str) -> dict:
        b = before_state.get(aid, {})
        a = after_state.get(aid, {})
        metrics = {}
        for key, unit in _COMPARISON_METRICS:
            bv, av = b.get(key), a.get(key)
            if _valid(bv) or _valid(av):
                metrics[key] = {
                    "before": float(bv) if _valid(bv) else None,
                    "after": float(av) if _valid(av) else None,
                    "unit": unit,
                }
        return metrics

    per_asset = {aid: _compare_one(aid) for aid in ids}

    # Avoided embodied carbon from choosing an in-place conversion
    # (repurpose or renovation) over a full rebuild.
    #
    # A renovation keeps the structural shell and changes only the
    # internal finishes, so its embodied carbon is even lower than
    # a repurpose. We use the same REPURPOSE intensity (0.08) as a
    # conservative estimate for both.
    #
    # Without this, a renovation to affordable housing that avoids
    # 800+ tCO2e of new-build embodied carbon shows zero avoided
    # carbon on the comparison block, and the plan looks
    # indistinguishable from a retrofit that does nothing to the
    # asset's structure.
    avoided_embodied_total = 0.0
    if interventions_df is not None:
        for aid in ids:
            intvs = interventions_for_asset(aid, interventions_df)

            subtype_change = next(
                (
                    i for i in intvs
                    if i.get("intervention_type") in (
                        "repurpose", "renovation",
                    )
                ),
                None,
            )
            if subtype_change is None:
                continue

            a_row = assets_df[assets_df["asset_id"] == aid]
            if a_row.empty:
                continue
            asset = a_row.iloc[0]
            gfa = _num_or_zero(asset.get("floor_area_m2"))
            if gfa <= 0:
                continue

            try:
                params = json.loads(
                    subtype_change.get("parameters_json") or "{}"
                )
            except (json.JSONDecodeError, TypeError):
                params = {}

            # subtype_changes path: sum converted area only.
            changes = params.get("subtype_changes")
            if changes:
                mix = _parse_unit_mix_engine(
                    asset.get("unit_mix_json"),
                ) or {}
                converted_area = 0.0
                weighted_intensity = 0.0
                for ch in changes:
                    if not isinstance(ch, dict):
                        continue
                    from_st = ch.get("from_subtype")
                    to_st = ch.get("to_subtype")
                    if not from_st or not to_st:
                        continue
                    from_area = float(
                        (mix.get(from_st) or {}).get("area_m2") or 0.0
                    )
                    requested = ch.get("area_m2")
                    if requested is not None:
                        try:
                            req = float(requested)
                            conv = (
                                min(req, from_area)
                                if from_area > 0 else req
                            )
                        except (TypeError, ValueError):
                            conv = from_area
                    else:
                        conv = from_area
                    if conv <= 0:
                        continue
                    defn = get_subtype(to_st) or {}
                    intensity = defn.get(
                        "material_intensity_tco2e_m2",
                        MATERIAL_INTENSITY_NEW_BUILD,
                    )
                    try:
                        intensity = float(intensity)
                    except (TypeError, ValueError):
                        intensity = MATERIAL_INTENSITY_NEW_BUILD
                    converted_area += conv
                    weighted_intensity += conv * intensity
                if converted_area <= 0:
                    continue
                intensity_new = weighted_intensity / converted_area
                repurposable_area = converted_area
            else:
                # Full conversion (repurpose or renovation).
                target_subtype = params.get("to_subtype")
                if target_subtype:
                    defn = get_subtype(target_subtype) or {}
                    intensity_new = defn.get(
                        "material_intensity_tco2e_m2",
                        MATERIAL_INTENSITY_NEW_BUILD,
                    )
                    try:
                        intensity_new = float(intensity_new)
                    except (TypeError, ValueError):
                        intensity_new = MATERIAL_INTENSITY_NEW_BUILD
                else:
                    intensity_new = MATERIAL_INTENSITY_NEW_BUILD
                repurposable_area = gfa

            # Mixed-ownership: only the developer-held portion
            # is actually convertible.
            uc_raw = asset.get("unit_count")
            held_raw = asset.get("developer_held_units")
            repurposable_ratio = 1.0
            try:
                uc = int(uc_raw) if uc_raw is not None else 1
                h = int(held_raw) if held_raw is not None else 0
                if uc > 1 and 0 < h < uc:
                    repurposable_ratio = h / uc
            except (TypeError, ValueError):
                pass

            saved = repurposable_area * repurposable_ratio * (
                intensity_new
                + DEMOLITION_CARBON_INTENSITY
                - MATERIAL_INTENSITY_REPURPOSE
            )
            if saved > 0:
                avoided_embodied_total += saved
                per_asset[aid]["avoided_embodied_carbon_tco2e"] = {
                    "before": 0.0,
                    "after": saved,
                    "unit": "tCO2e",
                }
                per_asset[aid]["_repurposable_ratio"] = {
                    "before": None,
                    "after": repurposable_ratio,
                    "unit": "ratio",
                }

    # ---- Link project pseudo-entries back to their target asset ----
    project_by_target: dict = {}
    for prj_id, st in after_state.items():
        if not prj_id.startswith(PROJECT_ID_PREFIX):
            continue
        target = st.get("_project_target_asset_id")
        if not target:
            continue
        if target not in per_asset:
            continue
        project_by_target.setdefault(target, []).append(prj_id)

    for target_aid, prj_ids in project_by_target.items():
        linked = []
        for prj_id in prj_ids:
            prj = after_state.get(prj_id, {})
            linked.append({
                "project_id": prj.get("_project_id"),
                "project_name": prj.get("_project_name"),
                "gfa_m2": prj.get("_project_gfa_m2"),
                "delivery_year": prj.get("_project_delivery_year"),
                "carbon_operational_tco2e": {
                    "before": None,
                    "after": prj.get("carbon_operational_tco2e"),
                    "unit": "tCO2e",
                },
                "energy_kwh": {
                    "before": None,
                    "after": prj.get("energy_kwh"),
                    "unit": "kWh",
                },
            })
        per_asset[target_aid]["_linked_projects"] = linked

    # ---- Focus asset (largest absolute delta on occupancy/utilisation) ----
    focus_asset = None
    best_delta = 0.0
    for aid in ids:
        b_st = before_state.get(aid, {})
        a_st = after_state.get(aid, {})
        for key in ("occupancy_rate", "utilisation_rate"):
            delta = abs(
                _num_or_zero(a_st.get(key)) - _num_or_zero(b_st.get(key))
            )
            if delta > best_delta:
                best_delta = delta
                focus_asset = aid

    if focus_asset is None and ids:
        focus_asset = ids[0]

    # ---- Aggregate over the selected set ----
    total_before = 0.0
    total_after = 0.0
    has_before = False
    has_after = False
    for aid in ids:
        b_val = before_state.get(aid, {}).get("carbon_operational_tco2e")
        a_val = after_state.get(aid, {}).get("carbon_operational_tco2e")
        if _valid(b_val):
            total_before += float(b_val)
            has_before = True
        if _valid(a_val):
            total_after += float(a_val)
            has_after = True

    carbon_delta_pct = None
    if has_before and total_before > 0:
        carbon_delta_pct = (total_after - total_before) / total_before

    return {
        "per_asset": per_asset,
        "aggregate": {
            "asset_count": len(ids),
            "total_carbon_before_tco2e": total_before if has_before else None,
            "total_carbon_after_tco2e": total_after if has_after else None,
            "carbon_delta_pct": carbon_delta_pct,
            "avoided_embodied_carbon_tco2e": (
                avoided_embodied_total if avoided_embodied_total > 0 else None
            ),
        },
        "focus_asset_id": focus_asset,
        "metrics": per_asset.get(focus_asset, {}) if focus_asset else {},
    }


# ------------------------------------------------------------------
# Township metrics
# ------------------------------------------------------------------


def _compute_township_metrics(state_by_year, years, base_year, final_year):
    """
    Township-level metrics aggregated across all entries in the state.

    Assets and projects are separated: the total carbon figure counts
    both, while project carbon is also reported on its own so a delay
    can be quantified against a no-delay baseline. Cumulative project
    carbon sums across every simulated year up to final_year — this is
    the number that actually differs between SC-CURRENT and SC-DELAY,
    since both scenarios have the project operating by final_year.

    Carbon sequestration
    --------------------
    Reported as a yearly rate (tCO2e/year), matching the temporal
    structure of `carbon_operational_tco2e`. This makes it possible
    to compare the two side-by-side:

        net_carbon_by_year[year] = operational_carbon[year]
                                   - sequestration[year]

    A negative net figure means the township is a net sink that year.

    Sequestration does NOT enter `carbon_operational_tco2e` — that
    would conflate a physical removal process with an emission
    stream and corrupt the primary carbon comparison.
    """
    before = state_by_year.get(base_year, {})
    after = state_by_year.get(final_year, {})

    def _is_valid(v):
        if v is None:
            return False
        try:
            f = float(v)
        except (TypeError, ValueError):
            return False
        return not math.isnan(f)

    def _avg_coverage(state_dict, key):
        vals = [float(st[key]) for st in state_dict.values()
                if _is_valid(st.get(key))]
        if not vals:
            return None
        return sum(vals) / len(vals)

    def _sum_carbon(state_dict, predicate=None):
        vals = []
        for aid, st in state_dict.items():
            if predicate is not None and not predicate(aid):
                continue
            c = st.get("carbon_operational_tco2e")
            if _is_valid(c):
                vals.append(float(c))
        if not vals:
            return None
        return sum(vals)

    def _is_project(aid):
        return aid.startswith(PROJECT_ID_PREFIX)

    walk_before = _avg_coverage(before, "coverage_ratio_15min_walk")
    walk_after = _avg_coverage(after, "coverage_ratio_15min_walk")

    carbon_before = _sum_carbon(before)
    carbon_after = _sum_carbon(after)
    carbon_delta_pct = None
    if carbon_before is not None and carbon_before > 0 and carbon_after is not None:
        carbon_delta_pct = (carbon_after - carbon_before) / carbon_before

    project_carbon_after = _sum_carbon(after, _is_project)

    project_carbon_cumulative = 0.0
    for idx, y in enumerate(years):
        if y > final_year:
            break
        dt = (y - years[idx - 1]) if idx > 0 else 1
        year_state = state_by_year.get(y, {})
        for aid, st in year_state.items():
            if not _is_project(aid):
                continue
            c = st.get("carbon_operational_tco2e")
            if _is_valid(c):
                project_carbon_cumulative += float(c) * dt

    # ---- Carbon sequestration, yearly rate ----
    #
    # `load_assumptions` is imported at module level and
    # lru_cached; the call is effectively free.
    _assumptions = load_assumptions()
    _seq_cfg = (
        _assumptions.get("carbon_accounting", {})
        .get("sequestration", {})
    )
    _uptake_rate = float(
        _seq_cfg.get("canopy_uptake_tco2e_per_m2_year", 0.0015),
    )

    def _seq_for_state(state_dict):
        total = 0.0
        for aid, st in state_dict.items():
            if _is_project(aid):
                continue
            if st.get("_effective_asset_type") != "green_space":
                continue
            canopy = st.get("canopy_coverage")
            land = st.get("land_area_m2")
            if not _is_valid(canopy) or not _is_valid(land):
                continue
            try:
                total += float(land) * float(canopy) * _uptake_rate
            except (TypeError, ValueError):
                continue
        return total

    # Per-year table of sequestration, operational carbon, and net
    seq_by_year = {}
    op_by_year = {}
    net_by_year = {}
    for y in years:
        yr_state = state_by_year.get(y, {})
        seq_val = _seq_for_state(yr_state)
        op_val = _sum_carbon(yr_state)
        seq_by_year[str(y)] = round(seq_val, 2)
        op_by_year[str(y)] = (
            round(op_val, 2) if op_val is not None else None
        )
        net_by_year[str(y)] = (
            round(op_val - seq_val, 2) if op_val is not None else None
        )

    seq_before = seq_by_year.get(str(base_year), 0.0)
    seq_after = seq_by_year.get(str(final_year), 0.0)

    # Cumulative sequestration: sum(rate × years_in_window)
    seq_cumulative = 0.0
    for idx, y in enumerate(years):
        if y > final_year:
            break
        dt = (y - years[idx - 1]) if idx > 0 else 1
        seq_cumulative += seq_by_year.get(str(y), 0.0) * dt

    return {
        "walk_15min_avg_coverage_before": walk_before,
        "walk_15min_avg_coverage_after": walk_after,
        "walk_15min_coverage_delta": (
            (walk_after - walk_before)
            if walk_before is not None and walk_after is not None
            else None
        ),
        "total_carbon_before_tco2e": carbon_before,
        "total_carbon_after_tco2e": carbon_after,
        "carbon_delta_pct": carbon_delta_pct,
        "project_carbon_after_tco2e": project_carbon_after,
        "project_carbon_cumulative_tco2e": (
            project_carbon_cumulative if project_carbon_cumulative > 0 else None
        ),
        # ---- Carbon sequestration, yearly ----
        "sequestration_by_year_tco2e_year": seq_by_year,
        "sequestration_before_tco2e_year": (
            round(seq_before, 2) if seq_before > 0 else None
        ),
        "sequestration_after_tco2e_year": (
            round(seq_after, 2) if seq_after > 0 else None
        ),
        "sequestration_delta_tco2e_year": round(seq_after - seq_before, 2),
        "sequestration_cumulative_tco2e": (
            round(seq_cumulative, 2) if seq_cumulative > 0 else None
        ),
        "canopy_uptake_rate_tco2e_per_m2_year": _uptake_rate,
        # ---- Net carbon (operational - sequestration), yearly ----
        "operational_carbon_by_year_tco2e_year": op_by_year,
        "net_carbon_by_year_tco2e_year": net_by_year,
    }


# ------------------------------------------------------------------
# Project schedule
# ------------------------------------------------------------------


def _resolve_project_delivery_year(proj, scenario_id, interventions_df,
                                   assets_df=None):
    """
    Return the delivery year this project takes under the given
    scenario, honouring delay/cancel directives.

    A directive may target the project either by project_id (legacy
    mock data) or by asset_id (the LLM's natural vocabulary). When
    assets_df is supplied, an asset-id target resolves to the
    project(s) sitting on the same parcel.
    """
    planned = proj.get("planned_delivery_year")
    if planned is None:
        return None
    try:
        planned = int(planned)
    except (TypeError, ValueError):
        return None

    if interventions_df is None or interventions_df.empty:
        return planned

    pid = proj.get("project_id")
    if pid is None:
        return planned
    pid_str = str(pid)
    proj_parcel = proj.get("parcel_id")

    scen = interventions_df[interventions_df["scenario_id"] == scenario_id]
    for _, intv in scen.iterrows():
        itype = intv.get("intervention_type")
        if itype not in ("delay_development", "cancel_development"):
            continue
        target = intv.get("target_asset_id")
        if target is None:
            continue
        target_str = str(target)

        # Match target to this project — either directly by project_id,
        # or by asset_id whose parcel hosts this project.
        matches = (target_str == pid_str)
        if not matches and assets_df is not None and not assets_df.empty:
            arow = assets_df[assets_df["asset_id"] == target_str]
            if not arow.empty:
                aid_parcel = arow.iloc[0].get("parcel_id")
                if aid_parcel is not None and aid_parcel == proj_parcel:
                    matches = True
        if not matches:
            continue

        if itype == "delay_development":
            try:
                params = json.loads(intv.get("parameters_json") or "{}")
            except (json.JSONDecodeError, TypeError):
                params = {}
            until = params.get("until")
            if until is not None:
                try:
                    planned = int(until)
                except (TypeError, ValueError):
                    pass
        elif itype == "cancel_development":
            return None
    return planned


def _build_project_schedule(projects_df, interventions_df, scenario_id,
                            assets_df=None):
    """
    Compare each project's delivery year under the baseline scenario
    (SC-CURRENT) vs the scenario being simulated. Projects whose
    schedule is unchanged are omitted; only differences are shown.
    """
    if projects_df is None or projects_df.empty:
        return []

    schedule = []
    for _, proj in projects_df.iterrows():
        pid = proj.get("project_id")
        if not pid:
            continue

        baseline_year = _resolve_project_delivery_year(
            proj, BASELINE_SCENARIO_ID, interventions_df,
            assets_df=assets_df,
        )
        scenario_year = _resolve_project_delivery_year(
            proj, scenario_id, interventions_df,
            assets_df=assets_df,
        )

        if baseline_year == scenario_year:
            continue

        if scenario_year is None:
            status = "cancelled"
        elif baseline_year is None:
            status = "added"
        elif scenario_year > baseline_year:
            status = "delayed"
        else:
            status = "advanced"

        schedule.append({
            "project_id": pid,
            "project_name": proj.get("project_name"),
            "parcel_id": proj.get("parcel_id"),
            "gfa_m2": float(proj.get("gfa_m2") or 0.0),
            "baseline_delivery_year": baseline_year,
            "scenario_delivery_year": scenario_year,
            "delta_years": (
                scenario_year - baseline_year
                if scenario_year is not None and baseline_year is not None
                else None
            ),
            "status": status,
        })

    return schedule


def _build_map_diff(assets_df, interventions_df, projects_df, scenario_id):
    changed = []
    spillover = []
    negative = []

    for _, intv in interventions_df.iterrows():
        if intv.get("scenario_id") != scenario_id:
            continue
        aid = intv["target_asset_id"]
        itype = intv["intervention_type"]

        if itype in ("repurpose", "retrofit"):
            changed.append({"asset_id": aid, "change_type": itype, "color": "blue"})
        elif itype in ("pedestrian_upgrade", "green_corridor"):
            spillover.append({"asset_id": aid, "change_type": itype, "color": "purple"})
        elif itype == "delay_development":
            changed.append({"asset_id": aid, "change_type": "delayed", "color": "blue"})
        elif itype == "interim_solar_farm":
            changed.append({"asset_id": aid, "change_type": "solar_farm", "color": "yellow"})

    project_schedule = _build_project_schedule(
        projects_df, interventions_df, scenario_id, assets_df=assets_df,
    )

    return {
        "changed_assets": changed,
        "spillover_assets": spillover,
        "negative_assets": negative,
        "project_schedule": project_schedule,
    }


def _scenario_name(scenario_id: str) -> str:
    names = {
        "SC-CURRENT": "Current Plan",
        "SC-REPURPOSE": "Option A - Repurpose",
        "SC-RETROFIT": "Option B - Retrofit + Green",
        "SC-DELAY": "Option C - Delay + Replan",
    }
    return names.get(scenario_id, scenario_id)


def _recompute_per_subtype_occupancy(metric_row, eff, new_occ, prev_occ):
    """
    P1-4 fix — keep per-subtype occupancy in sync with the aggregate.

    B3 computes `occupancy_by_subtype_calc_json` at the base year
    with a fixed seeded spread. B4 only updates the aggregate
    `occupancy_rate`, so without this fix the per-subtype breakdown
    shown on the dashboard froze at the 2026 snapshot even as the
    aggregate moved. Partial repurpose demos then showed identical
    "before" and "after" per-subtype occupancies despite the
    aggregate jumping.

    Strategy:
      - scale each EXISTING subtype by (new_occ / prev_occ)
      - initialise NEW subtypes (introduced by a partial repurpose)
        to their subtype benchmark, falling back to new_occ
      - clip everything to [0, 1]
    """
    mix = _parse_unit_mix_engine(eff.get("unit_mix_json"))
    if not mix:
        return

    old_json = metric_row.get("occupancy_by_subtype_calc_json")
    try:
        old = json.loads(old_json) if isinstance(old_json, str) and old_json else {}
    except (json.JSONDecodeError, TypeError):
        old = {}
    if not isinstance(old, dict):
        old = {}

    base = float(prev_occ) if prev_occ and float(prev_occ) > 0 else 1.0
    try:
        ratio = float(new_occ) / base if base > 0 else 1.0
    except (TypeError, ValueError, ZeroDivisionError):
        ratio = 1.0

    result = {}
    for st in mix.keys():
        v = old.get(st)
        if v is None:
            # Newly introduced subtype (partial repurpose target).
            bench = get_occupancy_benchmark(st)
            try:
                bench_f = float(bench) if bench is not None else float(new_occ)
            except (TypeError, ValueError):
                bench_f = float(new_occ)
            result[st] = round(min(1.0, max(0.0, bench_f)), 4)
        else:
            try:
                v_f = float(v) * ratio
            except (TypeError, ValueError):
                v_f = float(new_occ)
            result[st] = round(min(1.0, max(0.0, v_f)), 4)

    metric_row["occupancy_by_subtype_calc_json"] = json.dumps(result)


def _json_safe(obj):
    """
    Recursively replace float NaN with None so json.dump emits valid
    JSON.
    """
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, float) and math.isnan(obj):
        return None
    return obj


# ------------------------------------------------------------------
# Phase 4c — per-year deadspace diagnostics
# ------------------------------------------------------------------


def _compute_trajectories_from_state(state_by_year, upto_year):
    """
    Rebuild per-asset trajectory features from B4's simulated history.

    B6's detector consumes `trajectory_class`, `peak_occupancy`,
    `years_since_peak`, `occupancy_trend_3yr`, and
    `years_below_benchmark`. B4 does not update these on simulated
    years — the values carried forward from the base year are the
    B3 classification of 2022-2026, not the trajectory of the
    simulated window. Feeding them to B6 unchanged would emit a
    2026-derived `rapid_decline` flag on a 2033 asset that is
    actually stable.

    Strategy:
      - Base year (first entry in `state_by_year`): B4 copies B3's
        base-year state verbatim, so `trajectory_class` is already
        correct. Preserve it untouched.
      - Later years: reclassify from the (base_year..upto_year)
        occupancy sequence. Fewer years are available than B3 had,
        so classes requiring a long history (e.g. `declining`
        needs years_since_peak >= 2) may not fire until enough
        simulated years have accumulated. This is a data-
        availability limit, not a logic error.
    """
    from ..derived.engine import _classify_trajectory
    from ..taxonomy import get_subtype_or_default
    import numpy as np

    result = {}
    sorted_years = sorted(y for y in state_by_year if y <= upto_year)
    if not sorted_years:
        return result
    base_year = sorted_years[0]

    current_state = state_by_year.get(upto_year, {})
    for aid in current_state:
        if aid.startswith(PROJECT_ID_PREFIX):
            continue

        # Base year — B3's own classification is authoritative.
        if upto_year == base_year:
            st = current_state[aid]
            result[aid] = {
                "trajectory_class": st.get("trajectory_class"),
                "peak_occupancy": st.get("peak_occupancy"),
                "years_since_peak": st.get("years_since_peak"),
                "occupancy_trend_3yr": st.get("occupancy_trend_3yr"),
                "years_below_benchmark": st.get("years_below_benchmark"),
            }
            continue

        occ_history = []
        for y in sorted_years:
            st = state_by_year[y].get(aid, {})
            occ = st.get("occupancy_rate")
            if occ is None:
                occ = st.get("utilisation_rate")
            if occ is None:
                continue
            try:
                occ_history.append(float(occ))
            except (TypeError, ValueError):
                pass

        if len(occ_history) < 2:
            result[aid] = {"trajectory_class": "unknown"}
            continue

        peak = max(occ_history)
        peak_idx = occ_history.index(peak)
        years_since_peak = len(occ_history) - 1 - peak_idx

        subtype = current_state[aid].get("subtype")
        benchmark = None
        if subtype:
            defn = get_subtype_or_default(subtype)
            benchmark = (
                defn.get("occupancy_benchmark")
                or defn.get("utilisation_benchmark")
            )
        try:
            benchmark = float(benchmark) if benchmark is not None else 0.85
        except (TypeError, ValueError):
            benchmark = 0.85

        below_count = 0
        for o in reversed(occ_history):
            if o < benchmark * 0.85:
                below_count += 1
            else:
                break

        tclass = _classify_trajectory(
            occ_history, peak, years_since_peak, below_count, benchmark,
        )

        n = min(3, len(occ_history))
        y_arr = np.array(occ_history[-n:], dtype=float)
        x_arr = np.arange(n)
        try:
            trend = float(np.polyfit(x_arr, y_arr, 1)[0])
        except Exception:
            trend = None

        result[aid] = {
            "trajectory_class": tclass,
            "peak_occupancy": peak,
            "years_since_peak": years_since_peak,
            "occupancy_trend_3yr": trend,
            "years_below_benchmark": below_count,
        }

    return result


def _build_deadspace_by_year(
    state_by_year, assets_df, base_derived, assumptions, years,
):
    """
    Run B6's deadspace detector against every simulated year.

    Why this exists
    ---------------
    The frontend's year selector reads deadspace records per year.
    Before this function, only 2026 had a full diagnosis (B3 -> B6,
    written by run_phase3.py). Every later year fell back to a
    placeholder branch in /api/map/geometry that only checked
    occupancy < 0.50 and utilisation < 0.40. That collapsed a
    200-plus flagged population on 2026 to fewer than 80 on 2027 —
    semantically wrong (a thirty-flag detector becomes a two-flag
    detector) and narratively backwards (the intended story is
    "healthy today, at risk later"; the placeholder told the
    opposite).

    Field ownership
    ---------------
    B4's state carries most of B6's required fields (occupancy,
    utilisation, NOI, carbon split, surface temp, service coverage,
    green / canopy coverage, per-subtype occupancy). Three fields
    need to be filled in here:

      - trajectory_*: rebuilt from the simulated history via
        _compute_trajectories_from_state.
      - dsr: recomputed from effective_demand_m2 / _effective_lettable
        when both are present; inherited from the base year otherwise.
      - demographic_mismatch / neighborhood_diversity: static
        attributes of the asset, copied from the base-year B3 record.

    Asset identity
    --------------
    A repurpose or renovation changes asset_type / subtype. B6 must
    diagnose the asset under its NEW class, not its original one.
    `_effective_asset_type` and `subtype` from the B4 state override
    the raw asset row.

    Returns
    -------
    {year: [deadspace_record, ...]}
    """
    from ..deadspace.detector import detect_deadspace_for_asset
    import pandas as pd

    base_lookup = {}
    for _, row in base_derived.iterrows():
        base_lookup[row["asset_id"]] = row.to_dict()

    assets_lookup = {r["asset_id"]: r for _, r in assets_df.iterrows()}
    results = {}

    for year in years:
        year_state = state_by_year.get(year, {})
        if not year_state:
            continue

        trajectories = _compute_trajectories_from_state(state_by_year, year)

        records = []
        for aid, st in year_state.items():
            if aid.startswith(PROJECT_ID_PREFIX):
                continue
            if aid not in assets_lookup:
                continue

            asset_dict = dict(assets_lookup[aid])
            if st.get("_effective_asset_type"):
                asset_dict["asset_type"] = st["_effective_asset_type"]
            if st.get("subtype"):
                asset_dict["subtype"] = st["subtype"]

            metrics_dict = dict(st)
            metrics_dict["year"] = year
            metrics_dict["asset_id"] = aid
            metrics_dict.update(trajectories.get(aid, {}))

            # DSR — recompute if the base-year value is stale
            if metrics_dict.get("dsr") is None:
                demand = metrics_dict.get("effective_demand_m2")
                supply = (
                    metrics_dict.get("_effective_lettable")
                    or asset_dict.get("lettable_area_m2")
                )
                if demand is not None and supply:
                    try:
                        s = float(supply)
                        if s > 0:
                            metrics_dict["dsr"] = float(demand) / s
                    except (TypeError, ValueError):
                        pass

            # Static fields — inherit from base-year B3
            base = base_lookup.get(aid, {})
            for static_field in (
                "demographic_mismatch", "neighborhood_diversity",
            ):
                if metrics_dict.get(static_field) is None:
                    v = base.get(static_field)
                    if v is not None:
                        metrics_dict[static_field] = v

            try:
                rec = detect_deadspace_for_asset(
                    asset=pd.Series(asset_dict),
                    metrics=pd.Series(metrics_dict),
                    assumptions=assumptions,
                )
                records.append(rec)
            except Exception as e:
                log.warning(
                    "B6 failed for %s year %d: %s", aid, year, e,
                )

        results[year] = records

    return results


def write_scenario_result(result: dict, repo_root: Path = None) -> Path:
    """
    Output path derives from paths.yml instead of a hard-coded "mock/"
    prefix, and NaN values are sanitised to null before serialisation.
    """
    repo_root = repo_root or Path(__file__).resolve().parents[3]
    paths = load_paths()
    out_dir = repo_root / paths["base"] / "business" / "scenarios"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{result['scenario_id']}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(_json_safe(result), f, indent=2, default=str)
    return out
