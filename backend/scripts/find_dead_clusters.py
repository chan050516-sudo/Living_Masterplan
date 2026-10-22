"""Find geographic clusters of deadspace assets for Multi-Asset Demo."""
import sys
import math
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.llm.tool_service import TownshipDataSource

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

def main():
    repo_root = Path(__file__).resolve().parents[2]
    ds = TownshipDataSource(repo_root, year=2026)
    
    centroids = ds._load_centroids()
    
    # 找出所有烂掉的商业资产（排除住宅和空地）
    bad_commercials = []
    for aid, rec in ds.deadspace.items():
        if rec.get("status") != "deadspace_candidate":
            continue
        asset = ds._asset_row(aid)
        if not asset or asset.get("asset_type") != "commercial":
            continue
        if aid in centroids:
            bad_commercials.append(aid)
            
    # 找出所有的空地
    vacants = [aid for aid in centroids if aid.startswith("P-VAC")]

    print(f"Found {len(bad_commercials)} bad commercial assets.")
    print("Scanning for clusters of bad assets within 600m...\n")
    print("-" * 80)
    
    results = []
    
    for i, aid1 in enumerate(bad_commercials):
        x1, y1 = centroids[aid1]
        a1 = ds._asset_row(aid1)
        m1 = ds._metric_row(aid1, 2026) or {}
        occ1 = m1.get("occupancy_rate") or 0
        
        nearby_bad = []
        nearby_vacant = []
        
        # 找旁边一起烂的兄弟
        for aid2 in bad_commercials:
            if aid1 == aid2: continue
            x2, y2 = centroids[aid2]
            dist = math.hypot(x1-x2, y1-y2)
            if dist <= 600:
                a2 = ds._asset_row(aid2)
                m2 = ds._metric_row(aid2, 2026) or {}
                nearby_bad.append((aid2, a2.get("subtype"), dist, m2.get("occupancy_rate") or 0))
                
        # 找旁边的空地作为催化剂
        for vid in vacants:
            vx, vy = centroids[vid]
            dist = math.hypot(x1-vx, y1-vy)
            if dist <= 600:
                nearby_vacant.append((vid, dist))
                
        if len(nearby_bad) >= 1 and len(nearby_vacant) >= 1:
            results.append({
                "main": (aid1, a1.get("subtype"), occ1),
                "bads": nearby_bad,
                "vacs": nearby_vacant
            })
            
    # 排序打印最密集的集群
    if not results:
        print("No clusters found.")
        return
        
    # 简单去重（避免 A-B 和 B-A 都打印）
    seen = set()
    count = 0
    for r in results:
        key = tuple(sorted([r["main"][0]] + [b[0] for b in r["bads"]]))
        if key in seen: continue
        seen.add(key)
        
        print(f"🏢 Main Target: {r['main'][0]} ({r['main'][1]}) - Occ: {r['main'][2]*100:.1f}%")
        for b in r["bads"]:
            print(f"   ↳ Neighbor  : {b[0]} ({b[1]}) - Dist: {b[2]:.0f}m - Occ: {b[3]*100:.1f}%")
        for v in r["vacs"]:
            print(f"   ↳ Vacant Lot: {v[0]} - Dist: {v[1]:.0f}m")
        print("-" * 80)
        
        count += 1
        if count >= 5: # 只看前 5 个最好的集群
            break

if __name__ == "__main__":
    main()