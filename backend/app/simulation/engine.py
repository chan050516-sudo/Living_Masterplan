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
  - Adds UHI surface temp proxy (surface_temp_delta_c).
  - Supports interim_solar_farm for generating clean energy offsets.

Phase 11 (2026-10-16):
  - Productive vs stranded carbon split in every year's state row.
  - Energy sub-system breakdown (HVAC / lighting / base load) with
    canopy-based HVAC relief.
  - UHI proxy pulled from the B3-derived canopy field, evaluated
    BEFORE metric_row is constructed (metric_row is only created
    after the environmental block, so accessing it earlier raises
    UnboundLocalError).
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
    calculate_surface_temp_delta,
    interim_solar_generation,
    canopy_growth,
    embodied_carbon_for_subtype,
    MATERIAL_INTENSITY_NEW_BUILD,
    MATERIAL_INTENSITY_REPURPOSE,
    DEMOLITION_CARBON_INTENSITY,
)
from ..taxonomy import (
    get_taxonomy,
    get_occupancy_benchmark,
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


def _compute_distance_matrix(G):
    """All-pairs shortest path using effective_length_m (canopy-adjusted)."""
    return dict(nx.all_pairs_dijkstra_path_length(G, weight="effective_length_m"))


def _is_valid_number(v) -> bool:
    """True if v is a finite float (not None, not NaN)."""
    if v is None:
        return False
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    return not math.isnan(f)


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
) -> dict:
    """
    Returns a ScenarioResult dict per scenario_result.schema.json.

    If selected_ids is provided, the comparison block restricts to
    those assets and produces a per-asset structure (comparison.per_asset).
    If None, every non-project asset is compared. Backward-compat
    focus_asset_id + metrics are always present.

    Network versions
    ----------------
    A scenario may include spatial interventions (pedestrian_upgrade,
    green_corridor). These modify the walking network rather than any
    asset. B4 handles them by maintaining a cache keyed on the set of
    active spatial interventions; when the set changes (i.e. when a
    spatial intervention activates), the network is rebuilt, the
    distance matrix is recomputed, Huff is re-run, and every asset's
    catchment metrics are refreshed. Between activations the cache is
    reused, so the cost is paid once per network version rather than
    once per year.
    """
    repo_root = repo_root or Path(__file__).resolve().parents[3]
    years = years or DEFAULT_YEARS
    base_year = years[0]

    paths = load_paths()
    assumptions = load_assumptions()
    taxonomy = get_taxonomy()
    subtypes_config = taxonomy.get("subtypes", {})

    base = repo_root / paths["base"]
    assets_df = pd.read_csv(base / "business" / "assets.csv")
    interventions_df = pd.read_csv(base / "business" / "interventions.csv")
    projects_df = pd.read_csv(base / "business" / "development_projects.csv")

    scenario_interventions = interventions_df[
        interventions_df["scenario_id"] == scenario_id
    ]

    from ..loaders.geometry_loader import load_geometry
    geometry = load_geometry(repo_root, paths)

    base_derived = compute_derived_metrics(repo_root=repo_root, year=base_year)

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
    # Network version cache
    # ------------------------------------------------------------------
    # Maps network_version_tag -> {
    #     "distance_matrix": dict,
    #     "demand_nodes":   list,
    #     "supply_nodes":   list,
    #     "nodes_gdf":      GeoDataFrame,
    #     "derived":        DataFrame,   # B3 output for this network
    # }
    _pipeline_cache: dict = {}

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

        G, demand, supply, nodes = _build_graph_and_nodes(
            geometry, assets_df, assumptions, network_gdf=modified_network,
        )
        matrix = _compute_distance_matrix(G)

        result = {
            "distance_matrix": matrix,
            "demand_nodes":    demand,
            "supply_nodes":    supply,
            "nodes_gdf":       nodes,
            "derived":         derived,
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
                    activated = intv
                elif p == Phase.DURING:
                    status = intv.get("during_construction_status", "unavailable")
                    eff = apply_construction_state(eff, status)
            effective_assets[aid] = eff
            activated_interventions[aid] = activated

        # ---- Population ----
        projected_pop = project_population(base_pop, base_year, year, g_rate)
        pop_factor = projected_pop / base_pop

        # ---- Supply nodes from effective commercial assets ----
        active_commercial_ids = {
            aid for aid, eff in effective_assets.items()
            if eff.get("asset_type") == "commercial"
        }
        year_supply_nodes = []
        for s in pipeline_supply_nodes:
            if s["asset_id"] not in active_commercial_ids:
                continue
            s_copy = dict(s)
            s_copy["subtype"] = effective_assets[s["asset_id"]].get(
                "subtype", "convenience_retail",
            )
            year_supply_nodes.append(s_copy)

        # ---- New supply from delivered projects ----
        active_projects = active_projects_in_year(
            projects_df, year, scenario_id,
            interventions_df=scenario_interventions,
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
            if construction_status == "unavailable":
                new_occ = 0.0
                new_util = 0.0
            else:
                if effective_type == "commercial":
                    curr_demand = huff_m2.get(aid)
                    prev_demand = year_demand_prev.get(aid)
                    demand_changed = (
                        prev_demand is not None
                        and curr_demand is not None
                        and float(prev_demand) > 0
                        and abs(float(curr_demand) - float(prev_demand))
                            / float(prev_demand) > _DEMAND_CHANGE_THRESHOLD
                    )

                    if (activated is None
                            and not demand_changed
                            and not network_changed):
                        target_occ = prev_occ
                    else:
                        demand_m2 = curr_demand
                        effective_supply = (
                            eff.get("lettable_area_m2")
                            or eff.get("capacity")
                            or 1.0
                        )
                        if (demand_m2 is not None
                                and effective_supply
                                and float(effective_supply) > 0):
                            dsr = float(demand_m2) / float(effective_supply)
                        else:
                            dsr = None
                        target_occ = target_occupancy_from_dsr(dsr)

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
            floor_area = float(eff.get("floor_area_m2") or 0)

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
                energy = energy_from_subtype(
                    effective_subtype or "vacant", floor_area
                )
                eff_mult = eff.get("_energy_efficiency_multiplier")
                if _is_valid_number(eff_mult):
                    energy *= float(eff_mult)

                breakdown = breakdown_energy(
                    energy, effective_type, assumptions
                )
                canopy_for_hvac = (
                    canopy_from_b3 if canopy_from_b3 is not None else 0.0
                )
                hvac_adj = apply_canopy_hvac_relief(
                    breakdown["hvac_kwh"], canopy_for_hvac
                )
                energy_adjusted = (
                    hvac_adj
                    + breakdown["lighting_equipment_kwh"]
                    + breakdown["base_load_kwh"]
                )
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

            # Phase 11 — UHI proxy with type-specific canopy fallback
            if canopy_from_b3 is not None and canopy_from_b3 > 0.01:
                canopy_for_uhi = canopy_from_b3
            elif effective_type == "residential":
                canopy_for_uhi = 0.25
            elif effective_type == "green_space":
                canopy_for_uhi = 0.60
            else:
                canopy_for_uhi = 0.10
            uhi = calculate_surface_temp_delta(
                canopy_coverage_ratio=canopy_for_uhi,
                is_hard_surface=(effective_type != "green_space"),
            )

            # ---- Build metric row ----
            prev_metrics = _get_prev_metrics(state_by_year[years[year_idx - 1]], aid)
            metric_row = dict(prev_metrics)
            metric_row["asset_id"] = aid
            metric_row["year"] = year
            metric_row["subtype"] = effective_subtype

            _owned = _TYPE_EXCLUSIVE_FIELDS.get(effective_type, frozenset())
            for _field in _ALL_TYPE_EXCLUSIVE_FIELDS - _owned:
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
            elif effective_type == "residential":
                metric_row["occupancy_rate"] = new_occ
                metric_row["vacancy_rate"] = 1.0 - new_occ

            metric_row["effective_demand_m2"] = huff_m2.get(aid)
            metric_row["carbon_operational_tco2e"] = carbon
            metric_row["energy_kwh"] = energy
            metric_row["energy_kwh_hvac"] = hvac_adj
            metric_row["energy_kwh_lighting_equipment"] = breakdown["lighting_equipment_kwh"]
            metric_row["energy_kwh_base_load"] = breakdown["base_load_kwh"]
            metric_row["carbon_productive_tco2e"] = split["carbon_productive_tco2e"]
            metric_row["carbon_stranded_tco2e"] = split["carbon_stranded_tco2e"]
            metric_row["stranded_carbon_ratio"] = split["stranded_carbon_ratio"]
            metric_row["surface_temp_delta_c"] = uhi
            metric_row["canopy_coverage"] = canopy_from_b3
            metric_row["metric_source"] = "simulated"
            metric_row["model_version"] = __version__

            if effective_type == "community_facility":
                op = float(eff.get("opex_annual_rm") or 0)
                mt = float(eff.get("maintenance_annual_rm") or 0)
                cap = float(eff.get("capacity") or 0)
                util = float(metric_row.get("utilisation_rate") or 0)
                annual_users = util * cap * 365 if cap > 0 else 0
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

    # Phase 11b — subtype-aware embodied carbon for new construction.
    _ec = embodied_carbon_for_subtype(
        gfa, subtype, fallback_intensity=MATERIAL_INTENSITY_NEW_BUILD,
    )
    embodied_total = _ec["embodied_carbon_total_tco2e"] + (
        gfa * DEMOLITION_CARBON_INTENSITY
    )
    maintenance_carbon = maintenance_carbon_annual(embodied_total)

    uhi = calculate_surface_temp_delta(
        canopy_coverage_ratio=0.05,
        is_hard_surface=True,
    )

    year_state[key] = {
        "asset_id": key,
        "year": year,
        "subtype": subtype,
        "carbon_operational_tco2e": carbon,
        "carbon_productive_tco2e": carbon,
        "carbon_stranded_tco2e": 0.0,
        "stranded_carbon_ratio": 0.0,
        "embodied_carbon_total_tco2e": embodied_total,
        "embodied_carbon_amortised_tco2e": embodied_total / 50.0,
        "maintenance_carbon_tco2e": maintenance_carbon,
        "surface_temp_delta_c": uhi,
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
    """
    if network_gdf is None:
        network_gdf = geometry["network"]["analysis"]

    gamma = assumptions.get("accessibility", {}).get("canopy_impedance_gamma", 0.3)
    G = build_walk_graph(network_gdf, gamma=gamma)

    all_entries = {}
    for _, asset in assets_df.iterrows():
        aid = asset["asset_id"]
        parcels = geometry["parcels"]["analysis"]
        m = parcels[parcels["asset_id"] == aid]
        if m.empty:
            continue
        p, off_d, eid = find_entry_point(m.iloc[0].geometry, network_gdf, "walking")
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

    supply_nodes = []
    for _, asset in assets_df.iterrows():
        if asset["asset_type"] != "commercial":
            continue
        aid = asset["asset_id"]
        info = asset_entries.get(aid)
        if info is None:
            continue
        supply_nodes.append({
            "asset_id": aid,
            "node": info["virtual_node"],
            "attractiveness": float(asset.get("lettable_area_m2") or 0.0),
            "subtype": asset.get("subtype", "convenience_retail"),
        })

    nodes_gdf = extract_nodes(network_gdf)
    return G_aug, demand_nodes, supply_nodes, nodes_gdf


def _new_project_supply_nodes(active_projects, geometry, nodes_gdf, existing_supply_nodes):
    """
    Virtual supply nodes for projects delivered this year.
    """
    from ..derived.network_graph import find_nearest_node
    new_nodes = []

    for proj in active_projects:
        gfa = float(proj.get("gfa_m2") or 0)
        if gfa <= 0:
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

        new_nodes.append({
            "asset_id": f"NEW-{proj.get('project_id', 'unknown')}",
            "node": proj_node,
            "attractiveness": gfa,
            "subtype": proj.get("subtype") or default_subtype_for(proj.get("land_use")),
        })

    return new_nodes


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
    ("noi_rm", "RM"),
    ("maintenance_surge_rm", "RM"),
    ("noi_yield", "ratio"),
    ("coverage_ratio_5min_walk", "ratio"),
    ("coverage_ratio_10min_walk", "ratio"),
    ("coverage_ratio_10min_drive", "ratio"),
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

    # Phase 11 — avoided embodied carbon from choosing repurpose over
    # new build. Uses the material intensity difference times the
    # asset's floor area.
    avoided_embodied_total = 0.0
    if interventions_df is not None:
        for aid in ids:
            intvs = interventions_for_asset(aid, interventions_df)
            if not any(
                i.get("intervention_type") == "repurpose" for i in intvs
            ):
                continue
            a_row = assets_df[assets_df["asset_id"] == aid]
            if a_row.empty:
                continue
            gfa = _num_or_zero(a_row.iloc[0].get("floor_area_m2"))
            saved = gfa * (
                MATERIAL_INTENSITY_NEW_BUILD
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
    }


# ------------------------------------------------------------------
# Project schedule
# ------------------------------------------------------------------


def _resolve_project_delivery_year(proj, scenario_id, interventions_df):
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

    scen = interventions_df[interventions_df["scenario_id"] == scenario_id]
    for _, intv in scen.iterrows():
        if intv.get("target_asset_id") != pid:
            continue
        itype = intv.get("intervention_type")
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


def _build_project_schedule(projects_df, interventions_df, scenario_id):
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
        )
        scenario_year = _resolve_project_delivery_year(
            proj, scenario_id, interventions_df,
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
        projects_df, interventions_df, scenario_id,
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