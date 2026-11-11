import sys
from pathlib import Path

# === 修正：从 backend/scripts/ 往上跳一级到 backend/，这样就能 import app 了 ===
BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

import pandas as pd
import numpy as np
import json

from app.config import load_paths
from app.deadspace.layer1 import DEFAULTS

BASE = REPO_ROOT / "bukit_jelutong" / "processed" / "business"
metrics_df = pd.read_csv(BASE / "asset_metrics_enriched.csv")
assets_df = pd.read_csv(BASE / "assets.csv")

metrics = metrics_df[metrics_df["year"] == 2026]
merged = metrics.merge(assets_df[["asset_id", "asset_type", "authority"]], on="asset_id")
comm = merged[merged["asset_type"] == "commercial"].copy()

print("=== 1. 各 Subtype 的动态统计阈值 (Q1 - 1.5*IQR) ===")
for subtype, group in comm.groupby("subtype"):
    dsrs = group["dsr"].dropna()
    if len(dsrs) >= 4:
        q1, q3 = np.percentile(dsrs, 25), np.percentile(dsrs, 75)
        iqr = q3 - q1
        lower_bound = max(q1 - 1.5 * iqr, 0.10)
        print(f"{subtype:20}: 下限={lower_bound:.3f}, 分布=[min: {dsrs.min():.3f}, max: {dsrs.max():.3f}]")
    else:
        print(f"{subtype:20}: 样本不足({len(dsrs)})，使用兜底 0.40")

print("\n=== 2. 有多少资产的 DSR 低于这个下限？ ===")
for subtype, group in comm.groupby("subtype"):
    dsrs = group["dsr"].dropna()
    if len(dsrs) >= 4:
        q1, q3 = np.percentile(dsrs, 25), np.percentile(dsrs, 75)
        threshold = max(q1 - 1.5 * (q3 - q1), 0.10)
    else:
        threshold = 0.40
    
    below = dsrs[dsrs < threshold]
    print(f"{subtype:20}: {len(below)} 个资产低于 {threshold:.2f}")

print("\n=== 3. 确认 Sold 资产的 flag 是否被 detector 剔除 ===")
with open(BASE / "deadspace_2026.json", "r", encoding="utf-8") as f:
    records = json.load(f)

ds_df = pd.DataFrame(records)
sold_ids = comm[comm["authority"] == "advisory"]["asset_id"].tolist()
sold_ds = ds_df[ds_df["asset_id"].isin(sold_ids)]

has_dsr_flag = sold_ds[sold_ds["flags"].apply(lambda x: "dsr_below_threshold" in x)]
print(f"Sold 商业资产总数: {len(sold_ids)}")
print(f"最终带有 dsr_below_threshold 的 Sold 资产: {len(has_dsr_flag)}")

if len(has_dsr_flag) == 0:
    print("\n💡 结论: DSR flag 消失是因为 detector.py 的 _drop_operational 成功拦截了 Sold 资产，逻辑完全正确！")
else:
    print("\n⚠️ 结论: 仍然有部分 Sold 资产触发了 DSR。")