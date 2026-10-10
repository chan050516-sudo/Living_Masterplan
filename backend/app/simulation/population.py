"""Population model: P_t = P_0 * (1 + g)^t."""


def project_population(base_population: float, base_year: int, target_year: int,
                       growth_rate: float) -> float:
    t = target_year - base_year
    return base_population * (1.0 + growth_rate) ** t


def project_population_by_age(base_population_by_age: dict, base_year: int,
                              target_year: int, growth_rate: float) -> dict:
    """Scale each age band uniformly (simplified — no cohort-component model)."""
    factor = (1.0 + growth_rate) ** (target_year - base_year)
    return {k: v * factor for k, v in base_population_by_age.items()}