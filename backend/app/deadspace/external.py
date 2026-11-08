"""Read the external proxy tables built by ingest_external_data.py.

Two tables feed the 3a flags for sold assets:
  business/asset_business_presence.csv  (Google Places mock)
  business/asset_lbs_metrics.csv        (LBS / Kido mock)

Both are a 2026 snapshot. Peer benchmarks (median per subtype) are
computed here once so layer3_lbs can compare an asset to its peers.
"""

import logging
import math
from functools import lru_cache
from pathlib import Path

import pandas as pd

from ..config import load_paths

log = logging.getLogger(__name__)

_PRESENCE_FIELDS = (
    "business_presence_ratio", "proxied_occupancy_google",
    "business_vitality_score", "proxied_vacancy_duration",
    "business_turnover_count", "unit_mix_unit_count",
    "operational_place_count",
)
_LBS_FIELDS = (
    "lbs_unique_users_daily", "lbs_dwell_time_minutes",
    "lbs_visit_frequency_monthly", "proxied_occupancy_lbs",
    "traffic_exposure_vpd", "flow_island_ratio", "observed_demand_ratio",
)


def _clean(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _read(repo_root: Path, key: str):
    paths = load_paths()
    rel = paths.get("business", {}).get(key)
    if not rel:
        return None
    path = repo_root / paths["base"] / rel
    if not path.exists():
        log.info("External table %s not found at %s", key, path)
        return None
    return pd.read_csv(path)


@lru_cache(maxsize=1)
def _load(repo_root_str: str) -> dict:
    repo_root = Path(repo_root_str)
    assets = _read(repo_root, "assets")
    subtype_of = (
        dict(zip(assets["asset_id"], assets["subtype"]))
        if assets is not None else {}
    )

    by_asset: dict = {}
    for key, fields in (
        ("asset_business_presence", _PRESENCE_FIELDS),
        ("asset_lbs_metrics", _LBS_FIELDS),
    ):
        df = _read(repo_root, key)
        if df is None:
            continue
        for row in df.to_dict("records"):
            rec = by_asset.setdefault(row["asset_id"], {})
            for f in fields:
                if f in row:
                    rec[f] = _clean(row[f])

    # Peer medians per subtype, from the assets that have LBS data.
    peers: dict = {}
    for aid, rec in by_asset.items():
        st = subtype_of.get(aid)
        if st is None:
            continue
        for f in ("lbs_unique_users_daily", "lbs_dwell_time_minutes"):
            if rec.get(f) is not None:
                peers.setdefault(st, {}).setdefault(f, []).append(rec[f])
    peer_median = {
        st: {f: float(pd.Series(v).median()) for f, v in fields.items()}
        for st, fields in peers.items()
    }
    peer_users = {
        st: sorted(fields.get("lbs_unique_users_daily", []))
        for st, fields in peers.items()
    }
    return {"by_asset": by_asset, "peer_median": peer_median,
            "peer_users": peer_users}


def external_for(asset_id: str, subtype, repo_root: Path = None) -> dict:
    """Proxy fields for one asset, plus its subtype peer medians.

    Returns {} when the asset has no external data.
    """
    repo_root = repo_root or Path(__file__).resolve().parents[3]
    try:
        data = _load(str(repo_root))
    except Exception as e:  # never let a bad mock file break B6
        log.warning("Could not load external proxy tables: %s", e)
        return {}
    rec = data["by_asset"].get(asset_id)
    if not rec:
        return {}
    peer = data["peer_median"].get(subtype, {})
    return {
        **rec,
        "lbs_peer_users_median": peer.get("lbs_unique_users_daily"),
        "lbs_peer_dwell_median": peer.get("lbs_dwell_time_minutes"),
    }


def lbs_users_percentile(asset_id: str, subtype, repo_root: Path = None):
    """Where this asset's LBS footfall sits among its subtype peers (0-1).

    None when the asset has no LBS data or has no peers to compare with.
    """
    repo_root = repo_root or Path(__file__).resolve().parents[3]
    try:
        data = _load(str(repo_root))
    except Exception as e:
        log.warning("Could not load external proxy tables: %s", e)
        return None
    users = (data["by_asset"].get(asset_id) or {}).get("lbs_unique_users_daily")
    peers = data["peer_users"].get(subtype) or []
    if users is None or len(peers) < 2:
        return None
    return sum(1 for p in peers if p <= users) / len(peers)


def huff_vitality(asset_id: str, subtype, occupancy, use_lbs: bool) -> float:
    """Huff attractiveness multiplier for a commercial asset (v6.0 §5.2).

    Legacy: occupancy clamped to [0.1, 1.0]. With `use_lbs` (feature
    flag huff_lbs_attractiveness) and LBS data available, blend 60%
    footfall percentile within the subtype with 40% occupancy, so a
    busy small kopitiam can outcompete a quiet large supermarket.
    """
    occ_score = max(0.1, min(1.0, occupancy))
    if not use_lbs:
        return occ_score
    lbs_score = lbs_users_percentile(asset_id, subtype)
    if lbs_score is None:
        return occ_score
    return max(0.1, 0.6 * lbs_score + 0.4 * occ_score)
