"""Plain-Python validation. No LLM involved. Rejects bad proposals before simulation."""
import pandas as pd
from pathlib import Path
from ..config import load_paths
from .schemas import Option, Intervention, InterventionType as T

ROOT = Path(__file__).resolve().parents[3]

# ASSUMPTION: confirm these with David.
ALLOWED_REPURPOSE_TO = {"commercial", "community_facility", "green_space", "residential"}

RULES = {
    T.REPURPOSE:          {"asset_types": {"commercial", "community_facility"}, "required": ["to"]},
    T.RETROFIT:           {"asset_types": {"commercial", "community_facility", "residential"}, "required": []},
    T.GREEN_CORRIDOR:     {"asset_types": {"green_space", "undeveloped_parcel"}, "required": []},
    T.NEW_DEVELOPMENT:    {"asset_types": {"undeveloped_parcel"}, "required": []},
    T.PEDESTRIAN_UPGRADE: {"prefix": "E-", "required": []},      # targets a network edge
    T.DELAY_DEVELOPMENT:  {"prefix": "PRJ-", "required": ["until"]},  # targets a project
    T.NO_OP:              {"required": []},
}


def _asset_types() -> dict:
    base = ROOT / load_paths()["base"]
    df = pd.read_csv(base / "business" / "assets.csv")
    return dict(zip(df["asset_id"], df["asset_type"]))


def validate_intervention(i: Intervention, max_capex_rm: float | None = None) -> list[str]:
    errors = []
    rule = RULES[i.intervention_type]
    for key in rule.get("required", []):
        if key not in i.parameters:
            errors.append(f"{i.intervention_type.value}: missing parameter '{key}'")
    if "prefix" in rule:
        if not i.target_asset_id.startswith(rule["prefix"]):
            errors.append(f"{i.intervention_type.value}: target must start with {rule['prefix']}")
    elif "asset_types" in rule:
        atype = _asset_types().get(i.target_asset_id)
        if atype is None:
            errors.append(f"unknown asset '{i.target_asset_id}'")
        elif atype not in rule["asset_types"]:
            errors.append(f"{i.intervention_type.value} is not allowed on {atype} ({i.target_asset_id})")
    if i.intervention_type == T.REPURPOSE and i.parameters.get("to") not in ALLOWED_REPURPOSE_TO:
        errors.append(f"repurpose: invalid 'to' value {i.parameters.get('to')!r}")
    if i.activation_year < i.construction_start_year:
        errors.append("activation_year is before construction_start_year")
    if i.capex_delta_rm < 0:
        errors.append(f"capex_delta_rm must be >= 0 (got {i.capex_delta_rm})")
    if max_capex_rm is not None and i.capex_delta_rm > max_capex_rm:
        errors.append(f"capex {i.capex_delta_rm} exceeds budget {max_capex_rm}")
    return errors


def validate_option(option: Option, max_capex_rm: float | None = None) -> list[str]:
    errors = []
    for i in option.interventions:
        errors += validate_intervention(i, max_capex_rm)
    return errors