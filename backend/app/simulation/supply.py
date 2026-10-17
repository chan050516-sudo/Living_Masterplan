"""Supply model: S_t = S_0 + sum of active projects.

FIX: scenario-level delay / cancel directives (intervention_type
"delay_development" / "cancel_development") accept BOTH target
semantics:
  - a project id (PRJ-xx) — legacy mock data
  - an asset id            — resolved via parcel_id to the project(s)
                              on that parcel

The LLM side writes asset ids; the mock side historically wrote
project ids. Both must work.
"""

import json


def active_projects_in_year(
    projects_df,
    year: int,
    scenario_id: str,
    interventions_df=None,
    assets_df=None,
) -> list:
    """
    Returns projects whose planned_delivery_year <= year AND that are
    not cancelled/delayed by the given scenario.

    interventions_df (optional) is consulted for delay_development and
    cancel_development directives whose target_asset_id may be either
    a project id or an asset id.

    assets_df (optional) enables the asset_id -> project resolution.
    When omitted, only direct project-id matches are honoured.
    """
    if projects_df is None or projects_df.empty:
        return []

    delayed_ids, cancelled_ids = _project_directives(
        interventions_df, scenario_id, year,
        projects_df=projects_df, assets_df=assets_df,
    )

    active = []
    for _, p in projects_df.iterrows():
        pid = p.get("project_id")
        status = p.get("project_status")
        if status == "cancelled":
            continue
        if pid in cancelled_ids:
            continue
        if pid in delayed_ids:
            continue
        delivery = p.get("planned_delivery_year")
        if delivery is None or int(delivery) > year:
            continue
        active.append(p.to_dict())
    return active


def project_supply_additions(active_projects: list) -> float:
    """Sum GFA from active projects."""
    return sum(float(p.get("gfa_m2") or 0) for p in active_projects)


def _project_directives(interventions_df, scenario_id, year,
                        projects_df=None, assets_df=None):
    """
    Return (delayed_ids, cancelled_ids) for project-level directives.

    Each directive's target is resolved to zero or more project ids
    via `_resolve_target_projects`, which accepts both the legacy
    project-id form and the asset-id form the LLM writes.
    """
    delayed, cancelled = set(), set()
    if interventions_df is None or interventions_df.empty:
        return delayed, cancelled

    scen = interventions_df[interventions_df["scenario_id"] == scenario_id]
    for _, intv in scen.iterrows():
        itype = intv.get("intervention_type")
        if itype not in ("delay_development", "cancel_development"):
            continue
        target = intv.get("target_asset_id")
        if target is None:
            continue
        pids = _resolve_target_projects(target, projects_df, assets_df)
        if not pids:
            continue
        if itype == "delay_development":
            try:
                params = json.loads(intv.get("parameters_json") or "{}")
            except (json.JSONDecodeError, TypeError):
                params = {}
            until = params.get("until")
            if until is not None and int(until) > year:
                delayed |= pids
        else:  # cancel_development
            cancelled |= pids
    return delayed, cancelled


def _resolve_target_projects(target_id, projects_df, assets_df):
    """
    Resolve a delay/cancel target to zero or more project ids.

    Accepts BOTH:
      - a project id (PRJ-xx) — direct match in development_projects
      - an asset id            — resolved via parcel_id to the
                                 project(s) sitting on that parcel
    """
    pids = set()
    if target_id is None:
        return pids
    target_str = str(target_id)

    # Direct project-id match
    if projects_df is not None and not projects_df.empty:
        direct = projects_df[
            projects_df["project_id"].astype(str) == target_str
        ]
        for _, p in direct.iterrows():
            pids.add(str(p["project_id"]))

    # Asset-id -> parcel -> project match
    if assets_df is not None and not assets_df.empty:
        arow = assets_df[assets_df["asset_id"] == target_str]
        if not arow.empty:
            parcel = arow.iloc[0].get("parcel_id")
            if parcel is not None and projects_df is not None:
                pj = projects_df[projects_df["parcel_id"] == parcel]
                for _, p in pj.iterrows():
                    pids.add(str(p["project_id"]))

    return pids