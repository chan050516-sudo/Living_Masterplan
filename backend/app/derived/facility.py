"""Community facility derived metrics.

Phase 1 bridge: still uses the deprecated accessibility_score bridge
from the walking profile. Full profile-aware refactor is scheduled for
a later phase.
"""

import math
from .context import DerivationContext


def derive_facility(ctx: DerivationContext) -> dict:
    asset = ctx.asset
    year = ctx.year

    metrics = ctx.business["asset_metrics"]
    row = metrics[
        (metrics["asset_id"] == asset["asset_id"]) &
        (metrics["year"] == year)
    ]
    if row.empty:
        raise ValueError(f"No asset_metrics row for {asset['asset_id']} year {year}")
    raw = row.iloc[0]

    def _get(col):
        v = raw.get(col)
        if v is None:
            return None
        try:
            if math.isnan(float(v)):
                return None
        except (TypeError, ValueError):
            return None
        return float(v)

    utilisation = _get("utilisation_rate")
    accessibility = ctx.accessibility_score

    # Service coverage: use 10-min walking coverage ratio from the
    # Phase 1 profile. This is a bridge until the facility-specific
    # service_coverage logic is refactored.
    service_coverage = None
    if ctx.walking_profile:
        service_coverage = ctx.walking_profile.get("coverage_ratio_10min")

    # Cost per user
    opex = asset.get("opex_annual_rm")
    maintenance = asset.get("maintenance_annual_rm")
    annual_users = None
    if utilisation is not None and asset.get("capacity"):
        annual_users = utilisation * float(asset["capacity"]) * 365.0

    cost_per_user = None
    if annual_users and annual_users > 0:
        total = 0.0
        if opex is not None:
            total += float(opex)
        if maintenance is not None:
            total += float(maintenance)
        cost_per_user = total / annual_users

    return {
        "asset_id": asset["asset_id"],
        "year": year,
        "utilisation_rate": utilisation,
        "service_coverage": service_coverage,
        "cost_per_user_rm": cost_per_user,
        "accessibility_score": accessibility,  # deprecated bridge
        "metric_source": "derived",
        "model_version": "0.4.0",
    }