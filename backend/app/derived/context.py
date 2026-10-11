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
    benchmarks: dict
    assumptions: dict
    accessibility_score: Optional[float]
    huff_effective_demand: Optional[float]
    maintenance_surge_rm: Optional[float]
    graph: nx.Graph
    year: int
    canopy_coverage: Optional[float] = None
    distance_matrix: Optional[dict] = None

    # NEW (Phase 1): per-mode accessibility profiles.
    # Populated by engine after the distance matrix is computed.
    walking_profile: Optional[dict] = None
    driving_profile: Optional[dict] = None