"""Supply model: S_t = S_0 + sum of active projects."""


def active_projects_in_year(projects_df, year: int, scenario_id: str) -> list:
    """
    Returns projects whose planned_delivery_year <= year AND that are not
    cancelled/delayed by the given scenario.
    """
    if projects_df is None or projects_df.empty:
        return []

    active = []
    for _, p in projects_df.iterrows():
        status = p.get("project_status")
        if status == "cancelled":
            continue
        delivery = p.get("planned_delivery_year")
        if delivery is None or int(delivery) > year:
            continue
        active.append(p.to_dict())
    return active


def project_supply_additions(active_projects: list) -> float:
    """Sum GFA from active projects."""
    return sum(float(p.get("gfa_m2") or 0) for p in active_projects)