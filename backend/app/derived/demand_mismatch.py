"""Demographic demand mismatch between an asset and its catchment.

Purpose: flag assets whose subtype does not match the surrounding
population. Classic example: a youth fashion outlet in a
predominantly senior area, or a family-sized supermarket in a
singles-dominated apartment precinct.

The output is a single mismatch score in [0, 1]:
    0 = perfect alignment
    1 = complete mismatch
"""

from typing import Optional


# ------------------------------------------------------------------
# Target-group matching rules
# ------------------------------------------------------------------
#
# Each entry maps a taxonomy demographic tag to a check function that
# takes the population profile (dict with age_0_14, age_15_64,
# age_65_plus, total) and returns a match score in [0, 1].

def _match_young_families(profile: dict) -> float:
    total = profile.get("total", 0) or 1
    child_ratio = profile.get("age_0_14", 0) / total
    # Full match at 25% children, zero below 10%
    if child_ratio >= 0.25:
        return 1.0
    if child_ratio <= 0.10:
        return 0.0
    return (child_ratio - 0.10) / 0.15


def _match_seniors(profile: dict) -> float:
    total = profile.get("total", 0) or 1
    senior_ratio = profile.get("age_65_plus", 0) / total
    if senior_ratio >= 0.25:
        return 1.0
    if senior_ratio <= 0.10:
        return 0.0
    return (senior_ratio - 0.10) / 0.15


def _match_workers(profile: dict) -> float:
    total = profile.get("total", 0) or 1
    worker_ratio = profile.get("age_15_64", 0) / total
    if worker_ratio >= 0.65:
        return 1.0
    if worker_ratio <= 0.50:
        return 0.0
    return (worker_ratio - 0.50) / 0.15


def _match_students(profile: dict) -> float:
    total = profile.get("total", 0) or 1
    student_ratio = profile.get("age_0_14", 0) / total + profile.get("age_15_64", 0) / total * 0.2
    if student_ratio >= 0.30:
        return 1.0
    if student_ratio <= 0.15:
        return 0.0
    return (student_ratio - 0.15) / 0.15


MATCH_RULES = {
    "young_families": _match_young_families,
    "seniors": _match_seniors,
    "workers": _match_workers,
    "students": _match_students,
    # The following tags are treated as "all": no mismatch.
    "families": lambda p: 1.0,
    "young_adults": lambda p: 0.5,   # weakly matched; will not dominate the score
    "singles": lambda p: 0.5,
    "all": lambda p: 1.0,
}


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def demographic_mismatch(
    population_profile: dict,
    target_demographics: list,
) -> float:
    """
    Compute mismatch between an asset's target demographics and the
    population in its catchment.

    Returns mismatch in [0, 1].
        0 = asset targets people who are present
        1 = asset targets people who are absent
    """
    if not target_demographics:
        return 0.0

    if "all" in target_demographics:
        return 0.0

    match_scores = []
    for tag in target_demographics:
        rule = MATCH_RULES.get(tag)
        if rule is None:
            continue
        match_scores.append(rule(population_profile))

    if not match_scores:
        return 0.0

    # Take the maximum match; a subtype succeeds if it aligns with at
    # least one target group.
    best_match = max(match_scores)
    return max(0.0, 1.0 - best_match)


def aggregate_catchment_profile(
    demand_entries: list,
    distance_matrix: dict,
    asset_entry: dict,
    max_distance_m: Optional[float] = None,
) -> dict:
    """
    Build an aggregated population profile from demand nodes that are
    reachable from the asset within a distance threshold.

    demand_entries : list of dicts with keys:
        demand_id, virtual_node, off_distance,
        total_population, age_0_14, age_15_64, age_65_plus
    distance_matrix : all-pairs distances from the asset's mode pipeline
    asset_entry : {"virtual_node": vn_id, "off_distance": m}
    max_distance_m : optional cutoff; if None, use all reachable nodes

    Returns a dict with total, age_0_14, age_15_64, age_65_plus.
    """
    profile = {"total": 0.0, "age_0_14": 0.0, "age_15_64": 0.0, "age_65_plus": 0.0}

    if asset_entry is None:
        return profile
    asset_vn = asset_entry["virtual_node"]
    asset_off = asset_entry["off_distance"]
    if asset_vn not in distance_matrix:
        return profile

    row = distance_matrix[asset_vn]

    for d in demand_entries:
        d_vn = d["virtual_node"]
        d_off = d["off_distance"]
        d_network = row.get(d_vn)
        if d_network is None:
            continue

        d_total = asset_off + d_network + d_off
        if max_distance_m is not None and d_total > max_distance_m:
            continue

        pop = d.get("total_population", 0.0)
        if pop <= 0:
            continue

        profile["total"] += pop
        profile["age_0_14"] += d.get("age_0_14", 0.0) or 0.0
        profile["age_15_64"] += d.get("age_15_64", 0.0) or 0.0
        profile["age_65_plus"] += d.get("age_65_plus", 0.0) or 0.0

    return profile