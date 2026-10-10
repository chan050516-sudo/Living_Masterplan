"""Demand model.

Uses Huff gravity on projected population. Facility demand uses per-capita
service coefficients. Commercial demand is obtained from Huff allocation.
"""

from ..derived.huff import huff_gravity


def project_demand_commercial(G, demand_nodes, supply_nodes,
                              alpha: float, beta: float, gamma: float) -> dict:
    """Returns { asset_id: effective_demand }"""
    return huff_gravity(G, demand_nodes, supply_nodes,
                        alpha=alpha, beta=beta, gamma=gamma)


def project_demand_facility(population: float, service_per_capita: float) -> float:
    return population * service_per_capita