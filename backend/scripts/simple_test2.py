import pandas as pd, json
df = pd.read_csv("bukit_jelutong/processed/business/asset_metrics_enriched.csv")
df_2026 = df[df.year == 2026]
with_target = df_2026[df_2026.occupancy_by_subtype_target_json.notna()]
print(f"Assets with target: {len(with_target)}")
if not with_target.empty:
    r = with_target.iloc[0]
    print(f"\nAsset: {r.asset_id}")
    print(f"calc:   {r.occupancy_by_subtype_calc_json}")
    print(f"target: {r.occupancy_by_subtype_target_json}")