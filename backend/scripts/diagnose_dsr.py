import pandas as pd
df = pd.read_csv("bukit_jelutong/processed/business/asset_metrics_enriched.csv")

comm = df[df["subtype"].isin(["f_and_b", "supermarket", "services"])]
print("Commercial DSR:", comm["dsr"].notna().sum(), "/", len(comm))

g = df[df["asset_id"].str.startswith("G-")]
print("G reachable_population > 0:", (g["reachable_population_walk"] > 0).sum(), "/", len(g))

print("UHI unique values:", df["surface_temp_delta_c"].nunique())