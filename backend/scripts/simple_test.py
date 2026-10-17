import pandas as pd
df = pd.read_csv("bukit_jelutong/processed/business/assets.csv")
print(df["authority"].value_counts())