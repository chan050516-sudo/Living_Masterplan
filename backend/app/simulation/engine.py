"""B4 — Future state simulation engine.

Phase 5 changes:
  - Uses per-subtype Huff (m² demand) matching B3.
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
    first-class citizens of the simulation. Each delivered project is
    added to state_by_year as a virtual entry keyed "PRJ::<id>", so it
    contributes operational carbon to township totals and appears in
    the per-year asset listing with an explicit _state_kind marker.
  - Township metrics now report project carbon separately (annual
    snapshot + cumulative across the simulated year list). This makes
    the carbon cost of a delay directly comparable between scenarios.
  - map_diff gains a "project_schedule" block that shows, per project,
    the baseline vs scenario delivery year and a status enum
    (unchanged / delayed / advanced / cancelled / added).

Phase 9 changes:
  - simulate_scenario() accepts selected_ids. When given, the
    comparison block restricts to those assets and returns a per-asset
    structure, so a multi-asset LLM plan can be evaluated in a single
    simulation pass. A focus_asset_id + metrics pair is still returned
    at the top level for backward compatibility with the UI.
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
from ..derived.environmental import energy_from_subtype, operational_carbon
from ..taxonomy import (
    get_taxonomy,
    get_occupancy_benchmark,
    default_subtype_for,
)
from .time_anchors import resolve_phase, interventions_for_asset, Phase
from .interventions import apply_intervention, apply_construction_state
from .population import project_population
from .occupancy import damped_occupancy, target_occupancy_from_dsr
from .supply import active_projects_in_year

log = logging.getLogger(__name__)


DEFAULT_YEARS = [2026, 2027, 2028, 2030, 2033]

# Prefix for project pseudo-entries in state_by_year. Kept distinct
# from real asset IDs (which use plain alphanumeric codes) so the
# two populations can be told apart without extra metadata.
PROJECT_ID_PREFIX = "PRJ::"

# The "do nothing" baseline scenario. Used only to compute the delta
# shown in map_diff.project_schedule. Not a real simulated scenario.
BASELINE_SCENARIO_ID = "SC-CURRENT"


# ------------------------------------------------------------------
# Asset-type field ownership
# ------------------------------------------------------------------
# Each asset type produces a distinct set of derived fields. When a
# repurpose intervention flips the effective type mid-simulation, the
# metric_row inherits the previous year's values — including fields
# that no longer apply to the new type. Left unchecked, the comparison
# block shows e.g. "occupancy_rate: before 0.21, after 0.0" for a
# building that is now a community hall, which reads as "the repurpose
# made things worse" when in fact the metric is simply no longer
# meaningful.
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
    }),
    "residential": frozenset({
        "occupancy_rate",
        "vacancy_rate",
        "noi_rm",
        "energy_intensity_kwh_m2",
    }),
    "community_facility": frozenset({
        "utilisation_rate",
        "service_coverage",
        "cost_per_user_rm",
    }),
    "green_space": frozenset({
        "green_coverage",
        "canopy_coverage",
        "canopy_ratio_benchmark",
        "green_per_capita_m2",
        "shade_proxy_score",
    }),
    "undeveloped_parcel": frozenset({
        "developable_area_m2",
        "potential_gfa_m2",
        "demand_supply_gap",
        "infrastructure_cost_rm",
    }),
}

_ALL_TYPE_EXCLUSIVE_FIELDS = frozenset().union(*_TYPE_EXCLUSIVE_FIELDS.values())


def _compute_distance_matrix(G):
    """All-pairs shortest path using effective_length_m (canopy-adjusted)."""
    return dict(nx.all_pairs_dijkstra_path_length(G, weight="effective_length_m"))


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

    current_derived = compute_derived_metrics(repo_root=repo_root, year=base_year)

    G_base, demand_nodes, supply_nodes, nodes_gdf = _build_graph_and_nodes(
        geometry, assets_df, assumptions,
    )

    # ---- Population config ----
    pop_cfg = assumptions["population"]
    g_rate = pop_cfg["growth_rate"]["medium"]
    base_pop = float(pop_cfg["base_population"])

    # Huff params
    alpha = assumptions["huff"]["alpha"]
    beta = assumptions["huff"]["beta"]

    # Occupancy dynamics
    lambda_ = assumptions.get("occupancy_dynamics", {}).get("lambda", 0.35)
    critical = assumptions.get("occupancy_dynamics", {}).get("critical_threshold")
    kappa = assumptions.get("occupancy_dynamics", {}).get("kappa", 0.0)

    emission_factor = assumptions.get("environmental", {}).get(
        "emission_factor_energy", 0.58,
    )

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
        row = current_derived[current_derived["asset_id"] == aid]
        prev_value = 0.6
        if not row.empty:
            r = row.iloc[0]
            if asset["asset_type"] == "community_facility":
                prev_value = _safe_num(r.get("utilisation_rate"), 0.6)
            elif asset["asset_type"] in ("commercial", "residential"):
                prev_value = _safe_num(r.get("occupancy_rate"), 0.6)
        occupancy_prev[aid] = prev_value

    state_by_year = {}

    for year_idx, year in enumerate(years):
        # ---- Base year: use B3 output as-is ----
        if year == base_year:
            state_by_year[year] = _state_from_df(current_derived, assets_df)
            continue

        # ---- Resolve effective asset state for every asset ----
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

        # ---- Distance matrix ----
        distance_matrix = _compute_distance_matrix(G_base)

        # ---- Supply nodes from effective commercial assets ----
        active_commercial_ids = {
            aid for aid, eff in effective_assets.items()
            if eff.get("asset_type") == "commercial"
        }
        year_supply_nodes = []
        for s in supply_nodes:
            if s["asset_id"] not in active_commercial_ids:
                continue
            s_copy = dict(s)
            s_copy["subtype"] = effective_assets[s["asset_id"]].get(
                "subtype", "convenience_retail",
            )
            year_supply_nodes.append(s_copy)

        # New supply from delivered projects. Scenario-level delay/cancel
        # directives are respected via active_projects_in_year().
        active_projects = active_projects_in_year(
            projects_df, year, scenario_id,
            interventions_df=scenario_interventions,
        )
        year_supply_nodes.extend(
            _new_project_supply_nodes(active_projects, geometry, nodes_gdf, supply_nodes)
        )

        # ---- Huff (per-subtype) ----
        projected_demand_nodes = [
            {**d, "population": d["population"] * pop_factor}
            for d in demand_nodes
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
                    if activated is None:
                        target_occ = prev_occ
                    else:
                        demand_m2 = huff_m2.get(aid)
                        effective_supply = (
                            eff.get("lettable_area_m2")
                            or eff.get("capacity")
                            or 1.0
                        )
                        if (demand_m2 is not None
                                and effective_supply
                                and float(effective_supply) > 0):
                            dsr = demand_m2 / float(effective_supply)
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

            # ---- Environmental (subtype-aware) ----
            floor_area = float(eff.get("floor_area_m2") or 0)
            energy = energy_from_subtype(effective_subtype or "vacant", floor_area)
            carbon = operational_carbon(energy, emission_factor)

            # ---- Build metric row ----
            prev_metrics = _get_prev_metrics(state_by_year[years[year_idx - 1]], aid)
            metric_row = dict(prev_metrics)
            metric_row["asset_id"] = aid
            metric_row["year"] = year
            metric_row["subtype"] = effective_subtype

            _owned = _TYPE_EXCLUSIVE_FIELDS.get(effective_type, frozenset())
            for _field in _ALL_TYPE_EXCLUSIVE_FIELDS - _owned:
                metric_row[_field] = None

            if effective_type == "community_facility":
                metric_row["utilisation_rate"] = new_util
            elif effective_type in ("commercial", "residential"):
                metric_row["occupancy_rate"] = new_occ
                metric_row["vacancy_rate"] = 1.0 - new_occ

            metric_row["effective_demand_m2"] = huff_m2.get(aid)
            metric_row["carbon_operational_tco2e"] = carbon
            metric_row["energy_kwh"] = energy
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
        # New developments delivered by this year are recorded as
        # virtual entries so their operational carbon reaches township
        # totals and their presence is visible in the per-year listing.
        # Keyed with PROJECT_ID_PREFIX so UI and downstream logic can
        # distinguish them from real assets.
        for proj in active_projects:
            _add_project_state(
                year_state, proj, year, emission_factor,
            )

        state_by_year[year] = year_state

    # ---- Comparison ----
    comparison = _build_comparison(
        state_by_year, base_year, years[-1], assets_df,
        selected_ids=selected_ids,
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


# ---- Helpers ----------------------------------------------------


def _add_project_state(year_state, proj, year, emission_factor):
    """
    Insert a delivered project as a virtual entry into year_state.

    Projects do not carry the full asset schema, so only the fields
    that are meaningful for them are populated: GFA, energy, carbon,
    subtype. Asset-specific keys (occupancy_rate, NOI, ...) are
    intentionally absent.
    """
    pid = proj.get("project_id")
    if not pid:
        return

    key = f"{PROJECT_ID_PREFIX}{pid}"
    if key in year_state:
        return

    gfa = float(proj.get("gfa_m2") or 0.0)
    # development_projects.csv has no explicit subtype column; fall
    # back to a subtype derived from land_use via the taxonomy defaults.
    subtype = proj.get("subtype") or default_subtype_for(proj.get("land_use"))
    energy = energy_from_subtype(subtype, gfa)
    carbon = operational_carbon(energy, emission_factor)

    year_state[key] = {
        "asset_id": key,
        "year": year,
        "subtype": subtype,
        "carbon_operational_tco2e": carbon,
        "energy_kwh": energy,
        "metric_source": "simulated",
        "model_version": __version__,
        "_state_kind": "project",
        "_project_id": pid,
        "_project_name": proj.get("project_name"),
        "_project_gfa_m2": gfa,
        "_project_delivery_year": year,
        "_project_land_use": proj.get("land_use"),
    }


def _build_graph_and_nodes(geometry, assets_df, assumptions):
    """
    Build the walking graph and demand/supply node lists for Huff.

    Uses the same entry-point pipeline as B3 (find_entry_point +
    insert_all_entries) so that base-year and simulated coverage are
    computed against an identical network geometry.
    """
    network = geometry["network"]["analysis"]
    gamma = assumptions.get("accessibility", {}).get("canopy_impedance_gamma", 0.3)
    G = build_walk_graph(network, gamma=gamma)

    # --- Project all entries (assets + demand points) ---
    all_entries = {}
    for _, asset in assets_df.iterrows():
        aid = asset["asset_id"]
        parcels = geometry["parcels"]["analysis"]
        m = parcels[parcels["asset_id"] == aid]
        if m.empty:
            continue
        p, off_d, eid = find_entry_point(m.iloc[0].geometry, network, "walking")
        if p is None:
            continue
        all_entries[f"A::{aid}"] = (p, off_d, eid)

    pop_analysis = geometry["population"]["analysis"]
    for _, pop in pop_analysis.iterrows():
        pid = pop["population_id"]
        p, off_d, eid = find_entry_point(pop.geometry, network, "walking")
        if p is None:
            continue
        all_entries[f"D::{pid}"] = (p, off_d, eid)

    # --- Single insertion pass ---
    G_aug = G.copy()
    inserted = insert_all_entries(G_aug, network, all_entries)

    asset_entries = {}
    demand_entries_map = {}
    for key, val in inserted.items():
        if key.startswith("A::"):
            asset_entries[key[3:]] = val
        elif key.startswith("D::"):
            demand_entries_map[key[3:]] = val

    # --- Demand node list (virtual nodes) ---
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

    # --- Commercial supply node list (virtual nodes) ---
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

    nodes_gdf = extract_nodes(network)
    return G_aug, demand_nodes, supply_nodes, nodes_gdf


def _new_project_supply_nodes(active_projects, geometry, nodes_gdf, existing_supply_nodes):
    """
    Virtual supply nodes for projects delivered this year.

    NOTE: projects are inserted into the graph each year and therefore
    cannot participate in the one-time virtual-node pass. Node snapping
    (no off-network component) is used here instead. This is a known
    approximation vs the asset-side door-to-door distances.

    Projects whose parcel cannot be resolved are SKIPPED rather than
    placed on a fallback node.
    """
    new_nodes = []

    for proj in active_projects:
        gfa = float(proj.get("gfa_m2") or 0)
        if gfa <= 0:
            continue

        pid = proj.get("parcel_id")
        if not pid:
            log.warning(
                "Project %s has no parcel_id; skipping supply node.",
                proj.get("project_id"),
            )
            continue

        parcels = geometry["parcels"]["analysis"]
        pmatch = parcels[parcels["parcel_id"] == pid]
        if pmatch.empty:
            log.warning(
                "Project %s references missing parcel %s; skipping supply node.",
                proj.get("project_id"), pid,
            )
            continue

        try:
            proj_node = find_nearest_node(pmatch.iloc[0].geometry, nodes_gdf)
        except Exception as e:
            log.warning(
                "Could not resolve node for project %s: %s",
                proj.get("project_id"), e,
            )
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
    ("noi_yield", "ratio"),
    ("coverage_ratio_5min_walk", "ratio"),
    ("coverage_ratio_10min_drive", "ratio"),
    ("carbon_operational_tco2e", "tCO2e"),
]


def _build_comparison(state_by_year, base_year, final_year, assets_df,
                      selected_ids=None):
    """
    Per-asset comparison between base year and final year.

    When selected_ids is None, every non-project asset that appears in
    the base year is compared. When given, only the listed assets are
    included. Unknown IDs are silently skipped.

    Returns
    -------
    {
      "per_asset": {asset_id: {metric_key: {before, after, unit}}},
      "aggregate": {
          "asset_count": int,
          "total_carbon_before_tco2e": float | None,
          "total_carbon_after_tco2e":  float | None,
          "carbon_delta_pct":          float | None,
      },
      # Backward-compat aliases. Downstream code that expects the
      # single-focus format continues to work unchanged.
      "focus_asset_id": str | None,
      "metrics": {metric_key: {before, after, unit}},
    }
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

    # ---- Resolve the id list ----
    if selected_ids is None:
        ids = [aid for aid in before_state if not aid.startswith(PROJECT_ID_PREFIX)]
    else:
        ids = [
            aid for aid in selected_ids
            if not aid.startswith(PROJECT_ID_PREFIX)
        ]

    # ---- Per-asset metric comparison ----
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
        },
        # Backward-compat:
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

    # Total carbon includes both real assets and delivered projects.
    carbon_before = _sum_carbon(before)
    carbon_after = _sum_carbon(after)
    carbon_delta_pct = None
    if carbon_before is not None and carbon_before > 0 and carbon_after is not None:
        carbon_delta_pct = (carbon_after - carbon_before) / carbon_before

    # Project carbon, reported separately for scenario comparison.
    project_carbon_after = _sum_carbon(after, _is_project)

    # Cumulative project carbon across every simulated year up to
    # final_year. A project delivered earlier contributes to more
    # simulated years, so a delay visibly reduces this total.
    project_carbon_cumulative = 0.0
    for y in years:
        if y > final_year:
            continue
        year_state = state_by_year.get(y, {})
        for aid, st in year_state.items():
            if not _is_project(aid):
                continue
            c = st.get("carbon_operational_tco2e")
            if _is_valid(c):
                project_carbon_cumulative += float(c)

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
    """
    Return the effective delivery year for a project under a given
    scenario. Returns None if the project is cancelled.

    delay_development directives replace the planned delivery year
    with parameters_json["until"]. cancel_development removes the
    project entirely.
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
    JSON. pandas-originated dicts carry float('nan') for missing
    values; the default json encoder writes those as the literal NaN
    token, which is not valid JSON and breaks strict parsers.
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