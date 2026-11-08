"""Layer 3a — Proxied operating evidence for sold / advisory assets.

A developer cannot see a sold shoplot's occupancy or income. This layer
reads two external proxies instead (v6.0 §4.2):

  Google Places — is a business operating, how is it rated, did it change
  LBS / Kido    — how many people visit, how long they stay, whether
                  nearby footfall actually reaches the asset

Every flag raised here is tier 3a: valid for a judgement, never stated
as an observed fact.
"""

DEFAULTS = {
    "proxied_occupancy_below": 0.50,
    "proxied_vacancy_above_months": 12.0,
    "business_presence_below": 0.30,
    "business_turnover_at_least": 2,
    "business_vitality_below": 0.30,
    "lbs_footfall_peer_factor": 0.40,
    "lbs_dwell_peer_factor": 0.50,
    "flow_island_ratio_below": 0.30,
    # data_conflict: a business exists but nobody visits, or the reverse
    "conflict_presence_high": 0.70,
    "conflict_demand_low": 0.10,
    "conflict_presence_low": 0.30,
    "conflict_demand_high": 0.50,
}

# D-21: LBS footfall is tried first. Counting real visitors to the shop is
# a more reliable occupancy signal than Google listings, which stay
# "OPERATIONAL" long after a shop goes quiet (mock check vs hidden truth:
# LBS r=0.95, Google r=0.76). Google is the fallback.
_OCCUPANCY_PROXIES = (
    ("proxied_occupancy_lbs", "kido_dynamics_mock"),
    ("proxied_occupancy_google", "google_places_mock"),
)


def evaluate(external: dict, thresholds: dict = None) -> dict:
    t = {**DEFAULTS, **(thresholds or {})}
    reasons = []
    ext = external or {}

    occ, occ_source = None, None
    for key, source in _OCCUPANCY_PROXIES:
        if ext.get(key) is not None:
            occ, occ_source = ext[key], source
            break
    if occ is not None and occ < t["proxied_occupancy_below"]:
        reasons.append("low_occupancy_proxied")

    vac = ext.get("proxied_vacancy_duration")
    if vac is not None and vac > t["proxied_vacancy_above_months"]:
        reasons.append("long_vacancy_proxied")

    presence = ext.get("business_presence_ratio")
    if presence is not None and presence < t["business_presence_below"]:
        reasons.append("business_presence_low")

    turnover = ext.get("business_turnover_count")
    if turnover is not None and turnover >= t["business_turnover_at_least"]:
        reasons.append("business_turnover_high")

    vitality = ext.get("business_vitality_score")
    if vitality is not None and vitality < t["business_vitality_below"]:
        reasons.append("business_vitality_low")

    _check_lbs_footfall(reasons, ext, t)
    _check_lbs_dwell(reasons, ext, t)
    _check_flow_island(reasons, ext, t)
    _check_data_conflict(reasons, ext, t)

    return {
        "triggered": len(reasons) > 0,
        "reasons": reasons,
        "proxied_occupancy": occ,
        "proxied_occupancy_source": occ_source,
    }


def _check_lbs_footfall(reasons, ext, t):
    """LBS footfall well below the subtype's peer median."""
    users = ext.get("lbs_unique_users_daily")
    benchmark = ext.get("lbs_peer_users_median")
    if users is not None and benchmark and users < benchmark * t["lbs_footfall_peer_factor"]:
        reasons.append("low_footfall_lbs")


def _check_lbs_dwell(reasons, ext, t):
    """Visitors leave too quickly for this subtype."""
    dwell = ext.get("lbs_dwell_time_minutes")
    benchmark = ext.get("lbs_peer_dwell_median")
    if dwell is not None and benchmark and dwell < benchmark * t["lbs_dwell_peer_factor"]:
        reasons.append("short_dwell_lbs")


def _check_flow_island(reasons, ext, t):
    """Network-isolated: footfall exists nearby but does not reach the asset."""
    ratio = ext.get("flow_island_ratio")
    if ratio is not None and ratio < t["flow_island_ratio_below"]:
        reasons.append("flow_island")


def _check_data_conflict(reasons, ext, t):
    """Google Places and LBS disagree, so neither can be trusted alone."""
    presence = ext.get("business_presence_ratio")
    demand = ext.get("observed_demand_ratio")
    if presence is None or demand is None:
        return
    if (
        (presence > t["conflict_presence_high"] and demand < t["conflict_demand_low"])
        or (presence < t["conflict_presence_low"] and demand > t["conflict_demand_high"])
    ):
        reasons.append("data_conflict")
