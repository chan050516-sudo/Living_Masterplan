"""B4 — Future state simulation engine.

Simulates a scenario across multiple years by iterating the DAG:
  Population → Households → Demand → Occupancy → Score
                       ↑
                   Supply
"""

import json
import logging
from pathlib import Path

import pandas as pd

from ..config import load_paths, load_weights, load_benchmarks, load_assumptions
from ..derived.engine import compute_derived_metrics
from ..derived.network_graph import build_walk_graph, extract_nodes, find_nearest_node
from ..derived.accessibility import asset_accessibility
from ..scoring.score import score_asset
from .time_anchors import resolve_phase, interventions_for_asset, Phase
from .interventions import apply_intervention, apply_construction_state
from .population import project_population
from .demand import project_demand_commercial
from .occupancy import damped_occupancy, target_occupancy_from_dsr
from .environmental import operational_carbon, energy_from_intensity
from .supply import active_projects_in_year, project_supply_additions

log = logging.getLogger(__name__)


DEFAULT_YEARS = [2026, 2027, 2028, 2030, 2033]


def simulate_scenario(
    scenario_id: str,
    repo_root: Path = None,
    years: list = None,
) -> dict:
    """
    Returns a ScenarioResult dict per scenario_result.schema.json.
    """
    repo_root = repo_root or Path(__file__).resolve().parents[3]
    years = years or DEFAULT_YEARS
    base_year = years[0]

    paths = load_paths()
    weights_cfg = load_weights()
    benchmarks = load_benchmarks()
    assumptions = load_assumptions()

    weights = {k: v for k, v in weights_cfg.items() if isinstance(v, dict)}
    scoring_options = weights_cfg.get("scoring_options", {})
    ds_cfg = assumptions.get("deadspace", {})

    base = repo_root / paths["base"]
    assets_df = pd.read_csv(base / "business" / "assets.csv")
    metrics_df = pd.read_csv(base / "business" / "asset_metrics.csv")
    interventions_df = pd.read_csv(base / "business" / "interventions.csv")
    projects_df = pd.read_csv(base / "business" / "development_projects.csv")

    # Interventions relevant to this scenario
    scenario_interventions = interventions_df[interventions_df["scenario_id"] == scenario_id]

    # Preload geometry for spatial/accessibility
    from ..loaders.geometry_loader import load_geometry
    geometry = load_geometry(repo_root, paths)

    # Per-year state map: year -> { asset_id -> metrics_dict }
    state_by_year = {}
    scores_by_year = {}

    # Current year — use B3 output as-is
    current_derived = compute_derived_metrics(repo_root=repo_root, year=base_year)

    # Build asset node map + demand nodes
    G_base, demand_nodes, supply_nodes, asset_nodes = _build_graph_and_nodes(
        geometry, assets_df, assumptions
    )

    # Track occupancy per asset across years
    occupancy_prev = {}
    for _, asset in assets_df.iterrows():
        row = current_derived[current_derived["asset_id"] == asset["asset_id"]]
        occ = row.iloc[0]["occupancy_rate"] if not row.empty else None
        occupancy_prev[asset["asset_id"]] = float(occ) if occ is not None else 0.6

    # ---- Iterate years ----
    for year_idx, year in enumerate(years):
        if year == base_year:
            state_by_year[year] = _state_from_df(current_derived)
            scores_by_year[year] = _score_current(
                assets_df, current_derived, weights, benchmarks, scoring_options, year
            )
            continue

        # 1. Population
        pop_cfg = assumptions["population"]
        g = pop_cfg["growth_rate"]["medium"]
        base_pop = float(pop_cfg["base_population"])
        projected_pop = project_population(base_pop, base_year, year, g)
        pop_factor = projected_pop / base_pop

        # 2. Demand (Huff) with projected population
        projected_demand_nodes = []
        for d in demand_nodes:
            projected_demand_nodes.append({
                **d,
                "population": d["population"] * pop_factor,
            })

        alpha = assumptions["huff"]["alpha"]
        beta = assumptions["huff"]["beta"]
        gamma = assumptions["accessibility"]["canopy_impedance_gamma"]
        huff_result = project_demand_commercial(
            G_base, projected_demand_nodes, supply_nodes,
            alpha=alpha, beta=beta, gamma=gamma,
        )

        # 3. Supply — projects delivered by this year
        active_projects = active_projects_in_year(projects_df, year, scenario_id)
        supply_addition = project_supply_additions(active_projects)

        # 4. Asset state — apply interventions
        year_state = {}
        for _, asset in assets_df.iterrows():
            aid = asset["asset_id"]
            intvs = interventions_for_asset(aid, scenario_interventions)

            effective_asset = asset.to_dict()
            phase = Phase.PRE
            activated_intervention = None

            for intv in intvs:
                p = resolve_phase(year, intv)
                if p == Phase.POST:
                    effective_asset = apply_intervention(effective_asset, intv)
                    phase = Phase.POST
                    activated_intervention = intv
                elif p == Phase.DURING:
                    status = intv.get("during_construction_status", "unavailable")
                    effective_asset = apply_construction_state(effective_asset, status)
                    phase = Phase.DURING

            # 5. Occupancy
            prev_occ = occupancy_prev.get(aid, 0.6)

            if phase == Phase.DURING and effective_asset.get("_construction_status") == "unavailable":
                new_occ = 0.0
                new_util = 0.0
            else:
                dsr = huff_result.get(aid)
                effective_supply = effective_asset.get("lettable_area_m2") or effective_asset.get("capacity") or 1.0
                if dsr is not None and effective_supply and float(effective_supply) > 0:
                    dsr_ratio = dsr / float(effective_supply)
                else:
                    dsr_ratio = None

                target_occ = target_occupancy_from_dsr(dsr_ratio)
                lambda_ = assumptions.get("occupancy_dynamics", assumptions.get("occupancy", {})).get("lambda", 0.35)
                critical = assumptions.get("occupancy_dynamics", {}).get("critical_threshold")
                kappa = assumptions.get("occupancy_dynamics", {}).get("kappa", 0.0)
                new_occ = damped_occupancy(prev_occ, target_occ, lambda_,
                                           year, critical, kappa)
                new_util = new_occ  # proxy: utilisation tracks occupancy

            occupancy_prev[aid] = new_occ

            # 6. Environmental — recompute energy & carbon
            floor_area = float(effective_asset.get("floor_area_m2") or 0)
            intensity = assumptions["environmental"]["energy_intensity_default"]
            energy = energy_from_intensity(floor_area, intensity)
            carbon = operational_carbon(energy, assumptions["environmental"]["emission_factor_energy"])

            # Build metrics row from previous + new values
            prev_metrics = _get_prev_metrics(state_by_year[years[year_idx - 1]], aid)
            metric_row = dict(prev_metrics)
            metric_row["asset_id"] = aid
            metric_row["year"] = year
            metric_row["occupancy_rate"] = new_occ
            metric_row["vacancy_rate"] = 1.0 - new_occ
            metric_row["utilisation_rate"] = new_util
            metric_row["effective_demand"] = huff_result.get(aid)
            metric_row["carbon_operational_tco2e"] = carbon
            metric_row["energy_kwh"] = energy
            metric_row["metric_source"] = "simulated"
            metric_row["model_version"] = "0.3.0"

            # Consume expected_derived_json from the activated intervention
            if activated_intervention is not None:
                import json as _json
                try:
                    expected = _json.loads(
                        activated_intervention.get("expected_derived_json") or "{}"
                    )
                except (_json.JSONDecodeError, TypeError):
                    expected = {}

                if "service_coverage" in expected:
                    metric_row["service_coverage"] = float(expected["service_coverage"])
                if "utilisation" in expected:
                    metric_row["utilisation_rate"] = float(expected["utilisation"])
                if "carbon_operational_tco2e" in expected:
                    metric_row["carbon_operational_tco2e"] = float(expected["carbon_operational_tco2e"])
                if "accessibility_delta" in expected:
                    prev_acc = float(prev_metrics.get("accessibility_score") or 50.0)
                    metric_row["accessibility_score"] = min(
                        100.0, prev_acc + float(expected["accessibility_delta"]) * 100
                    )

            # Cost per user for facility: opex + maintenance / annual users
            if effective_asset.get("asset_type") == "community_facility":
                op = float(effective_asset.get("opex_annual_rm") or 0)
                mt = float(effective_asset.get("maintenance_annual_rm") or 0)
                cap = float(effective_asset.get("capacity") or 0)
                util = float(metric_row.get("utilisation_rate") or 0)
                annual_users = util * cap * 365 if cap > 0 else 0
                metric_row["cost_per_user_rm"] = (op + mt) / annual_users if annual_users > 0 else None

            metric_row["_effective_asset_type"] = effective_asset.get("asset_type", asset["asset_type"])
            metric_row["_effective_capacity"] = effective_asset.get("capacity")
            metric_row["_effective_lettable"] = effective_asset.get("lettable_area_m2")
            year_state[aid] = metric_row

        state_by_year[year] = year_state

        # 7. Score for this year
        scores_by_year[year] = _score_year(
            assets_df, year_state, weights, benchmarks, scoring_options, year
        )

    # ---- Build comparison ----
    comparison = _build_comparison(state_by_year, scores_by_year, base_year, years[-1],
                                   scenario_interventions)

    # ---- Build map diff ----
    map_diff = _build_map_diff(assets_df, scenario_interventions)

    return {
        "scenario_id": scenario_id,
        "scenario_name": _scenario_name(scenario_id),
        "interventions": scenario_interventions.to_dict("records"),
        "years": {
            str(y): {
                "assets": state_by_year.get(y, {}),
                "scores": scores_by_year.get(y, {}),
            }
            for y in years
        },
        "comparison": comparison,
        "map_diff": map_diff,
        "model_version": "0.3.0",
    }


