"""parse intent -> generate options -> validate -> simulate -> compare -> explain.
Output shape matches Mathaba's options.json / comparison.json."""
import json
import os
from pydantic import BaseModel
from .schemas import Option, InterventionType as T
from .intent import parse_intent
from .options import generate_options
from .validator import validate_option
from .tools import get_asset_metrics, simulate_option
from .client import complete_json

SCORE_BONUS = {T.REPURPOSE: 35, T.PEDESTRIAN_UPGRADE: 8, T.RETROFIT: 25, T.GREEN_CORRIDOR: 13,
               T.DELAY_DEVELOPMENT: 3, T.NEW_DEVELOPMENT: 5, T.NO_OP: 0}


def _mock() -> bool:
    return os.getenv("USE_MOCK", "false").lower() == "true"


def _current_score(asset_id: str) -> int:
    try:
        rows = get_asset_metrics(asset_id, 2026)
        return int(round(rows[0]["performance_score"]))
    except Exception:
        return 28  # placeholder until David's metrics column is confirmed


def _simulate(option: Option, current: int) -> dict:
    if os.getenv("USE_MOCK_SIM", "true").lower() == "true":
        after = min(100, current + sum(SCORE_BONUS[i.intervention_type] for i in option.interventions))
        return {"source": "mock", "score_after": after,
                "capex_rm": sum(i.capex_delta_rm for i in option.interventions),
                "months": max(i.construction_duration_months for i in option.interventions)}
    result = simulate_option(option)
    # TODO: map David's ScenarioResult to these keys once we have seen its shape.
    raise NotImplementedError(f"Summarise real result keys: {list(result.keys())}")


def _changes(option: Option) -> list[str]:
    out = []
    for i in option.interventions:
        p, t = i.parameters, i.target_asset_id
        out.append({
            T.REPURPOSE: f"{t}: {p.get('from')} → {p.get('to')}",
            T.PEDESTRIAN_UPGRADE: f"Pedestrian route {t}: upgraded",
            T.DELAY_DEVELOPMENT: f"{t}: delayed to {p.get('until')}",
            T.RETROFIT: f"{t}: retrofitted",
            T.GREEN_CORRIDOR: f"{t}: green corridor added",
            T.NEW_DEVELOPMENT: f"{t}: new development",
        }.get(i.intervention_type, f"{t}: no change"))
    return out


class Explanation(BaseModel):
    analysis: str
    recommended_option_id: str
    reason: str


def _explain(asset_id: str, facts: list[dict]) -> Explanation:
    best = max(facts, key=lambda f: f["score_after"])
    if _mock():
        return Explanation(
            analysis=f"{asset_id} is underperforming. {len(facts)} candidate strategies were generated and simulated.",
            recommended_option_id=best["id"],
            reason=f"Option {best['id']} gives the highest projected score ({best['score_after']}).")
    system = ("Explain the trade-offs between options. Use ONLY numbers present in FACTS. "
              "Never invent numbers. Pick the recommended option from FACTS.")
    return complete_json(system, f"Asset: {asset_id}\nFACTS: {json.dumps(facts)}", Explanation)


def run_query(text: str, selected_asset_id: str | None = None, year: int = 2026) -> dict:
    intent = parse_intent(text, selected_asset_id, year)
    if intent.needs_clarification or not intent.target_asset_id:
        return {"needs_clarification": True, "question": intent.clarification_question}
    asset = intent.target_asset_id
    current = _current_score(asset)

    options = []
    for opt in generate_options(intent):
        errors = validate_option(opt)
        if not errors:
            options.append(opt)
    if not options:
        return {"needs_clarification": True, "question": "No valid option could be generated."}

    facts, cards = [], []
    for opt in options:
        sim = _simulate(opt, current)
        facts.append({"id": opt.option_id, "capex_rm": sim["capex_rm"], "score_after": sim["score_after"],
                      "delta": sim["score_after"] - current, "months": sim["months"], "source": sim["source"]})
        cards.append({"id": opt.option_id, "title": opt.title, "summary": opt.summary,
                      "capex": f"RM{sim['capex_rm'] / 1e6:.1f}m", "score_after": sim["score_after"],
                      "changes": _changes(opt)})
    exp = _explain(asset, facts)
    col = {f["id"].lower(): f for f in facts}

    def row(label, fn, cur="—"):
        r = {"label": label, "current": cur}
        for k, f in col.items():
            r[k] = fn(f)
        return r

    best_title = next(c["title"] for c in cards if c["id"] == exp.recommended_option_id)
    return {
        "asset": asset,
        "intent": intent.model_dump(mode="json"),
        "options": {asset: {"analysis": exp.analysis, "options": cards}},
        "comparison": {asset: {
            "rows": [row("CAPEX", lambda f: f"RM{f['capex_rm'] / 1e6:.1f}m"),
                     row("Performance score", lambda f: str(f["score_after"]), str(current)),
                     row("Change in score", lambda f: f"{f['delta']:+d}"),
                     row("Time to impact", lambda f: f"{f['months']}mo")],
            "recommended": best_title, "reason": exp.reason}},
        "data_source": facts[0]["source"],
    }