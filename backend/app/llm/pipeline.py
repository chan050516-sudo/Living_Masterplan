"""parse intent -> generate options -> validate -> simulate -> compare -> explain.
Output shape matches Mathaba's options.json / comparison.json, plus a map_diff per option."""
import json
import math
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

NOT_ASSET_PREFIXES = ("PRJ-", "E-")  # projects and network edges have no asset performance score


def _mock() -> bool:
    return os.getenv("USE_MOCK", "false").lower() == "true"


def _use_mock_sim() -> bool:
    return os.getenv("USE_MOCK_SIM", "true").lower() == "true"


def _num(x):
    """NaN is not valid JSON, so turn it into None."""
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else x


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    return _num(o)


def _current_score(asset_id: str) -> int:
    try:
        rows = get_asset_metrics(asset_id, 2026)
        return int(round(rows[0]["performance_score"]))
    except Exception:
        return 28


def _scores_an_asset(option: Option) -> bool:
    return any(not i.target_asset_id.startswith(NOT_ASSET_PREFIXES) for i in option.interventions)


def _mock_sim(option: Option, current: int) -> dict:
    after = min(100, current + sum(SCORE_BONUS[i.intervention_type] for i in option.interventions))
    return {"source": "mock", "score_after": after, "current_score": None,
            "capex_rm": sum(i.capex_delta_rm for i in option.interventions),
            "months": max(i.construction_duration_months for i in option.interventions),
            "utilisation": None, "npv": None, "environmental": None, "social": None,
            "map_diff": None, "note": None}


def _real_sim(option: Option) -> dict:
    r = simulate_option(option)
    c = _clean(r["comparison"])
    base = {"source": "simulated",
            "capex_rm": c.get("capex") or 0,
            "months": int(c.get("time_to_impact_months") or 0),
            "map_diff": _clean(r.get("map_diff"))}
    if not _scores_an_asset(option):
        # The engine scores the first target; a project or edge has no asset score, so do not show its 0.
        return {**base, "score_after": None, "current_score": None, "utilisation": None,
                "npv": None, "environmental": None, "social": None,
                "note": "Changes project timing or a route, so no asset score is calculated."}
    perf, delta = c.get("performance_score"), c.get("delta_score")
    return {**base,
            "score_after": int(round(perf)),
            "current_score": int(round(perf - delta)) if delta is not None else None,
            "utilisation": c.get("projected_utilisation"),
            "npv": c.get("npv"),
            "environmental": c.get("environmental_score"),
            "social": c.get("social_score"),
            "note": None}


def _simulate(option: Option, current: int) -> dict:
    if _use_mock_sim():
        return _mock_sim(option, current)
    try:
        return _real_sim(option)
    except Exception as e:
        print(f"[pipeline] real simulation failed for option {option.option_id}: {e!r}; using mock numbers")
        return _mock_sim(option, current)


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


def _check_expected(option: Option, sim: dict) -> list[str]:
    """Compare the LLM's own estimate with the simulation (design doc 6.2)."""
    warnings = []
    actual = sim.get("utilisation")
    for i in option.interventions:
        exp = i.expected_derived.get("utilisation")
        if exp is not None and actual is not None and abs(exp - actual) > 0.2:
            warnings.append(f"LLM estimated utilisation {exp:.2f}, simulation gives {actual:.2f}")
    return warnings


class Explanation(BaseModel):
    analysis: str
    recommended_option_id: str
    reason: str


def _explain(asset_id: str, facts: list[dict]) -> Explanation:
    scored = [f for f in facts if f["score_after"] is not None] or facts
    best = max(scored, key=lambda f: f["score_after"] if f["score_after"] is not None else -1)
    if _mock():
        return Explanation(
            analysis=f"{asset_id} is underperforming. {len(facts)} candidate strategies were generated and simulated.",
            recommended_option_id=best["id"],
            reason=f"Option {best['id']} gives the highest projected score ({best['score_after']}).")
    system = ("Explain the trade-offs between options. Use ONLY numbers present in FACTS. "
              "A null value means the number is unavailable: do not mention it or compare it. "
              "A null score_after means the option changes project timing or a route and has no asset score. "
              "Never invent numbers. Pick the recommended option from FACTS.")
    return complete_json(system, f"Asset: {asset_id}\nFACTS: {json.dumps(facts)}", Explanation)