# ---- Helper functions ----------------------------------------------------

def _build_graph_and_nodes(geometry, assets_df, assumptions):
    network = geometry["network"]["analysis"]
    G = build_walk_graph(network)
    nodes_gdf = extract_nodes(network)

    asset_nodes = {}
    for _, asset in assets_df.iterrows():
        parcels = geometry["parcels"]["analysis"]
        m = parcels[parcels["asset_id"] == asset["asset_id"]]
        if m.empty:
            continue
        asset_nodes[asset["asset_id"]] = find_nearest_node(m.iloc[0].geometry, nodes_gdf)

    pop_analysis = geometry["population"]["analysis"]
    demand_nodes = []
    for idx, pop in pop_analysis.iterrows():
        node = find_nearest_node(pop.geometry, nodes_gdf)
        demand_nodes.append({
            "population_id": pop["population_id"],
            "node": node,
            "population": float(pop["total_population"]),
        })

    supply_nodes = []
    for _, asset in assets_df.iterrows():
        if asset["asset_type"] != "commercial":
            continue
        supply_nodes.append({
            "asset_id": asset["asset_id"],
            "node": asset_nodes.get(asset["asset_id"]),
            "attractiveness": float(asset.get("lettable_area_m2") or 0.0),
        })

    return G, demand_nodes, supply_nodes, asset_nodes


