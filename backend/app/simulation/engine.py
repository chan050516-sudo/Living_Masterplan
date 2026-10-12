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
from ..taxonomy import get_taxonomy, get_occupancy_benchmark
from .time_anchors import resolve_phase, interventions_for_asset, Phase
from .interventions import apply_intervention, apply_construction_state
from .population import project_population
from .occupancy import damped_occupancy, target_occupancy_from_dsr
from .supply import active_projects_in_year

log = logging.getLogger(__name__)


DEFAULT_YEARS = [2026, 2027, 2028, 2030, 2033]


def _compute_distance_matrix(G):
    """All-pairs shortest path using effective_length_m (canopy-adjusted)."""
    return dict(nx.all_pairs_dijkstra_path_length(G, weight="effective_length_m"))


def simulate_scenario(
    scenario_id: str,
    repo_root: Path = None,
    years: list = None,
) -> dict:
    """Returns a ScenarioResult dict per scenario_result.schema.json."""
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
                    demand_m2 = huff_m2.get(aid)
                    effective_supply = (
                        eff.get("lettable_area_m2")
                        or eff.get("capacity")
                        or 1.0
                    )
                    if demand_m2 is not None and effective_supply and float(effective_supply) > 0:
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

            if effective_type == "community_facility":
                metric_row["utilisation_rate"] = new_util
            elif effective_type in ("commercial", "residential"):
                metric_row["occupancy_rate"] = new_occ
                metric_row["vacancy_rate"] = 1.0 - new_occ
                metric_row["utilisation_rate"] = None
            else:
                pass

            metric_row["effective_demand_m2"] = huff_m2.get(aid)
            metric_row["carbon_operational_tco2e"] = carbon
            metric_row["energy_kwh"] = energy
            metric_row["metric_source"] = "simulated"
            metric_row["model_version"] = __version__

            # Cost per user for facility
            if effective_type == "community_facility":
                op = float(eff.get("opex_annual_rm") or 0)
                mt = float(eff.get("maintenance_annual_rm") or 0)
                cap = float(eff.get("capacity") or 0)
                util = float(metric_row.get("utilisation_rate") or 0)
                annual_users = util * cap * 365 if cap > 0 else 0
                metric_row["cost_per_user_rm"] = (
                    (op + mt) / annual_users if annual_users > 0 else None
                )

            metric_row["_effective_asset_type"] = effective_type
            metric_row["_effective_capacity"] = eff.get("capacity")
            metric_row["_effective_lettable"] = eff.get("lettable_area_m2")
            year_state[aid] = metric_row

        state_by_year[year] = year_state

    # ---- Comparison ----
    comparison = _build_comparison(state_by_year, base_year, years[-1], assets_df)
    comparison["township_metrics"] = _compute_township_metrics(
        state_by_year, base_year, years[-1],
    )

    map_diff = _build_map_diff(assets_df, scenario_interventions)

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


