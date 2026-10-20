"""Business diversity index (Shannon entropy) for a neighborhood.

Purpose: measure how varied the business mix is within a walking
radius of a given asset. Single-subtype clusters are riskier because
they share correlated demand shocks (e.g. all restaurants close when
office workers switch to remote work).
"""

import math
from collections import Counter
from typing import List, Optional


def shannon_diversity(subtypes: List[str], normalize: bool = True) -> float:
    """
    Shannon entropy of the subtype distribution.

    normalize=True returns a value in [0, 1]:
        0 = single subtype only
        1 = perfectly even distribution across all present subtypes
    normalize=False returns raw entropy in nats.
    """
    if not subtypes:
        return 0.0

    counts = Counter(subtypes)
    total = len(subtypes)

    if len(counts) <= 1:
        return 0.0

    entropy = -sum((c / total) * math.log(c / total) for c in counts.values())

    if not normalize:
        return entropy

    max_entropy = math.log(len(counts))
    if max_entropy <= 0:
        return 0.0
    return entropy / max_entropy


def neighborhood_diversity(
    asset_id: str,
    supply_nodes: List[dict],
    distance_matrix: dict,
    asset_vn: str,
    radius_m: float,
) -> float:
    """
    Compute Shannon diversity of subtypes within `radius_m` of the asset.

    supply_nodes : list with keys: asset_id, node, subtype
    asset_vn : the asset's virtual node in the same distance matrix
    """
    if asset_vn not in distance_matrix:
        return 0.0

    row = distance_matrix[asset_vn]
    subtypes = []

    for s in supply_nodes:
        if s["asset_id"] == asset_id:
            continue  # exclude self
        s_node = s["node"]
        if s_node is None:
            continue
        d = row.get(s_node)
        if d is None:
            continue
        if d <= radius_m:
            st = s.get("subtype")
            if st:
                subtypes.append(st)

    return shannon_diversity(subtypes, normalize=True)