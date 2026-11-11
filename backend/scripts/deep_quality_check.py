import json
import pandas as pd
from pathlib import Path
import sys

# 修正路径解析：从 backend/scripts/ 往上跳两级才是真正的项目根目录
REPO_ROOT = Path(__file__).resolve().parents[2]
BASE = REPO_ROOT / "bukit_jelutong" / "processed" / "business"

# 确保路径存在
if not (BASE / "deadspace_2026.json").exists():
    print(f"错误: 找不到 {BASE / 'deadspace_2026.json'}，请检查当前路径。")
    sys.exit(1)

# 加载数据
with open(BASE / "deadspace_2026.json", "r", encoding="utf-8") as f:
    deadspace = pd.DataFrame(json.load(f))

assets = pd.read_csv(BASE / "assets.csv")
metrics = pd.read_csv(BASE / "asset_metrics_enriched.csv")
metrics = metrics[metrics["year"] == 2026]

# 加载外部代理数据
presence = pd.read_csv(BASE / "asset_business_presence.csv")
lbs = pd.read_csv(BASE / "asset_lbs_metrics.csv")

# 合并主数据
df = deadspace.merge(assets[["asset_id", "asset_type", "authority", "ownership_status", "developer_held_units", "lettable_area_m2"]], on="asset_id")
df = df.merge(metrics[["asset_id", "occupancy_rate", "noi_rm", "stranded_carbon_ratio"]], on="asset_id", how="left")
df = df.merge(presence[["asset_id", "business_presence_ratio", "consumer_facing_unit_count", "operational_place_count"]], on="asset_id", how="left")
df = df.merge(lbs[["asset_id", "lbs_unique_users_daily", "proxied_occupancy_lbs", "flow_island_ratio"]], on="asset_id", how="left")

# ==========================================
# 1. Commercial 的完整全貌
# ==========================================
print("\n=== 1. Commercial 状态与 Authority 交叉表 ===")
comm = df[df["asset_type"] == "commercial"]
print(pd.crosstab(comm["authority"], comm["status"]))
print("\n商业地产总数:", len(comm), "其中 healthy 数量:", len(comm[comm["status"] == "healthy"]))

monitor_comm = comm[comm["status"] == "monitor"]
if not monitor_comm.empty:
    print("\n处于 monitor 状态的商业资产，触发最多的 Flag:")
    flags = []
    for f in monitor_comm["flags"]: flags.extend(f)
    print(pd.Series(flags).value_counts().head(3))

# ==========================================
# 2. Residential 死空间的真实性
# ==========================================
print("\n=== 2. Residential deadspace_candidate 的真实性 ===")
res_dead = df[(df["asset_type"] == "residential") & (df["status"] == "deadspace_candidate")]
print("住宅死空间总数:", len(res_dead))
if not res_dead.empty:
    print("住宅死空间的 ownership_status 分布:")
    print(res_dead["ownership_status"].value_counts())
    print("住宅死空间的 developer_held_units 分布:")
    print(res_dead["developer_held_units"].value_counts())

    if len(res_dead[res_dead["ownership_status"] == "sold"]) > 0:
        print("\n⚠️ 警告: 有已卖出的住宅被判定为死空间！这是误报。")
    else:
        print("\n✅ 合理: 所有住宅死空间都是开发商持有的未售资产 (developer_held)。")

# ==========================================
# 3. 为什么 operating_hemorrhage (存活成本倒挂) 没有触发？
# ==========================================
print("\n=== 3. Sold Commercial 的代理数据真实度 ===")
sold_comm = comm[comm["authority"] == "advisory"]
has_proxy = sold_comm[sold_comm["business_presence_ratio"].notna()]

print(f"有代理数据的 Sold 商业资产数量: {len(has_proxy)}")
if not has_proxy.empty:
    print("商业存在率 (business_presence_ratio) 分布:")
    print(has_proxy["business_presence_ratio"].describe())

hemorrhage_count = 0
for f in has_proxy["flags"]:
    if "operating_hemorrhage" in f: hemorrhage_count += 1
print(f"\n触发 operating_hemorrhage 的 Sold 商业资产数量: {hemorrhage_count}")
if hemorrhage_count == 0:
    print("💡 原因分析: 说明计算出的 estimated_revenue 依然大于 opex_floor。可能 LBS 人流给的太高，或者商铺面积太小导致 opex 成本低。")

# ==========================================
# 4. LBS 数据与 Flag 的匹配度
# ==========================================
print("\n=== 4. Sold 商业资产的 Flow Island 情况 ===")
flow_islands = has_proxy[has_proxy["flags"].apply(lambda x: "flow_island" in x)]
print(f"属于 flow_island 的资产数: {len(flow_islands)}")
if not flow_islands.empty:
    print(flow_islands[["asset_id", "flow_island_ratio", "lbs_unique_users_daily", "status"]].head(5).to_string())

# ==========================================
# 5. 展示几个典型的 Sold 死空间和健康案例
# ==========================================
print("\n=== 5. 典型案例对比 (Sold Commercial) ===")
cols = ["asset_id", "status", "intervention_mode", "business_presence_ratio", "lbs_unique_users_daily", "flags"]

print("\n--- 典型案例: 被判为 deadspace_candidate 的 Sold 商铺 ---")
if not sold_comm[sold_comm["status"] == "deadspace_candidate"].empty:
    print(sold_comm[sold_comm["status"] == "deadspace_candidate"][cols].head(3).to_string())
else:
    print("无")

print("\n--- 对比案例: 判为 monitor 的 Sold 商铺 ---")
if not sold_comm[sold_comm["status"] == "monitor"].empty:
    print(sold_comm[sold_comm["status"] == "monitor"][cols].head(3).to_string())
else:
    print("无")