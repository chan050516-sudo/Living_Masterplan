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
    Shared quantities (accessibility, Huff demand, canopy coverage, distance
    matrix) are precomputed so all derivers read from the same source.
    """
    asset: pd.Series
    business: dict
    geometry: dict
    benchmarks: dict
    assumptions: dict
    accessibility_score: Optional[float]
    huff_effective_demand: Optional[float]
    maintenance_surge_rm: Optional[float]
    graph: nx.Graph
    year: int
    # Canopy coverage ratio [0, 1] computed by the engine via spatial overlay.
    canopy_coverage: Optional[float] = None
    # All-pairs effective distances (Fix 1+4). Used by facility coverage.
    distance_matrix: Optional[dict] = None