"""C2: turn a user's sentence into a structured Intent. No numbers, no simulation."""
import os
from typing import Literal
from pydantic import BaseModel
from .schemas import InterventionType
from .client import complete_json
from .tools import list_assets

Objective = Literal["reduce_vacancy", "reduce_carbon", "improve_access",
                    "avoid_capex", "improve_score", "unspecified"]


class Intent(BaseModel):
    target_asset_id: str | None
    objective: Objective
    constraints: list[str]
    proposed_interventions: list[InterventionType]
    needs_clarification: bool
    clarification_question: str | None


SYSTEM = """You parse requests about a township asset into a structured Intent.
Rules:
- target_asset_id must be one of the KNOWN ASSETS. If the user says "this", use the selected asset.
  If you cannot determine it, set needs_clarification=true and ask one short question.
- proposed_interventions may only contain the allowed intervention types, and only if the user asked for them.
  Do not add interventions the user did not mention.
- "Phase 3" refers to development project PRJ-P3; "should we proceed with Phase 3" means objective=avoid_capex
  with no proposed interventions.
- Never invent numbers or asset IDs. If the request is outside the allowed types
  (e.g. build a stadium), set needs_clarification=true.
KNOWN ASSETS: {assets}
ALLOWED INTERVENTIONS: {types}"""


def _mock_parse(text: str, selected: str | None) -> Intent:
    t = text.lower()
    found = [w for w, k in [(InterventionType.REPURPOSE, "repurpose"),
                            (InterventionType.RETROFIT, "retrofit"),
                            (InterventionType.GREEN_CORRIDOR, "green"),
                            (InterventionType.PEDESTRIAN_UPGRADE, "pedestrian"),
                            (InterventionType.DELAY_DEVELOPMENT, "delay")] if k in t]
    asset = next((a for a in ["B-03", "F-02", "P-05", "G-01", "R-01"] if a.lower() in t), selected)
    objective = "avoid_capex" if "phase 3" in t else "improve_score"
    return Intent(target_asset_id=asset, objective=objective, constraints=[],
                  proposed_interventions=found, needs_clarification=asset is None,
                  clarification_question="Which asset do you mean?" if asset is None else None)


def parse_intent(user_text: str, selected_asset_id: str | None = None, year: int = 2026) -> Intent:
    if os.getenv("USE_MOCK", "false").lower() == "true":
        intent = _mock_parse(user_text, selected_asset_id)
    else:
        known = [a["asset_id"] for a in list_assets()]
        system = SYSTEM.format(assets=known, types=[t.value for t in InterventionType])
        user = f"Selected asset: {selected_asset_id}\nYear: {year}\nRequest: {user_text}"
        intent = complete_json(system, user, Intent)

    # Code-level guard: never trust the model's asset ID.
    known_ids = {a["asset_id"] for a in list_assets()}
    if intent.target_asset_id and intent.target_asset_id not in known_ids:
        intent.needs_clarification = True
        intent.clarification_question = f"I don't know an asset called {intent.target_asset_id}."
        intent.target_asset_id = None
    return intent