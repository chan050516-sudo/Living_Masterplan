import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import pearsonr

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE = REPO_ROOT / "bukit_jelutong" / "processed" / "business"

def main():
    # 1. 加载数据
    wri = pd.read_csv(BASE / "wri_canopy_observations.csv")
    thermal = pd.read_csv(BASE / "thermal_observations.csv")
    assets = pd.read_csv(BASE / "assets.csv")[["asset_id", "asset_type"]]

    print("=" * 70)
    print(" 1. WRI 全量数据概况 (Tree Canopy Observations)")
    print("=" * 70)
    print(f"总资产数: {len(wri)}")
    print(f"Tree Cover Fraction 统计:")
    print(wri["wri_treecover_fraction"].describe().round(3))
    
    zeros = (wri["wri_treecover_fraction"] == 0).sum()
    print(f"\n树冠覆盖率为 0 的资产数: {zeros} ({zeros/len(wri)*100:.1f}%)")
    print(f"树冠覆盖率 > 30% 的资产数: {(wri['wri_treecover_fraction'] > 0.3).sum()}")

    # 与资产类型合并，看各类型的树冠分布
    wri_typed = wri.merge(assets, on="asset_id", how="left")
    print("\n按资产类型统计的树冠覆盖率均值:")
    print(wri_typed.groupby("asset_type")["wri_treecover_fraction"].mean().round(3))

    # 2. 合并温度数据计算 Pearson
    print("\n" + "=" * 70)
    print(" 2. Pearson 相关性分析 (WRI Canopy vs Landsat LST)")
    print("=" * 70)
    
    # 只保留有 Landsat 真实温度且 WRI 有数据的样本
    thermal_valid = thermal[thermal["t_asset_c"].notna()]
    merged = (
        wri
        .merge(thermal_valid, on="asset_id", how="inner")
        .merge(assets, on="asset_id", how="left")
        .dropna(subset=["wri_treecover_fraction", "surface_temp_delta_c"])
    )

    print(f"有效配对样本量 (Paired samples): {len(merged)}")

    # 计算全样本相关性
    r_all, p_all = pearsonr(merged["wri_treecover_fraction"], merged["surface_temp_delta_c"])
    print(f"\n全样本 (n={len(merged)}):")
    print(f"  Pearson r = {r_all:+.4f}  (p-value = {p_all:.4e})")

    # 计算排除绿地后的相关性 (更重要，避免类别效应)
    non_green = merged[merged["asset_type"] != "green_space"]
    if len(non_green) > 30:
        r_ng, p_ng = pearsonr(non_green["wri_treecover_fraction"], non_green["surface_temp_delta_c"])
        print(f"\n排除绿地的硬核测试 (n={len(non_green)}):")
        print(f"  Pearson r = {r_ng:+.4f}  (p-value = {p_ng:.4e})")
        
        # 3. 线性回归获取最终耦合系数
        print("\n" + "=" * 70)
        print(" 3. 最终用于 B4 仿真的线性回归系数 (排除绿地)")
        print("=" * 70)
        x = non_green["wri_treecover_fraction"].values
        y = non_green["surface_temp_delta_c"].values
        slope, intercept = np.polyfit(x, y, 1)
        
        print(f"  Equation: ΔT = {intercept:+.3f} + ({slope:+.3f} × Canopy_Fraction)")
        print(f"  → 树冠覆盖率每增加 10%，温度变化: {slope * 0.1:+.3f} °C")
        print(f"  → 树冠覆盖率每增加 20%，温度变化: {slope * 0.2:+.3f} °C")
        print("\n  (请将上述 slope 和 intercept 填入 assumptions.yml)")
        
    else:
        print("\n样本量不足以进行非绿地回归分析。")

if __name__ == "__main__":
    main()