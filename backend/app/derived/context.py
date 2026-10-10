"""Shared computation context passed to per-asset derivation functions."""

from dataclasses import dataclass
from typing import Optional
import networkx as nx
import pandas as pd


@dataclass
class DerivationContext:
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