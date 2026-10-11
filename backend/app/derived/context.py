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
    This ensures all derivers read from the same source of truth for shared
    quantities (accessibility, Huff demand, canopy coverage, etc.).
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
    # P0.4: canopy coverage ratio [0, 1] computed by the engine via spatial
    # overlay with green_blue.geojson. None if data is missing.
    canopy_coverage: Optional[float] = None