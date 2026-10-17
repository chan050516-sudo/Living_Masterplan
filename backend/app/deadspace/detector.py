"""B6 — per-asset deadspace detection.

Phase 3 change: the detector no longer requires a score record.
All decisions come from observed and derived metrics.
"""

from .. import __version__
from .layer1 import evaluate as layer1_eval
from .layer2 import evaluate as layer2_eval
from .layer3 import evaluate as layer3_eval
from .factors import compute_factors
from .evidence import build_evidence
from .status import decide_status
from .urgency import compute_urgency_index


def detect_deadspace_for_asset(
    asset,
    metrics,
    assumptions,
) -> dict:
    """
    asset:        Series from assets.csv
    metrics:      Series from asset_metrics_enriched.csv
    assumptions:  loaded assumptions.yml

    Returns a dict describing the flags, factors, and status.
    """
    atype = asset["asset_type"]
    ds_cfg = assumptions.get("deadspace", {})
    l1_t = ds_cfg.get("layer1", {})
    l2_t = ds_cfg.get("layer2", {})

    layer1 = layer1_eval(atype, metrics.to_dict(), thresholds=l1_t)
    layer2 = layer2_eval(atype, asset.to_dict(), metrics.to_dict(), thresholds=l2_t)
    layer3 = layer3_eval(atype)

    # Phase 15 — pass authority into the classification. Developer-
    # held unsold residential can be a deadspace candidate; sold
    # residential cannot.
    authority = asset.get("authority") if hasattr(asset, "get") else None
    status = decide_status(atype, layer1, layer2, layer3, authority=authority)

    # Collect all flags into one list for urgency computation
    all_flags = (
        list(layer1.get("reasons", []))
        + list(layer2.get("reasons", []))
    )

    # Contributing factors (relative importance of what is going wrong)
    factors = compute_factors(layer1, layer2)

    # Human-readable evidence
    evidence = build_evidence(atype, asset.get("subtype"), metrics.to_dict())

    return {
        "asset_id": asset["asset_id"],
        "year": int(metrics["year"]),
        "status": status,
        "flags": all_flags,
        "urgency_index": compute_urgency_index(all_flags),
        "layer1": layer1,
        "layer2": layer2,
        "layer3": layer3,
        "contributing_factors": factors,
        "evidence": evidence,
        "model_version": __version__,
    }