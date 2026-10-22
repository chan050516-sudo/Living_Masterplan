"""Shared computation context passed to per-asset derivation functions."""

from dataclasses import dataclass
from typing import Optional
import networkx as nx
import pandas as pd


@dataclass
class DerivationContext:
    """
    Per-asset computation context.

    Computed once in the B3 engine and passed to each asset-specific deriver.
    """
    asset: pd.Series
    business: dict
    geometry: dict
    assumptions: dict
    accessibility_score: Optional[float]
    huff_effective_demand: Optional[float]           # persons (legacy)
    huff_effective_demand_m2: Optional[float]        # m² (total across subtypes)
    graph: nx.Graph
    year: int
    canopy_coverage: Optional[float] = None
    distance_matrix: Optional[dict] = None
    walking_profile: Optional[dict] = None
    driving_profile: Optional[dict] = None

    # Phase 2 additions
    catchment_population_profile: Optional[dict] = None   # age structure
    neighborhood_diversity: Optional[float] = None

    # Phase B.1 — per-subtype Huff demand.
    # A commercial asset with a unit_mix has one demand figure per
    # subtype; a commercial asset without one carries a single-entry
    # dict keyed by its own subtype. huff_effective_demand_m2 is the
    # sum of this dict for backwards compatibility.
    huff_by_subtype: Optional[dict] = None