def _state_from_df(derived_df):
    state = {}
    for _, row in derived_df.iterrows():
        state[row["asset_id"]] = row.to_dict()
    return state


def _get_prev_metrics(prev_state, asset_id):
    if asset_id in prev_state:
        return dict(prev_state[asset_id])
    return {}


def _score_current(assets_df, derived_df, weights, benchmarks, scoring_options, year):
    scores = {}
    for _, asset in assets_df.iterrows():
        row = derived_df[derived_df["asset_id"] == asset["asset_id"]]
        if row.empty:
            continue
        r = score_asset(asset, row.iloc[0], weights, benchmarks, scoring_options)
        if r:
            r["year"] = year
            r["model_version"] = "0.3.0"
            scores[asset["asset_id"]] = r
    return scores


def _score_year(assets_df, year_state, weights, benchmarks, scoring_options, year):
    scores = {}
    for _, asset in assets_df.iterrows():
        aid = asset["asset_id"]
        if aid not in year_state:
            continue
        # Use the effective asset_type (post-intervention), not the CSV one
        effective_asset = dict(asset)
        effective_asset["asset_type"] = year_state[aid].get(
            "_effective_asset_type", asset["asset_type"]
        )
        effective_asset["capacity"] = year_state[aid].get("_effective_capacity", asset.get("capacity"))
        effective_asset["lettable_area_m2"] = year_state[aid].get(
            "_effective_lettable", asset.get("lettable_area_m2")
        )

        r = score_asset(effective_asset, year_state[aid], weights, benchmarks, scoring_options)
        if r:
            r["year"] = year
            r["model_version"] = "0.3.0"
            scores[aid] = r
    return scores


