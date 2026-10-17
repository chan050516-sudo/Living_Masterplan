import pandas as pd
df = pd.read_csv("bukit_jelutong/processed/business/assets.csv")
print(df[df.asset_id.isin(["BLD-0183", "BLD-0151"])][[
    "asset_id", "asset_type", "subtype",
    "ownership_status", "authority",
    "unit_count", "developer_held_units",
]].to_string())

import json
with open("bukit_jelutong/processed/business/interventions.csv") as f:
    import pandas as pd
    df = pd.read_csv(f)
sub = df[df.scenario_id == "SC-LLM-40e3ab9a-C1"]
for _, r in sub.iterrows():
    print(r.target_asset_id, r.intervention_type)
    print("  params:", r.parameters_json)

import json
with open("bukit_jelutong/processed/business/scenarios/SC-LLM-40e3ab9a-C1.json") as f:
    r = json.load(f)
# 查 base year 的 BLD-0151 状态
base = r["years"]["2026"]["assets"]["BLD-0151"]
print("occupancy:", base.get("occupancy_rate"))
print("developer_held_units:", base.get("developer_held_units"))
print("subtype:", base.get("subtype"))