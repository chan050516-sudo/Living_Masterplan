# backend/scripts/demo_extract.py
import json, sys
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))
from app.config import load_paths
from app.llm.tool_service import TownshipDataSource, get_nearby_assets

paths = load_paths()
base = REPO_ROOT / paths["base"]
with open(base / "business" / "asset_profiles_2026.json") as f:
    profiles = json.load(f)
ds = TownshipDataSource(REPO_ROOT, year=2026)


# [1] BLD-0037 完整 profile
print("=== [1] BLD-0037 FULL PROFILE ===")
print(json.dumps(profiles["BLD-0037"], indent=2, default=str))


# [2] 周边 commercial 简表
print("\n=== [2] BLD-0037 NEIGHBOURS (1200m) ===")
for n in get_nearby_assets(ds, "BLD-0037", radius_m=1200.0):
    p = profiles.get(n["asset_id"])
    if not p or p["identity"]["asset_type"] != "commercial":
        continue
    soc, diag = p.get("social") or {}, p.get("deadspace_diagnosis") or {}
    print(f"{n['asset_id']:<12} d={n['distance_m']:>5.0f}m "
          f"sub={(p['identity'].get('subtype') or '?'):<20} "
          f"auth={p['authority'].get('level'):<12} "
          f"occ={soc.get('occupancy_rate')} prox={soc.get('proxied_occupancy')} "
          f"status={diag.get('status'):<22} "
          f"flow={soc.get('flow_island_ratio')} "
          f"mism={soc.get('demographic_mismatch')} "
          f"flags={diag.get('flags', [])[:3]}")


# [3] 周边 full_control residential
print("\n=== [3] BLD-0037 NEIGHBOURS — full_control residential ===")
for n in get_nearby_assets(ds, "BLD-0037", radius_m=1500.0):
    p = profiles.get(n["asset_id"])
    if not p or p["identity"]["asset_type"] != "residential":
        continue
    if p["authority"].get("level") != "full_control":
        continue
    phys, soc = p.get("physical") or {}, p.get("social") or {}
    diag = p.get("deadspace_diagnosis") or {}
    print(f"{n['asset_id']:<12} d={n['distance_m']:>5.0f}m "
          f"sub={p['identity'].get('subtype')} "
          f"held={phys.get('developer_held_units')}/{phys.get('unit_count')} "
          f"occ={soc.get('occupancy_rate')} "
          f"status={diag.get('status')} flags={diag.get('flags', [])}")


# [4] Case 2 候选：single_shop sold 商业
print("\n=== [4] CASE 2 CANDIDATES — single_shop advisory commercial ===")
for aid, p in profiles.items():
    if p["identity"]["asset_type"] != "commercial":
        continue
    if p["authority"].get("level") != "advisory":
        continue
    subs = p.get("subunits") or []
    if len(subs) > 1:
        continue
    soc, diag = p.get("social") or {}, p.get("deadspace_diagnosis") or {}
    prox = soc.get("proxied_occupancy")
    if prox is None or float(prox) >= 0.5:
        continue
    print(f"{aid:<12} sub={(p['identity'].get('subtype') or '?'):<20} "
          f"prox={prox} flow={soc.get('flow_island_ratio')} "
          f"mism={soc.get('demographic_mismatch')} "
          f"presence={soc.get('business_presence_ratio')} "
          f"lbs={soc.get('lbs_unique_users_daily')} "
          f"status={diag.get('status'):<22} "
          f"flags={diag.get('flags', [])[:4]}")