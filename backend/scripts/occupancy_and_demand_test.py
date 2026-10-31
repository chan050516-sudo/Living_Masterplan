import sys
from pathlib import Path
import pandas as pd

# 确保在 repo 根目录下运行
REPO_ROOT = Path('.').resolve()
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.derived.engine import compute_derived_metrics

print("正在计算 B3 指标（带空置折扣）...")
df = compute_derived_metrics(repo_root=REPO_ROOT, year=2026)

# 1. 找一个空置率极低的商业资产
commercial = df[(df["asset_type"] == "commercial") & (df["occupancy_rate"] < 0.30)]
if commercial.empty:
    print("没找到空置率 < 30% 的商业资产，无法对比")
else:
    target = commercial.iloc[0]
    aid = target["asset_id"]
    demand = target["effective_demand_m2"]
    print(f"空置资产 {aid} (入驻率: {target['occupancy_rate']:.1%}) 的 Huff 有效需求: {demand:.1f} m2")
    
    # 2. 找一个健康的商业资产
    healthy = df[(df["asset_type"] == "commercial") & (df["occupancy_rate"] > 0.80)].iloc[0]
    print(f"健康资产 {healthy['asset_id']} (入驻率: {healthy['occupancy_rate']:.1%}) 的 Huff 有效需求: {healthy['effective_demand_m2']:.1f} m2")
    
    print("\n验证逻辑：")
    print("如果空置资产的吸引力被折减，它的 effective_demand_m2 会显著小于同面积、同位置的健康资产。")