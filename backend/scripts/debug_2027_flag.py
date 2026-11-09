import json
import pandas as pd
from pathlib import Path

# Fixed path: scripts -> backend -> repo_root
REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = REPO_ROOT / "bukit_jelutong" / "processed" / "business"
SCEN_DIR = BASE_DIR / "scenarios"

def load_ds(filename):
    path = BASE_DIR / filename if "2026" in filename else SCEN_DIR / filename
    if not path.exists():
        print(f"❌ 找不到文件: {path}")
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def print_compare(row26, row27):
    cols_to_check = [
        "occupancy_rate", "utilisation_rate", "noi_rm", 
        "surface_temp_delta_c", "canopy_coverage", 
        "carbon_stranded_tco2e", "stranded_carbon_ratio",
        "trajectory_class", "peak_occupancy", "years_since_peak"
    ]
    print(f"\n{'指标 (Metric)':<30} | {'2026 (Base)':<15} | {'2027 (Sim)':<15}")
    print("-" * 65)
    for c in cols_to_check:
        v26 = row26.get(c) if isinstance(row26, dict) else getattr(row26, c, None)
        v27 = row27.get(c) if isinstance(row27, dict) else getattr(row27, c, None)
        if isinstance(v26, float): v26 = round(v26, 3)
        if isinstance(v27, float): v27 = round(v27, 3)
        print(f"{c:<30} | {str(v26):<15} | {str(v27):<15}")


# 1. 加载 2026 和 2027 的诊断结果
ds26 = load_ds("deadspace_2026.json")
ds27 = load_ds("deadspace_SC-CURRENT_2027.json")

if not ds27:
    print("⚠️ 未找到 2027 的文件，请确认你跑过 run_phase4.py 或者前端触发了模拟。")
    exit()

# 2. 统计 Flag 分布
flags_26 = {}
flags_27 = {}
for r in ds26:
    for f in r.get("flags", []): flags_26[f] = flags_26.get(f, 0) + 1
for r in ds27:
    for f in r.get("flags", []): flags_27[f] = flags_27.get(f, 0) + 1

print("=== 🚨 Flag 爆发排行榜 (2026 vs 2027) ===")
all_flags = set(flags_26.keys()) | set(flags_27.keys())
for f in sorted(all_flags):
    c26 = flags_26.get(f, 0)
    c27 = flags_27.get(f, 0)
    diff = c27 - c26
    if diff > 0:
        print(f"  {f:<35}: 2026({c26:>3}) -> 2027({c27:>3})  [🚨 增加 {diff}]")
    else:
        print(f"  {f:<35}: 2026({c26:>3}) -> 2027({c27:>3})")

# 3. 抽样对比：找一个 2026 healthy，2027 monitor 的资产
target_asset = None
for r26 in ds26:
    if r26["status"] == "healthy":
        aid = r26["asset_id"]
        for r27 in ds27:
            if r27["asset_id"] == aid and r27["status"] == "monitor":
                target_asset = aid
                break
    if target_asset: break

if not target_asset:
    print("\n⚠️ 找不到 2026 healthy -> 2027 monitor 的样本。")
    exit()

print(f"\n=== 🔍 抽样对比资产: {target_asset} ===")
r26 = next(r for r in ds26 if r["asset_id"] == target_asset)
r27 = next(r for r in ds27 if r["asset_id"] == target_asset)

print(f"2026 Status: {r26['status']}, 2027 Status: {r27['status']}")
print(f"2026 Flags: {r26.get('flags')}")
print(f"2027 Flags: {r27.get('flags')}")

# 4. 读取底层的 metrics
metrics_path = BASE_DIR / "asset_metrics_enriched.csv"
df = pd.read_csv(metrics_path)
m26 = df[(df["asset_id"] == target_asset) & (df["year"] == 2026)]
m27 = df[(df["asset_id"] == target_asset) & (df["year"] == 2027)]

if m26.empty or m27.empty:
    # B4 实时模拟的指标不一定会写回 enriched 表，尝试去 scenarios/SC-CURRENT.json 里找
    sc_path = SCEN_DIR / "SC-CURRENT.json"
    if sc_path.exists():
        with open(sc_path, "r", encoding="utf-8") as f:
            sc_data = json.load(f)
        assets_27 = sc_data.get("years", {}).get("2027", {}).get("assets", {})
        if target_asset in assets_27:
            row26 = m26.iloc[0] if not m26.empty else {}
            row27 = assets_27[target_asset]
            print_compare(row26, row27)
            exit()
    print("❌ 无法找到该资产的 2027 指标数据")
else:
    print_compare(m26.iloc[0], m27.iloc[0])
