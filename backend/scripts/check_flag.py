# 保存为 check_flags.py 然后运行
import json
import pandas as pd

with open('bukit_jelutong/processed/business/deadspace_2026.json', 'r', encoding='utf-8') as f:
    records = json.load(f)

assets = pd.read_csv('bukit_jelutong/processed/business/assets.csv')
df = pd.DataFrame(records)
merged = df.merge(assets[['asset_id', 'asset_type', 'authority']], on='asset_id', how='left')

print("\n=== 1. 全局 Status 分布 ===")
print(merged['status'].value_counts())

print("\n=== 2. Sold / Advisory 资产的状态 (印证死空间) ===")
sold_df = merged[merged['authority'].isin(['advisory', 'shared'])]
print(sold_df['status'].value_counts())
if 'deadspace_candidate' in sold_df['status'].values:
    print("\n✅ 成功！Sold 商铺被识别为 Deadspace 的案例：")
    print(sold_df[sold_df['status'] == 'deadspace_candidate'][['asset_id', 'asset_type', 'status', 'urgency_index']].head())

print("\n=== 3. 各资产类型的状态分布 ===")
print(pd.crosstab(merged['asset_type'], merged['status']))

print("\n=== 4. 触发最高频的 Top 10 Flags ===")
all_flags = []
for flags in merged['flags']:
    all_flags.extend(flags)
flag_counts = pd.Series(all_flags).value_counts()
print(flag_counts.head(10))