def _build_graph_and_nodes(geometry, assets_df, assumptions):
    """
    Build the walking graph and demand/supply node lists for Huff.

    Uses the same entry-point pipeline as B3 (find_entry_point +
    insert_all_entries) so that base-year and simulated coverage are
    computed against an identical network geometry.

    Returns (G_aug, demand_nodes, supply_nodes, nodes_gdf). nodes_gdf is
    kept for project-based supply nodes, which are inserted each year
    and therefore cannot participate in the one-time virtual-node pass.
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
            "subtype": proj.get("subtype", "convenience_retail"),
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
        state[aid] = row_dict
    return state


def _get_prev_metrics(prev_state, asset_id):
    if asset_id in prev_state:
        return dict(prev_state[asset_id])
    return {}


def _build_comparison(state_by_year, base_year, final_year, assets_df):
    """
    Metric-level comparison between base year and final year.

    Focus asset selection: pick the asset with the largest absolute
    change in either occupancy_rate or utilisation_rate, considering
    both base and final states. The primary metric is the one that
    actually changed.
    """
    before_state = state_by_year.get(base_year, {})
    after_state = state_by_year.get(final_year, {})

    def _valid(v):
        try:
            f = float(v)
            return not math.isnan(f)
        except (TypeError, ValueError):
            return False

    def _num_or_zero(v):
        return float(v) if _valid(v) else 0.0

    focus_asset = None
    best_delta = 0.0
    for aid in before_state:
        b_st = before_state.get(aid, {})
        a_st = after_state.get(aid, {})
        for key in ("occupancy_rate", "utilisation_rate"):
            delta = abs(_num_or_zero(a_st.get(key)) - _num_or_zero(b_st.get(key)))
            if delta > best_delta:
                best_delta = delta
                focus_asset = aid

    if focus_asset is None:
        focus_asset = next(iter(after_state), None)

    if focus_asset is None:
        return {"focus_asset_id": None, "metrics": {}}

    before = before_state.get(focus_asset, {})
    after = after_state.get(focus_asset, {})

    candidate_metrics = [
        ("occupancy_rate", "ratio"),
        ("utilisation_rate", "ratio"),
        ("noi_rm", "RM"),
        ("noi_yield", "ratio"),
        ("coverage_ratio_5min_walk", "ratio"),
        ("coverage_ratio_10min_drive", "ratio"),
        ("carbon_operational_tco2e", "tCO2e"),
    ]

    metrics = {}
    for key, unit in candidate_metrics:
        b = before.get(key)
        a = after.get(key)
        if _valid(b) or _valid(a):
            metrics[key] = {"before": b, "after": a, "unit": unit}

    return {
        "focus_asset_id": focus_asset,
        "metrics": metrics,
    }


def _compute_township_metrics(state_by_year, base_year, final_year):
    """
    Township-level metrics aggregated across all assets.
    NaN values are skipped during aggregation.
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

    def _total_carbon(state_dict):
        vals = [float(st["carbon_operational_tco2e"])
                for st in state_dict.values()
                if _is_valid(st.get("carbon_operational_tco2e"))]
        if not vals:
            return None
        return sum(vals)

    walk_before = _avg_coverage(before, "coverage_ratio_15min_walk")
    walk_after = _avg_coverage(after, "coverage_ratio_15min_walk")

    carbon_before = _total_carbon(before)
    carbon_after = _total_carbon(after)
    carbon_delta_pct = None
    if carbon_before is not None and carbon_before > 0 and carbon_after is not None:
        carbon_delta_pct = (carbon_after - carbon_before) / carbon_before

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
    }


def _build_map_diff(assets_df, interventions_df):
    changed = []
    spillover = []
    negative = []

    for _, intv in interventions_df.iterrows():
        aid = intv["target_asset_id"]
        itype = intv["intervention_type"]

        if itype in ("repurpose", "retrofit"):
            changed.append({"asset_id": aid, "change_type": itype, "color": "blue"})
        elif itype in ("pedestrian_upgrade", "green_corridor"):
            spillover.append({"asset_id": aid, "change_type": itype, "color": "purple"})
        elif itype == "delay_development":
            changed.append({"asset_id": aid, "change_type": "delayed", "color": "blue"})

    return {
        "changed_assets": changed,
        "spillover_assets": spillover,
        "negative_assets": negative,
    }


def _scenario_name(scenario_id: str) -> str:
    names = {
        "SC-CURRENT": "Current Plan",
        "SC-REPURPOSE": "Option A - Repurpose",
        "SC-RETROFIT": "Option B - Retrofit + Green",
        "SC-DELAY": "Option C - Delay + Replan",
    }
    return names.get(scenario_id, scenario_id)


def write_scenario_result(result: dict, repo_root: Path = None) -> Path:
    """
    FIX: output path now derives from paths.yml instead of a hard-coded
    "mock/" prefix.
    """
    repo_root = repo_root or Path(__file__).resolve().parents[3]
    paths = load_paths()
    out_dir = repo_root / paths["base"] / "business" / "scenarios"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{result['scenario_id']}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    return out