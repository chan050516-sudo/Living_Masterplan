import pandas as pd
import json
from pathlib import Path

base_dir = Path("bukit_jelutong/processed/business")
geom_dir = Path("bukit_jelutong/processed/geometry")

metrics = pd.read_csv(base_dir / "asset_metrics_enriched.csv")
assets = pd.read_csv(base_dir / "assets.csv")

# Merge asset_type into metrics
metrics_2026 = metrics[metrics["year"] == 2026].merge(
    assets[["asset_id", "asset_type"]], on="asset_id", how="left"
)

# 1. 检查 P-VAC 黄金地块
vacants = assets[assets["asset_type"] == "undeveloped_parcel"]
print(f"=== 1. Golden Parcels Check ===")
print(vacants[["asset_id", "asset_name", "land_area_m2"]].to_string(index=False))

# 2. 检查人口节点是否真的生成了
print(f"\n=== 2. Population File Audit ===")
pop_path = geom_dir / "population_bj.geojson"
with open(pop_path, "r", encoding="utf-8") as f:
    geo_data = json.load(f)

features = geo_data.get("features", [])
print(f"Total population nodes: {len(features)}")

# Check properties of first node
if features:
    print("Sample node properties:", features[0].get("properties"))
    
# Count by source
sources = [f.get("properties", {}).get("source") for f in features]
from collections import Counter
print("Source distribution:", Counter(sources))

# 3. 检查 Top 5 商业资产（是否吃到了外部溢出）
commercials = metrics_2026[metrics_2026["asset_type"] == "commercial"].copy()
commercials = commercials.sort_values("effective_demand_m2", ascending=False)
print(f"\n=== 3. Top 5 Commercial by Effective Demand ===")
for _, row in commercials.head(5).iterrows():
    print(f"  {row['asset_id']} ({row['subtype']}): Demand = {row['effective_demand_m2']:.1f} m2, DSR = {row.get('dsr', 0):.2f}")

# 4. 检查 mismatch
with open(base_dir / "deadspace_2026.json", "r", encoding="utf-8") as f:
    ds_list = json.load(f)
mismatch_count = sum(1 for rec in ds_list if "demographic_mismatch" in rec.get("flags", []))
print(f"\n=== 4. Demographic Mismatch Flags: {mismatch_count} ===")