def _build_comparison(state_by_year, scores_by_year, base_year, final_year, interventions_df):
    # Focus asset: first intervention's target
    if not interventions_df.empty:
        target = None
        for _, intv in interventions_df.iterrows():
            aid = intv.get("target_asset_id")
            if aid and intv.get("intervention_type") != "no_op":
                target = aid
                break
    else:
        target = None

    base_score = 0.0
    final_score = 0.0
    if target:
        base_score = scores_by_year.get(base_year, {}).get(target, {}).get("overall_score", 0.0)
        final_score = scores_by_year.get(final_year, {}).get(target, {}).get("overall_score", 0.0)

    capex = float(interventions_df["capex_delta_rm"].fillna(0).sum()) if not interventions_df.empty else 0.0

    final_state = state_by_year.get(final_year, {}).get(target, {}) if target else {}
    projected_util = (
        final_state.get("utilisation_rate")
        or final_state.get("occupancy_rate")
        or 0.0
    )

    # Time to impact: first year where score improves materially
    tti = 0
    if target:
        base = base_score
        for y in sorted(scores_by_year.keys()):
            if y <= base_year:
                continue
            s = scores_by_year[y].get(target, {}).get("overall_score", 0.0)
            if s - base > 5:
                tti = (y - base_year) * 12
                break

    return {
        "capex": capex,
        "projected_utilisation": float(final_state.get("occupancy_rate") or final_state.get("utilisation_rate") or 0.0),
        "npv": 0.0,   # placeholder — Phase 5
        "environmental_score": float(scores_by_year.get(final_year, {}).get(target, {}).get("environmental_score") or 0.0),
        "social_score": float(scores_by_year.get(final_year, {}).get(target, {}).get("social_score") or 0.0),
        "projected_utilisation": float(projected_util),
        "performance_score": float(final_score),
        "delta_score": float(final_score - base_score),
        "time_to_impact_months": tti,
    }


def _build_map_diff(assets_df, interventions_df):
    changed = []
    spillover = []
    negative = []

    for _, intv in interventions_df.iterrows():
        aid = intv["target_asset_id"]
        itype = intv["intervention_type"]

        if itype in ("repurpose", "retrofit"):
            changed.append({
                "asset_id": aid,
                "change_type": itype,
                "color": "blue",
            })
        elif itype in ("pedestrian_upgrade", "green_corridor"):
            spillover.append({
                "asset_id": aid,
                "change_type": itype,
                "color": "purple",
            })
        elif itype == "delay_development":
            changed.append({
                "asset_id": aid,
                "change_type": "delayed",
                "color": "blue",
            })

    return {
        "changed_assets": changed,
        "spillover_assets": spillover,
        "negative_assets": negative,
    }


def _scenario_name(scenario_id: str) -> str:
    names = {
        "SC-CURRENT": "Current Plan",
        "SC-REPURPOSE": "Option A — Repurpose",
        "SC-RETROFIT": "Option B — Retrofit + Green",
        "SC-DELAY": "Option C — Delay + Replan",
    }
    return names.get(scenario_id, scenario_id)


def write_scenario_result(result: dict, repo_root: Path = None) -> Path:
    repo_root = repo_root or Path(__file__).resolve().parents[3]
    out_dir = repo_root / "mock" / "business" / "scenarios"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{result['scenario_id']}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    return out