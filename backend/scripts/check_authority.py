"""Check authority levels for specific assets and their neighbors."""
import sys
import math
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.llm.tool_service import TownshipDataSource

def main():
    repo_root = Path(__file__).resolve().parents[2]
    ds = TownshipDataSource(repo_root, year=2026)
    centroids = ds._load_centroids()

    target_ids = ["BLD-0741", "BLD-0643"]
    
    print("🎯 目标资产 Authority 排查:")
    for aid in target_ids:
        asset = ds._asset_row(aid)
        if asset:
            print(f"  {aid}: Authority={asset.get('authority')}, Ownership={asset.get('ownership_status')}")
        else:
            print(f"  {aid}: Not found!")
            
    print("\n🔍 扫描 BLD-0741 周围 600m 内的死区邻居:")
    x1, y1 = centroids["BLD-0741"]
    
    # 获取所有死区候选
    flagged = [
        aid for aid, rec in ds.deadspace.items() 
        if rec.get("status") in ("deadspace_candidate", "monitor") and aid.startswith("BLD")
    ]
    
    results = []
    for aid in flagged:
        if aid == "BLD-0741": continue
        if aid not in centroids: continue
        x2, y2 = centroids[aid]
        dist = math.hypot(x1-x2, y1-y2)
        
        if dist <= 600:
            asset = ds._asset_row(aid)
            m = ds._metric_row(aid, 2026) or {}
            occ = m.get("occupancy_rate") or 0
            auth = asset.get("authority")
            own = asset.get("ownership_status")
            sub = asset.get("subtype")
            
            # 只关注有特点的（比如不是 full_control，或者入住率极低）
            if auth != "full_control" or occ < 0.20:
                results.append({
                    "id": aid, "sub": sub, "dist": dist, "occ": occ, 
                    "auth": auth, "own": own
                })
                
    # 按距离排序
    results.sort(key=lambda x: x["dist"])
    
    for r in results:
        highlight = "🌟" if r["auth"] in ("advisory", "shared") else "  "
        print(f"  {highlight} {r['id']:<10} | {r['sub']:<18} | Dist: {r['dist']:>3.0f}m | Occ: {r['occ']*100:>4.1f}% | Auth: {r['auth']:<12} ({r['own']})")

if __name__ == "__main__":
    main()