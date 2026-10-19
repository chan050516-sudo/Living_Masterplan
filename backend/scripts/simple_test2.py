# 1. 确认 park 面积分布（M4）
import json
from pathlib import Path
base = Path("bukit_jelutong/processed/business")
assets = __import__("pandas").read_csv(base / "assets.csv")
green = assets[assets["asset_type"] == "green_space"]
print(green[["asset_id", "land_area_m2"]].sort_values(
    "land_area_m2", ascending=False).head(20))

# 2. 确认 declining 的真实触发（M2 / M6）
import pandas as pd
from pathlib import Path
m = pd.read_csv(
    Path("bukit_jelutong/processed/business/asset_metrics_enriched.csv")
)
m26 = m[m["year"] == 2026]
print(m26["trajectory_class"].value_counts(dropna=False))

# 3. 确认 facilities 的 utilisation 分布（M3）
import pandas as pd
from pathlib import Path
m = pd.read_csv(
    Path("bukit_jelutong/processed/business/asset_metrics_enriched.csv")
)
a = pd.read_csv(Path("bukit_jelutong/processed/business/assets.csv"))
m26 = m[m["year"] == 2026].merge(a[["asset_id", "asset_type"]], on="asset_id")
f = m26[m26["asset_type"] == "community_facility"]
print(f["utilisation_rate"].describe())