"""B6 — per-asset deadspace detection.

Phase 3 change: the detector no longer requires a score record.
All decisions come from observed and derived metrics.
"""

from .. import __version__
from .layer1 import evaluate as layer1_eval
from .layer2 import evaluate as layer2_eval
from .layer3 import evaluate as layer3_eval
from .layer3_lbs import evaluate as layer3_lbs_eval
from .layer3_survival import evaluate_survival_floor
from .external import external_for
from .tiers import OPERATIONAL_FLAGS, evaluation_mode, is_full_control, tier_of
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
    # Phase 16 — layer3 now receives the l1/l2 verdict so its
    # `candidate_interventions` reflects the diagnosed state, not
    # just the asset type's legal action space.
    layer3 = layer3_eval(atype, layer1=layer1, layer2=layer2)

    # Phase 15 — pass authority into the classification. Developer-
    # held unsold residential can be a deadspace candidate; sold
    # residential cannot.
    authority = asset.get("authority") if hasattr(asset, "get") else None

    # v6.0 Phase 2 — a sold / advisory asset's operational record is not
    # visible to the developer, so its tier-1 operational flags are
    # dropped and replaced by tier-3a proxy flags (Google Places, LBS).
    proxy = None
    survival = None
    external = None
    suppressed = []
    if atype == "commercial" and not is_full_control(authority):
        layer1, layer2, suppressed = _drop_operational(layer1, layer2)
        external = external_for(asset["asset_id"], asset.get("subtype"))
        proxy = layer3_lbs_eval(external, thresholds=ds_cfg.get("proxy", {}))
        survival = evaluate_survival_floor(
            asset.to_dict(), external, assumptions, year=metrics.get("year"),
        )
        if survival.get("triggered"):
            proxy["reasons"].append("operating_hemorrhage")
            proxy["triggered"] = True

    # Ramp-up exemption needs completion_year and base_year so a
    # newly delivered asset (age < grace window) can be held at
    # "monitor" rather than escalated to deadspace_candidate while
    # tenants / residents are still arriving.
    completion_year = (
        asset.get("completion_year") if hasattr(asset, "get") else None
    )
    try:
        base_year = int(metrics["year"])
    except (KeyError, TypeError, ValueError):
        base_year = 2026

    status = decide_status(
        atype, layer1, layer2, layer3,
        authority=authority,
        completion_year=completion_year,
        base_year=base_year,
        proxy=proxy,
    )

    # Collect all flags into one list for urgency computation
    all_flags = (
        list(layer1.get("reasons", []))
        + list(layer2.get("reasons", []))
        + list((proxy or {}).get("reasons", []))
    )

    # Contributing factors (relative importance of what is going wrong)
    factors = compute_factors(layer1, layer2, extra_flags=(proxy or {}).get("reasons"))

    # Human-readable evidence
    evidence = build_evidence(atype, asset.get("subtype"), metrics.to_dict(),
                              proxy=proxy, survival=survival, external=external)

    return {
        "asset_id": asset["asset_id"],
        "year": int(metrics["year"]),
        "status": status,
        "flags": all_flags,
        "urgency_index": compute_urgency_index(all_flags),
        "layer1": layer1,
        "layer2": layer2,
        "layer3": layer3,
        "layer3a": proxy,
        "survival": survival,
        "flag_tiers": {f: tier_of(f) for f in all_flags},
        "suppressed_flags": suppressed,
        "evaluation_mode": evaluation_mode(authority),
        "contributing_factors": factors,
        "evidence": evidence,
        "model_version": __version__,
    }


def _drop_operational(layer1: dict, layer2: dict):
    """Remove flags built on operational data the developer cannot see."""
    suppressed = []

    def keep(layer):
        kept = []
        for f in layer.get("reasons", []):
            (suppressed if f in OPERATIONAL_FLAGS else kept).append(f)
        return {**layer, "reasons": kept, "triggered": len(kept) > 0}

    return keep(layer1), keep(layer2), suppressed