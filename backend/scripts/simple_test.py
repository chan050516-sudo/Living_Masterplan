import pandas as pd
df = pd.read_csv("bukit_jelutong/processed/business/asset_metrics_enriched.csv")

# 1. 排放因子变化：同样的 energy_kwh，carbon 应该涨 33%
print("Carbon/Energy ratio:",
      (df["carbon_operational_tco2e"] / df["energy_kwh"]).dropna().median())
# 期望 ~0.000769

# 2. 隐含碳按类型分化
for st in ("clinic", "terrace", "supermarket"):
    sub = df[df["subtype"] == st]
    if not sub.empty:
        print(f"{st}: embodied_total median =",
              sub["embodied_carbon_total_tco2e"].median())

# 3. 树冠增长 — 对比 B4 的 2026 vs 2033
import json
with open("bukit_jelutong/processed/business/scenarios/SC-CURRENT.json") as f:
    sc = json.load(f)
canopy_2026 = sc["years"]["2026"]["assets"].get("BLD-0037", {}).get("canopy_coverage")
canopy_2033 = sc["years"]["2033"]["assets"].get("BLD-0037", {}).get("canopy_coverage")
print(f"BLD-0037 canopy: 2026={canopy_2026}, 2033={canopy_2033}")