def _fmt_score(v) -> str:
    # David's engine returns exactly 0.0 for npv/environmental while unfinished: show "—", not a fake zero.
    return "—" if v is None or v == 0 else f"{v:.0f}"


def run_query(text: str, selected_asset_id: str | None = None, year: int = 2026) -> dict:
    intent = parse_intent(text, selected_asset_id, year)
    if intent.needs_clarification or not intent.target_asset_id:
        return {"needs_clarification": True, "question": intent.clarification_question}
    asset = intent.target_asset_id

    options = []
    for _ in range(2):  # one retry if the model proposes invalid options
        valid = []
        for o in generate_options(intent):
            errs = validate_option(o)
            if errs:
                print(f"[pipeline] dropped option {o.option_id}: {errs}")
            else:
                valid.append(o)
        if len(valid) > len(options):
            options = valid
        if len(options) == 3:
            break
    if not options:
        return {"needs_clarification": True, "question": "No valid option could be generated."}

    fallback_current = _current_score(asset)
    sims = [(o, _simulate(o, fallback_current)) for o in options]
    current = next((s["current_score"] for _, s in sims if s["current_score"] is not None), fallback_current)

    facts, cards = [], []
    for opt, sim in sims:
        after = sim["score_after"]
        facts.append({"id": opt.option_id, "capex_rm": sim["capex_rm"], "score_after": after,
                      "delta": None if after is None else after - current, "months": sim["months"],
                      "utilisation": sim["utilisation"], "social": sim["social"], "source": sim["source"]})
        cards.append({"id": opt.option_id, "title": opt.title, "summary": opt.summary,
                      "capex": f"RM{sim['capex_rm'] / 1e6:.1f}m", "score_after": after,
                      "changes": _changes(opt), "source": sim["source"], "map_diff": sim["map_diff"],
                      "note": sim["note"], "warnings": _check_expected(opt, sim)})
    exp = _explain(asset, facts)
    by_id = {opt.option_id.lower(): sim for opt, sim in sims}

    def row(label, fn, cur="—"):
        r = {"label": label, "current": cur}
        for k, sim in by_id.items():
            r[k] = fn(sim)
        return r

    rows = [row("CAPEX", lambda s: f"RM{s['capex_rm'] / 1e6:.1f}m")]
    if any(s["utilisation"] is not None for s in by_id.values()):
        rows.append(row("Projected utilisation",
                        lambda s: "—" if s["utilisation"] is None else f"{s['utilisation'] * 100:.0f}%"))
    for label, key in (("Environmental", "environmental"), ("Social", "social")):
        if any(s[key] not in (None, 0) for s in by_id.values()):
            rows.append(row(label, lambda s, k=key: _fmt_score(s[k])))
    rows += [row("Performance score", lambda s: "—" if s["score_after"] is None else str(s["score_after"]), str(current)),
             row("Change in score", lambda s: "—" if s["score_after"] is None else f"{s['score_after'] - current:+d}"),
             row("Time to impact", lambda s: f"{s['months']}mo")]

    sources = {s["source"] for s in by_id.values()}
    best_title = next(c["title"] for c in cards if c["id"] == exp.recommended_option_id)
    return {
        "asset": asset,
        "intent": intent.model_dump(mode="json"),
        "options": {asset: {"analysis": exp.analysis, "options": cards}},
        "comparison": {asset: {"rows": rows, "recommended": best_title, "reason": exp.reason}},
        "data_source": sources.pop() if len(sources) == 1 else "mixed",
    }
