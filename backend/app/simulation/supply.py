"""Supply model: S_t = S_0 + sum of active projects.

FIX: scenario-level delay / cancel directives (intervention_type
"delay_development" / "cancel_development" targeting a project id)
are now honoured. Previously SC-DELAY's INT-003 was silently ignored
because this module never consulted the interventions table.
"""

import json


def active_projects_in_year(
    projects_df,
    year: int,
    scenario_id: str,
    interventions_df=None,
) -> list:
    """
    Returns projects whose planned_delivery_year <= year AND that are
    not cancelled/delayed by the given scenario.

    interventions_df (optional) is consulted for delay_development and
    cancel_development directives whose target_asset_id is a project ID.
    """
    if projects_df is None or projects_df.empty:
        return []

    delayed_ids, cancelled_ids = _project_directives(
        interventions_df, scenario_id, year,
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


def _project_directives(interventions_df, scenario_id, year):
    """Return (delayed_ids, cancelled_ids) for project-level directives."""
    delayed, cancelled = set(), set()
    if interventions_df is None or interventions_df.empty:
        return delayed, cancelled

    scen = interventions_df[interventions_df["scenario_id"] == scenario_id]
    for _, intv in scen.iterrows():
        itype = intv.get("intervention_type")
        target = intv.get("target_asset_id")
        if target is None:
            continue
        if itype == "delay_development":
            try:
                params = json.loads(intv.get("parameters_json") or "{}")
            except (json.JSONDecodeError, TypeError):
                params = {}
            until = params.get("until")
            if until is not None and int(until) > year:
                delayed.add(target)
        elif itype == "cancel_development":
            cancelled.add(target)
    return delayed, cancelled