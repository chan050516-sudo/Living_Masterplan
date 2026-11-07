"""Survival OPEX floor — the `operating_hemorrhage` flag (v6.0 §4.5).

Early warning for a "bleeding" shoplot: estimate what the business earns
from its LBS footfall and compare it with the least it costs to stay open.

  estimated_revenue   = lbs_users_daily × conversion × avg_spend × operating_days
  survival_opex_floor = lettable_area_m2 × survival_opex_per_m2 × inflation_index

Both are tier 3a estimates. Rates come from assumptions.yml
`survival_analysis`; the constants below are used only when a subtype
is missing there.
"""

_DEFAULT_CONVERSION = 0.10
_DEFAULT_SPEND_RM = 25.0
_DEFAULT_OPEX_PER_M2 = 180.0
_DEFAULT_DAYS = 360


def _rate(cfg: dict, key: str, subtype, default):
    return (cfg.get(key) or {}).get(subtype, default)


def _inflation(cfg: dict, year) -> float:
    index = cfg.get("inflation_index") or {}
    if not index:
        return 1.0
    try:
        y = int(year)
    except (TypeError, ValueError):
        y = 2026
    known = sorted(int(k) for k in index)
    # Use the latest index year at or before `year`.
    eligible = [k for k in known if k <= y] or known[:1]
    return float(index.get(eligible[-1], index.get(str(eligible[-1]), 1.0)))


def evaluate_survival_floor(asset: dict, external: dict, assumptions: dict,
                            year=2026) -> dict:
    cfg = (assumptions or {}).get("survival_analysis", {})
    subtype = asset.get("subtype")
    users = (external or {}).get("lbs_unique_users_daily")
    if users is None:
        return {"triggered": False, "reason": "no_lbs_footfall"}

    try:
        lettable = float(asset.get("lettable_area_m2") or 0)
    except (TypeError, ValueError):
        lettable = 0.0
    if lettable <= 0:
        return {"triggered": False, "reason": "no_lettable_area"}

    conversion = _rate(cfg, "conversion_rate_by_subtype", subtype, _DEFAULT_CONVERSION)
    spend = _rate(cfg, "avg_spend_rm_by_subtype", subtype, _DEFAULT_SPEND_RM)
    days = _rate(cfg, "operating_days_by_subtype", subtype, _DEFAULT_DAYS)
    opex = _rate(cfg, "survival_opex_per_m2_by_subtype", subtype, _DEFAULT_OPEX_PER_M2)

    est_rev = users * conversion * spend * days
    floor = lettable * opex * _inflation(cfg, year)

    return {
        "triggered": est_rev < floor,
        "estimated_revenue_rm": round(est_rev, 0),
        "survival_opex_floor_rm": round(floor, 0),
        "hemorrhage_ratio": round(est_rev / floor, 2) if floor > 0 else None,
    }
