"""B4 — Future state simulation engine.

Simulates a scenario across multiple years by iterating the DAG:
  Population -> Households -> Demand -> Occupancy -> Score
                     ^
                 Supply

Design notes:
  - Fix 1+4: distance matrix is recomputed per year so the Huff model uses
    canopy-adjusted effective distances.
  - Fix 2:   post-intervention asset_type changes are honoured; assets that
    are no longer commercial are removed from the Huff supply pool.
  - Fix 3:   community facility utilisation is driven by projected population
    and the per-capita service coefficient.
"""

import json
import logging
from pathlib import Path

import networkx as nx
import pandas as pd

from ..config import load_paths, load_weights, load_benchmarks, load_assumptions
from ..derived.engine import compute_derived_metrics
from ..derived.network_graph import build_walk_graph, extract_nodes, find_nearest_node
from ..derived.huff import huff_gravity
from ..scoring.score import score_asset
from .time_anchors import resolve_phase, interventions_for_asset, Phase
from .interventions import apply_intervention, apply_construction_state
from .population import project_population
from .demand import project_demand_facility
from .occupancy import damped_occupancy, target_occupancy_from_dsr
from .environmental import operational_carbon, energy_from_intensity
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
    weights_cfg = load_weights()
    benchmarks = load_benchmarks()
    assumptions = load_assumptions()

    weights = {k: v for k, v in weights_cfg.items() if isinstance(v, dict)}
    scoring_options = weights_cfg.get("scoring_options", {})

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

    G_base, demand_nodes, supply_nodes, asset_nodes, nodes_gdf = _build_graph_and_nodes(
        geometry, assets_df, assumptions,
    )

    # ---- Global population config ----
    pop_cfg = assumptions["population"]
    g_rate = pop_cfg["growth_rate"]["medium"]
    base_pop = float(pop_cfg["base_population"])

    # Facility service coefficient (sum over facility categories)
    service_coeffs = assumptions.get("demand", {}).get("facility_service_per_capita", {})
    total_service_coeff = sum(service_coeffs.values()) if service_coeffs else 0.0

    # Huff params
    alpha = assumptions["huff"]["alpha"]
    beta = assumptions["huff"]["beta"]

    # Occupancy dynamics
    lambda_ = assumptions.get(
        "occupancy_dynamics", assumptions.get("occupancy", {})
    ).get("lambda", 0.35)
    critical = assumptions.get("occupancy_dynamics", {}).get("critical_threshold")
    kappa = assumptions.get("occupancy_dynamics", {}).get("kappa", 0.0)

    # --- Track occupancy per asset ---
    occupancy_prev = {}
    for _, asset in assets_df.iterrows():
        row = current_derived[current_derived["asset_id"] == asset["asset_id"]]
        occ = row.iloc[0]["occupancy_rate"] if not row.empty else None
        occupancy_prev[asset["asset_id"]] = float(occ) if occ is not None else 0.6

    state_by_year = {}
    scores_by_year = {}

    for year_idx, year in enumerate(years):
        # ---- Base year: use B3 output as-is ----
        if year == base_year:
            state_by_year[year] = _state_from_df(current_derived, assets_df)
            scores_by_year[year] = _score_current(
                assets_df, current_derived, weights, benchmarks, scoring_options, year,
            )
            continue

        # ---- Fix 2: resolve effective asset state for every asset ----
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

        # ---- 1. Population ----
        projected_pop = project_population(base_pop, base_year, year, g_rate)
        pop_factor = projected_pop / base_pop

        # ---- Fix 1+4: distance matrix (recompute each year) ----
        distance_matrix = _compute_distance_matrix(G_base)

        # ---- Fix 2: build supply nodes from effective types ----
        active_commercial_ids = {
            aid for aid, eff in effective_assets.items()
            if eff.get("asset_type") == "commercial"
        }
        year_supply_nodes = [
            s for s in supply_nodes if s["asset_id"] in active_commercial_ids
        ]

        active_projects = active_projects_in_year(projects_df, year, scenario_id)
        year_supply_nodes.extend(
            _new_project_supply_nodes(
                active_projects, geometry, nodes_gdf, supply_nodes,
            )
        )

        # ---- 2. Huff gravity ----
        projected_demand_nodes = [
            {**d, "population": d["population"] * pop_factor}
            for d in demand_nodes
        ]
        huff_result = huff_gravity(
            distance_matrix, projected_demand_nodes, year_supply_nodes,
            alpha=alpha, beta=beta,
        )

        # ---- 3. Per-asset metrics ----
        year_state = {}
        for _, asset in assets_df.iterrows():
            aid = asset["asset_id"]
            eff = effective_assets[aid]
            activated = activated_interventions[aid]

            construction_status = eff.get("_construction_status")
            effective_type = eff.get("asset_type", asset["asset_type"])

            prev_occ = occupancy_prev.get(aid, 0.6)

            # ---- 4. Target occupancy by effective type (Fix 3) ----
            if construction_status == "unavailable":
                new_occ = 0.0
                new_util = 0.0
            else:
                if effective_type == "commercial":
                    dsr = huff_result.get(aid)
                    effective_supply = (
                        eff.get("lettable_area_m2")
                        or eff.get("capacity")
                        or 1.0
                    )
                    if dsr is not None and effective_supply and float(effective_supply) > 0:
                        dsr_ratio = dsr / float(effective_supply)
                    else:
                        dsr_ratio = None
                    target_occ = target_occupancy_from_dsr(dsr_ratio)

                elif effective_type == "community_facility":
                    # Fix 3: facility utilisation tracks projected service demand.
                    # capacity is interpreted as users/day → annual = capacity × 365.
                    # service_per_capita is per-capita annual service demand.
                    demand_persons = project_demand_facility(
                        projected_pop, total_service_coeff,
                    )
                    cap = float(eff.get("capacity") or 0.0)
                    annual_capacity = cap * 365.0
                    if annual_capacity > 0:
                        target_occ = min(1.0, demand_persons / annual_capacity)
                    else:
                        target_occ = prev_occ

                else:
                    # Residential / green_space / undeveloped_parcel:
                    # no demand model drives occupancy in this iteration.
                    target_occ = prev_occ

                year_gap = max(1, year - years[year_idx - 1])
                new_occ = prev_occ
                for _ in range(year_gap):
                    new_occ = damped_occupancy(
                        new_occ, target_occ, lambda_, year, critical, kappa,
                    )
                new_util = new_occ

            occupancy_prev[aid] = new_occ

            # ---- 5. Environmental ----
            floor_area = float(eff.get("floor_area_m2") or 0)
            intensity = assumptions["environmental"]["energy_intensity_default"]
            energy = energy_from_intensity(floor_area, intensity)
            carbon = operational_carbon(
                energy, assumptions["environmental"]["emission_factor_energy"],
            )

            # ---- Build metric row ----
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
            metric_row["model_version"] = "0.3.2"

            # Consume expected_derived_json
            if activated is not None:
                try:
                    expected = json.loads(
                        activated.get("expected_derived_json") or "{}"
                    )
                except (json.JSONDecodeError, TypeError):
                    expected = {}

                if "service_coverage" in expected:
                    metric_row["service_coverage"] = float(expected["service_coverage"])
                if "utilisation" in expected:
                    metric_row["utilisation_rate"] = float(expected["utilisation"])
                if "carbon_operational_tco2e" in expected:
                    metric_row["carbon_operational_tco2e"] = float(
                        expected["carbon_operational_tco2e"]
                    )
                if "accessibility_delta" in expected:
                    prev_acc = float(prev_metrics.get("accessibility_score") or 50.0)
                    metric_row["accessibility_score"] = min(
                        100.0, prev_acc + float(expected["accessibility_delta"]) * 100,
                    )

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
        scores_by_year[year] = _score_year(
            assets_df, year_state, weights, benchmarks, scoring_options, year,
        )

    comparison = _build_comparison(
        state_by_year, scores_by_year, base_year, years[-1], scenario_interventions,
    )
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
        "model_version": "0.3.2",
    }


