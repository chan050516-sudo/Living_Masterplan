"""Demand model helpers.

Commercial demand is projected via Huff gravity, using a precomputed
all-pairs effective distance matrix (Fix 1+4).
"""

from ..derived.huff import huff_gravity


def project_demand_commercial(distance_matrix, demand_nodes, supply_nodes,
                              alpha: float, beta: float) -> dict:
    """Returns { asset_id: effective_demand (persons) }."""
    return huff_gravity(
        distance_matrix, demand_nodes, supply_nodes, alpha=alpha, beta=beta,
    )


def project_demand_facility(population: float, service_per_capita: float) -> float:
    """Annual facility demand (persons/year) from projected population."""
    return population * service_per_capita