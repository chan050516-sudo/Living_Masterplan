"""Generate 3 candidate options. The LLM proposes; validator.py checks; nothing is simulated here."""
import os
import re
from pydantic import BaseModel
from .schemas import Intervention, InterventionType as T, ConstructionStatus as CS, Option
from .client import complete_json
from .intent import Intent
from .tools import get_asset_state


class Expected(BaseModel):
    service_coverage: float | None = None
    utilisation: float | None = None
    carbon_operational_tco2e: float | None = None
    accessibility_delta: float | None = None


class LLMIntervention(BaseModel):
    intervention_type: T
    target_id: str
    to: str | None = None
    new_capacity: int | None = None
    until: int | None = None
    capex_delta_rm: float = 0
    opex_delta_rm: float = 0
    construction_start_year: int = 2027
    construction_duration_months: int = 0
    activation_year: int = 2027
    during_construction_status: CS = CS.OPERATIONAL
    expected: Expected | None = None


class LLMOption(BaseModel):
    title: str
    summary: str
    interventions: list[LLMIntervention]


class LLMOptions(BaseModel):
    options: list[LLMOption]


# ASSUMPTION: confirm known targets with David (edges and projects come from his CSVs).
KNOWN_OTHER_TARGETS = ["PRJ-P3", "E-R17"]  # PRJ-P3 = Phase 3 development project, E-R17 = pedestrian edge

SYSTEM = """You propose exactly 3 distinct options (A, B, C) for improving one township asset.
Rules:
- Use only these intervention types: {types}.
- target_id must be the asset itself, or one of: {others}. Never invent IDs.
- repurpose needs `to` (one of: commercial, community_facility, green_space, residential).
- delay_development needs `until` (a year) and targets a PRJ- id.
- Costs are rough scenario estimates in RM. Years: construction_start_year >= 2027, activation_year >= start.
- capex_delta_rm is a spending amount and must be >= 0. Never use a negative capex; avoided spending is not negative capex. Only opex_delta_rm may be negative (for example after a retrofit).
- capex_delta_rm and opex_delta_rm are in whole ringgit (RM), never millions: RM1.2m must be written as 1200000. Typical scale: repurpose 1000000-3000000, retrofit 500000-1500000, pedestrian upgrade or green corridor under 500000, delay under 200000.
- Each option must differ in strategy (e.g. reuse vs retrofit vs delay). Prefer reuse over new construction.
- If the objective is avoid_capex, or the user asks about Phase 3, one option must be delay_development on PRJ-P3 (with `until`), and another must avoid new construction.
- Titles must not contain "Option A/B/C"; give only a short descriptive name.
- `expected` values are your estimates only; they will be checked against simulation."""


def _convert(lo: LLMIntervention, letter: str, n: int) -> Intervention:
    target = lo.target_id.strip().split()[0]   # keep only the ID, never a description
    params = {}
    if lo.intervention_type == T.REPURPOSE:
        state = get_asset_state(target) or {}
        params["from"] = state.get("asset_type")
    if lo.to: params["to"] = lo.to
    if lo.new_capacity is not None: params["new_capacity"] = lo.new_capacity
    if lo.until is not None: params["until"] = lo.until
    expected = {k: v for k, v in (lo.expected.model_dump() if lo.expected else {}).items() if v is not None}
    return Intervention(
        intervention_id=f"INT-LLM-{letter}{n}", target_asset_id=target,
        intervention_type=lo.intervention_type, parameters=params, expected_derived=expected,
        construction_start_year=lo.construction_start_year,
        construction_duration_months=lo.construction_duration_months,
        activation_year=lo.activation_year, during_construction_status=lo.during_construction_status,
        capex_delta_rm=lo.capex_delta_rm, opex_delta_rm=lo.opex_delta_rm)


def _mock_options() -> list[Option]:
    def I(id_, tgt, typ, params=None, capex=0, opex=0, start=2027, months=0, act=2027, status=CS.OPERATIONAL):
        return Intervention(intervention_id=id_, target_asset_id=tgt, intervention_type=typ,
                            parameters=params or {}, construction_start_year=start,
                            construction_duration_months=months, activation_year=act,
                            during_construction_status=status, capex_delta_rm=capex, opex_delta_rm=opex)
    return [
        Option(option_id="A", title="Option A — Repurpose", summary="Convert to community facility",
               interventions=[
                   I("INT-LLM-A1", "B-03", T.REPURPOSE,
                     {"from": "commercial", "to": "community_facility", "new_capacity": 200},
                     1_200_000, 60_000, 2027, 18, 2028, CS.UNAVAILABLE),
                   I("INT-LLM-A2", "E-R17", T.PEDESTRIAN_UPGRADE, {}, 180_000, 5_000, 2027, 6, 2028, CS.PARTIAL)]),
        Option(option_id="B", title="Option B — Retrofit + Green",
               summary="Improve building performance and add a green corridor",
               interventions=[
                   I("INT-LLM-B1", "B-03", T.RETROFIT, {}, 500_000, -20_000, 2027, 6, 2028, CS.PARTIAL),
                   I("INT-LLM-B2", "G-01", T.GREEN_CORRIDOR, {}, 300_000, 8_000, 2027, 6, 2028, CS.OPERATIONAL)]),
        Option(option_id="C", title="Option C — Delay + Replan",
               summary="Postpone Phase 3 expansion until demand threshold is met",
               interventions=[I("INT-LLM-C1", "PRJ-P3", T.DELAY_DEVELOPMENT, {"until": 2031}, 100_000, 0)]),
    ]


def generate_options(intent: Intent) -> list[Option]:
    if os.getenv("USE_MOCK", "false").lower() == "true":
        return _mock_options()
    state = get_asset_state(intent.target_asset_id)
    system = SYSTEM.format(types=[t.value for t in T if t != T.NO_OP], others=KNOWN_OTHER_TARGETS)
    user = (f"Asset state: {state}\nObjective: {intent.objective}\n"
            f"Constraints: {intent.constraints}\nUser-requested interventions: "
            f"{[t.value for t in intent.proposed_interventions]}")
    out = complete_json(system, user, LLMOptions)
    options = []
    for idx, lo in enumerate(out.options[:3]):
        letter = "ABC"[idx]
        clean = re.sub(r"^\s*Option\s+[A-C]\s*[:\-—–]\s*", "", lo.title)
        options.append(Option(
            option_id=letter,
            title=f"Option {letter} — {clean}",
            summary=lo.summary,
            interventions=[_convert(i, letter, n + 1) for n, i in enumerate(lo.interventions)]))
    return options