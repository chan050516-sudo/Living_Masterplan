# backend/scripts/analyze_subtype_distribution.py
"""Quick inventory of subtypes across the current asset base."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE = REPO_ROOT / "bukit_jelutong" / "processed" / "business"

assets = pd.read_csv(BASE / "assets.csv")
metrics = pd.read_csv(BASE / "asset_metrics_enriched.csv")

# 只看 2026 年
m = metrics[metrics["year"] == 2026].copy()

# 合并资产基础信息
df = assets.merge(
    m[["asset_id", "occupancy_rate", "utilisation_rate",
       "occupancy_by_subtype_calc_json", "occupancy_by_subtype_target_json"]],
    on="asset_id", how="left",
)

# ---- 1. 按 asset_type 分布 ----
print("\n" + "=" * 72)
print("  ASSET TYPE DISTRIBUTION")
print("=" * 72)
summary = df.groupby("asset_type").agg(
    count=("asset_id", "count"),
    total_lettable_m2=("lettable_area_m2", "sum"),
    total_floor_m2=("floor_area_m2", "sum"),
    avg_occupancy=("occupancy_rate", "mean"),
).round(3)
print(summary.to_string())

# ---- 2. 按 subtype 分布（全部 asset_type）----
print("\n" + "=" * 72)
print("  SUBTYPE DISTRIBUTION (all asset types)")
print("=" * 72)
by_sub = df.groupby(["asset_type", "subtype"]).agg(
    count=("asset_id", "count"),
    total_lettable_m2=("lettable_area_m2", "sum"),
    avg_occupancy=("occupancy_rate", "mean"),
).reset_index()
by_sub = by_sub.sort_values(
    ["asset_type", "count"], ascending=[True, False],
)
for atype, grp in by_sub.groupby("asset_type"):
    print(f"\n[{atype}]  ({grp['count'].sum()} assets)")
    print(f"  {'subtype':<24} {'count':>5}  {'lettable m2':>12}  {'avg occ':>8}")
    print("  " + "-" * 56)
    for _, r in grp.iterrows():
        occ = f"{r['avg_occupancy']:.2f}" if pd.notna(r["avg_occupancy"]) else "-"
        let = f"{r['total_lettable_m2']:.0f}" if pd.notna(r["total_lettable_m2"]) else "-"
        print(f"  {r['subtype']:<24} {int(r['count']):>5}  {let:>12}  {occ:>8}")

# ---- 3. Mixed-use 商业资产的 subtype 明细 ----
print("\n" + "=" * 72)
print("  MIXED-USE COMMERCIAL ASSETS (with unit_mix_json)")
print("=" * 72)
comm = df[(df["asset_type"] == "commercial")
          & df["unit_mix_json"].notna()
          & (df["unit_mix_json"] != "")]

print(f"\n  {len(comm)} mixed-use commercial assets\n")

# 聚合每个 subtype 在这些 mall 里的总面积、总单元数、平均实际入驻率
subtype_in_mall = {}   # {st: {"area": 0, "count": 0, "occ_list": [], "target_list": [], "mall_ids": []}}
total_mall_lettable = 0.0

for _, r in comm.iterrows():
    try:
        mix = json.loads(r["unit_mix_json"])
    except (json.JSONDecodeError, TypeError):
        continue
    if not isinstance(mix, dict):
        continue

    total_mall_lettable += float(r["lettable_area_m2"] or 0)

    # 解析 calc 和 target
    calc = {}
    try:
        calc = json.loads(r["occupancy_by_subtype_calc_json"] or "{}")
    except (json.JSONDecodeError, TypeError):
        pass
    target = {}
    try:
        target = json.loads(r["occupancy_by_subtype_target_json"] or "{}")
    except (json.JSONDecodeError, TypeError):
        pass

    for st, info in mix.items():
        area = float(info.get("area_m2") or 0)
        count = int(info.get("count") or 0)
        if area <= 0:
            continue
        entry = subtype_in_mall.setdefault(st, {
            "area": 0.0, "count": 0,
            "occ_list": [], "target_list": [],
            "mall_ids": [],
        })
        entry["area"] += area
        entry["count"] += count
        if st in calc:
            entry["occ_list"].append(float(calc[st]))
        if st in target:
            entry["target_list"].append(float(target[st]))
        entry["mall_ids"].append(r["asset_id"])

print(f"  Total mall lettable: {total_mall_lettable:.0f} m²")
print(f"  {'subtype':<24} {'malls':>5}  {'total m2':>10}  {'share':>6}  {'units':>6}  {'avg occ':>8}  {'avg tgt':>8}")
print("  " + "-" * 82)
for st, e in sorted(subtype_in_mall.items(), key=lambda kv: -kv[1]["area"]):
    share = e["area"] / total_mall_lettable if total_mall_lettable > 0 else 0
    occ_avg = sum(e["occ_list"]) / len(e["occ_list"]) if e["occ_list"] else None
    tgt_avg = sum(e["target_list"]) / len(e["target_list"]) if e["target_list"] else None
    occ_s = f"{occ_avg:.3f}" if occ_avg is not None else "-"
    tgt_s = f"{tgt_avg:.3f}" if tgt_avg is not None else "-"
    print(f"  {st:<24} {len(e['mall_ids']):>5}  "
          f"{e['area']:>10.0f}  {share*100:>5.1f}%  "
          f"{e['count']:>6}  {occ_s:>8}  {tgt_s:>8}")

# ---- 4. 健康的 vs 可能死亡的具体 mall ----
print("\n" + "=" * 72)
print("  MALLS WITH AT LEAST ONE SUBTYPE BELOW 30% ACTUAL OCCUPANCY")
print("=" * 72)
found_any = False
for _, r in comm.iterrows():
    try:
        calc = json.loads(r["occupancy_by_subtype_calc_json"] or "{}")
    except (json.JSONDecodeError, TypeError):
        continue
    low = {st: v for st, v in calc.items() if v < 0.30}
    if not low:
        continue
    found_any = True
    print(f"\n  {r['asset_id']}  (lettable {r['lettable_area_m2']:.0f} m², aggregate occ {r['occupancy_rate']:.2f})")
    mix = json.loads(r["unit_mix_json"])
    for st, occ in sorted(low.items(), key=lambda kv: kv[1]):
        area = mix.get(st, {}).get("area_m2", 0)
        print(f"    {st:<22}  occ={occ:.3f}  area={area:.0f} m²")

if not found_any:
    print("\n  (none — all mixed-use malls have every subtype >= 30% actual)")

# ---- 5. 单 subtype 商业资产 ----
print("\n" + "=" * 72)
print("  SINGLE-SUBTYPE COMMERCIAL ASSETS")
print("=" * 72)
single = df[(df["asset_type"] == "commercial")
            & (df["unit_mix_json"].isna() | (df["unit_mix_json"] == ""))]
print(f"\n  {len(single)} single-subtype commercial assets")
if not single.empty:
    sg = single.groupby("subtype").agg(
        count=("asset_id", "count"),
        avg_occ=("occupancy_rate", "mean"),
        avg_lettable=("lettable_area_m2", "mean"),
    ).round(3).sort_values("count", ascending=False)
    print(f"\n  {'subtype':<24} {'count':>5}  {'avg occ':>8}  {'avg lettable':>12}")
    print("  " + "-" * 56)
    for st, r in sg.iterrows():
        print(f"  {st:<24} {int(r['count']):>5}  {r['avg_occ']:>8.2f}  {r['avg_lettable']:>12.0f}")

print("\n" + "=" * 72)