# ---- Helpers ----------------------------------------------------


def _build_graph_and_nodes(geometry, assets_df, assumptions):
    gamma = assumptions.get("accessibility", {}).get("canopy_impedance_gamma", 0.3)
    network = geometry["network"]["analysis"]
    G = build_walk_graph(network, gamma=gamma)
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

    return G, demand_nodes, supply_nodes, asset_nodes, nodes_gdf


def _new_project_supply_nodes(active_projects, geometry, nodes_gdf, existing_supply_nodes):
    """Virtual supply nodes for projects delivered this year."""
    new_nodes = []
    fallback_node = existing_supply_nodes[0]["node"] if existing_supply_nodes else None

    for proj in active_projects:
        gfa = float(proj.get("gfa_m2") or 0)
        if gfa <= 0:
            continue

        proj_node = None
        pid = proj.get("parcel_id")
        if pid:
            parcels = geometry["parcels"]["analysis"]
            pmatch = parcels[parcels["parcel_id"] == pid]
            if not pmatch.empty:
                try:
                    proj_node = find_nearest_node(pmatch.iloc[0].geometry, nodes_gdf)
                except Exception as e:
                    log.warning("Could not resolve node for project %s: %s", pid, e)

        if proj_node is None:
            proj_node = fallback_node
        if proj_node is None:
            continue

        new_nodes.append({
            "asset_id": f"NEW-{proj.get('project_id', 'unknown')}",
            "node": proj_node,
            "attractiveness": gfa,
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


def _score_current(assets_df, derived_df, weights, benchmarks, scoring_options, year):
    scores = {}
    for _, asset in assets_df.iterrows():
        row = derived_df[derived_df["asset_id"] == asset["asset_id"]]
        if row.empty:
            continue
        r = score_asset(asset, row.iloc[0], weights, benchmarks, scoring_options)
        if r:
            r["year"] = year
            r["model_version"] = "0.3.2"
            scores[asset["asset_id"]] = r
    return scores


def _score_year(assets_df, year_state, weights, benchmarks, scoring_options, year):
    scores = {}
    for _, asset in assets_df.iterrows():
        aid = asset["asset_id"]
        if aid not in year_state:
            continue
        effective_asset = dict(asset)
        effective_asset["asset_type"] = year_state[aid].get(
            "_effective_asset_type", asset["asset_type"],
        )
        effective_asset["capacity"] = year_state[aid].get(
            "_effective_capacity", asset.get("capacity"),
        )
        effective_asset["lettable_area_m2"] = year_state[aid].get(
            "_effective_lettable", asset.get("lettable_area_m2"),
        )

        r = score_asset(effective_asset, year_state[aid], weights, benchmarks, scoring_options)
        if r:
            r["year"] = year
            r["model_version"] = "0.3.2"
            scores[aid] = r
    return scores


def _build_comparison(state_by_year, scores_by_year, base_year, final_year, interventions_df):
    """Focus asset: explicit intervention target, else largest |delta|."""
    target = None
    if not interventions_df.empty:
        for _, intv in interventions_df.iterrows():
            aid = intv.get("target_asset_id")
            if aid and intv.get("intervention_type") != "no_op":
                target = aid
                break

    base_scores = scores_by_year.get(base_year, {})
    final_scores = scores_by_year.get(final_year, {})

    if target is None or target not in base_scores:
        best_asset, best_delta = None, 0.0
        for aid in final_scores:
            b = base_scores.get(aid, {}).get("overall_score", 0.0)
            f = final_scores.get(aid, {}).get("overall_score", 0.0)
            delta = abs(f - b)
            if delta > best_delta:
                best_delta = delta
                best_asset = aid
        target = best_asset

    base_score = base_scores.get(target, {}).get("overall_score", 0.0) if target else 0.0
    final_score = final_scores.get(target, {}).get("overall_score", 0.0) if target else 0.0

    capex = (
        float(interventions_df["capex_delta_rm"].fillna(0).sum())
        if not interventions_df.empty else 0.0
    )

    final_state = state_by_year.get(final_year, {}).get(target, {}) if target else {}

    carbon_10y = _compute_10y_carbon(state_by_year, target)

    projected_util = (
        final_state.get("utilisation_rate")
        or final_state.get("occupancy_rate")
        or 0.0
    )

    tti = 0
    if target:
        for y in sorted(scores_by_year.keys()):
            if y <= base_year:
                continue
            s = scores_by_year[y].get(target, {}).get("overall_score", 0.0)
            if s - base_score > 5:
                tti = (y - base_year) * 12
                break

    return {
        "capex": capex,
        "projected_utilisation": float(projected_util),
        "npv": 0.0,
        "environmental_score": float(
            final_scores.get(target, {}).get("environmental_score") or 0.0
        ) if target else 0.0,
        "social_score": float(
            final_scores.get(target, {}).get("social_score") or 0.0
        ) if target else 0.0,
        "performance_score": float(final_score),
        "carbon_10y_tco2e": carbon_10y,
        "delta_score": float(final_score - base_score),
        "time_to_impact_months": tti,
    }


def _compute_10y_carbon(state_by_year, target):
    """Sum operational carbon across simulated years; extrapolate to 10y."""
    if target is None or not state_by_year:
        return 0.0

    years_sorted = sorted(state_by_year.keys())
    if not years_sorted:
        return 0.0

    carbon_sum = 0.0
    span_covered = 0

    for i, y in enumerate(years_sorted):
        st = state_by_year[y].get(target, {})
        annual = float(st.get("carbon_operational_tco2e") or 0.0)
        if i < len(years_sorted) - 1:
            interval = years_sorted[i + 1] - y
        else:
            interval = 1
        carbon_sum += annual * interval
        span_covered += interval

    if span_covered <= 0:
        return 0.0

    avg_annual = carbon_sum / span_covered
    if span_covered < 10:
        carbon_sum += avg_annual * (10 - span_covered)

    return carbon_sum


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
    repo_root = repo_root or Path(__file__).resolve().parents[3]
    out_dir = repo_root / "mock" / "business" / "scenarios"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{result['scenario_id']}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    return out