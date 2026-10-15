import pandas as pd
df = pd.read_csv("bukit_jelutong/processed/business/asset_metrics_enriched.csv")

# 1. Green per capita
g = df[df["asset_id"].str.startswith("G-")]
print("G green_per_capita:", g["green_per_capita_m2"].notna().sum(), "/", len(g))

# 2. UHI 分布应该离散化改善
print("UHI unique values:", df["surface_temp_delta_c"].nunique())
print("UHI max:", df["surface_temp_delta_c"].max())
print("UHI min:", df["surface_temp_delta_c"].min())
print("UHI == 8.0 count:", (df["surface_temp_delta_c"] == 8.0).sum())

# 3. Commercial DSR
comm = df[df["subtype"].isin(["f_and_b", "supermarket", "services", "convenience_retail"])]
print("Commercial dsr:", comm["dsr"].notna().sum(), "/", len(comm))

# 4. Green reachable population
print("G reachable_population > 0:", (g["reachable_population_walk"] > 0).sum())