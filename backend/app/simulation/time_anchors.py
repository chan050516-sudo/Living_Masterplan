"""Intervention time anchor logic.

Each intervention has three anchors:
    construction_start_year
    construction_duration_months
    activation_year
    during_construction_status  ("unavailable" / "partial" / "operational")

For any asset-year, resolve which phase it is in.
"""

from enum import Enum


class Phase(str, Enum):
    PRE = "pre"           # Before construction
    DURING = "during"     # Construction in progress
    POST = "post"         # Activated


def resolve_phase(year: int, intervention: dict) -> Phase:
    start = int(intervention["construction_start_year"])
    activation = int(intervention["activation_year"])

    if year < start:
        return Phase.PRE
    if start <= year < activation:
        return Phase.DURING
    return Phase.POST


def interventions_for_asset(asset_id: str, interventions_df) -> list:
    """Return list of interventions targeting this asset as dicts."""
    if interventions_df is None or interventions_df.empty:
        return []
    subset = interventions_df[interventions_df["target_asset_id"] == asset_id]
    return subset.to_dict("records")