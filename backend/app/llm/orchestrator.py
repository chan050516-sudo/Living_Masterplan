"""B7 — LLM orchestration.

Phase 12 (2026-10-16): replaced the agentic tool-calling loop with a
deterministic 4-stage pipeline.

  Stage 0  Intent parsing        1 LLM call
  Stage 1  Context assembly      0 LLM calls  (deterministic)
  Stage 2  Proposal              1 LLM call   (structured output)
  Stage 3  Validate + simulate   0 LLM calls  (deterministic)
  Stage 3b Retry once on reject  0-1 LLM call
  Stage 4  Justification         1 LLM call

Total: 3 LLM calls in the common case, 4 in the worst case. The
previous agentic design averaged 6-8 calls and took 2-3 minutes; this
design averages 30-60 seconds.

The LLM's role is narrowed to two decisions it is uniquely good at:
  1. Given a complete context pack, what intervention fits?
  2. Given a simulated outcome, how do we explain it?

Everything else — data fetching, tool dispatch, validation, and the
simulation itself — is deterministic code.
"""

import json
import logging
import uuid
from pathlib import Path

import pandas as pd

from .context_builder import build_context_pack
from .schemas import INTENT_SCHEMA, PROPOSAL_SCHEMA, JUSTIFICATION_SCHEMA
from .tool_service import TownshipDataSource
from .validator import ProposalValidator

log = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

PROMPTS_DIR = Path(__file__).parent / "prompts"

MAX_PROPOSAL_ATTEMPTS = 2   # one initial try + one retry on reject


# ------------------------------------------------------------------
# Public entry points
# ------------------------------------------------------------------


def orchestrate(
    user_query: str,
    selected_asset_ids: list,
    llm_client,
    repo_root: Path = None,
    base_year: int = 2026,
) -> dict:
    """Single-focus alias for orchestrate_and_simulate_batch."""
    return orchestrate_and_simulate_batch(
        user_query=user_query,
        selected_asset_ids=selected_asset_ids,
        llm_client=llm_client,
        repo_root=repo_root,
        base_year=base_year,
    )


def orchestrate_and_simulate_batch(
    user_query: str,
    selected_asset_ids: list,
    llm_client,
    repo_root: Path = None,
    base_year: int = 2026,
) -> dict:
    """
    Run the full 4-stage pipeline for a user query against a set of
    selected assets.

    Returns
    -------
    dict with keys: run_id, scenario_id, intent, context, proposal,
    validation, simulation, simulation_brief, justification, meta.
    """
    repo_root = repo_root or Path(__file__).resolve().parents[3]
    ds = TownshipDataSource(repo_root, year=base_year)
    validator = ProposalValidator(ds, base_year=base_year)

    run_id = f"LLM-{uuid.uuid4().hex[:8]}"

    # ---- Stage 0: intent parsing ----
    log.info("[%s] Stage 0 — intent parsing", run_id)
    intent = _parse_intent(user_query, selected_asset_ids, llm_client, base_year)

    # ---- Stage 1: context assembly (deterministic) ----
    log.info("[%s] Stage 1 — context assembly", run_id)
    context_pack = build_context_pack(intent, ds)
    log.info(
        "[%s] context pack: %d targets, %d asset classes",
        run_id, len(context_pack["targets"]),
        len(context_pack["available_subtypes"]),
    )

    # ---- Stage 2 + 3: proposal loop ----
    proposal = None
    validation = None
    validator_feedback = None
    attempt = 0
    for attempt in range(1, MAX_PROPOSAL_ATTEMPTS + 1):
        log.info("[%s] Stage 2 — proposal (attempt %d)", run_id, attempt)
        proposal = _generate_proposal(
            intent=intent,
            context_pack=context_pack,
            llm_client=llm_client,
            attempt=attempt,
            validator_feedback=validator_feedback,
        )

        log.info("[%s] Stage 3 — validation", run_id)
        validation = validator.validate(
            proposal.get("plan", []),
            constraints=intent.get("constraints") or {},
        )
        if validation.valid:
            break

        validator_feedback = {
            "errors": list(validation.errors),
            "warnings": list(validation.warnings),
            "note": (
                "The previous plan was rejected. Revise the plan to "
                "address every error. You may keep any part of the "
                "previous plan that was not flagged."
            ),
        }
        log.info(
            "[%s] proposal rejected: %s",
            run_id, "; ".join(validation.errors),
        )

    if not validation.valid:
        return {
            "run_id": run_id,
            "scenario_id": None,
            "intent": intent,
            "context": _summarise_context(context_pack),
            "proposal": proposal,
            "validation": validation.to_dict(),
            "simulation": None,
            "simulation_brief": None,
            "justification": None,
            "error": "max_proposal_attempts_reached",
            "meta": {
                "attempts": attempt,
                "asset_count": len(intent["target_asset_ids"]),
                "model": getattr(llm_client, "model", None),
            },
        }

    # ---- Stage 3b: write interventions + simulate ----
    log.info("[%s] Stage 3b — write + simulate", run_id)
    scenario_id = f"SC-{run_id}"
    _write_interventions(ds, scenario_id, validation.normalised_plan)

    simulation_result = _run_simulation(
        scenario_id, repo_root,
        selected_ids=intent["target_asset_ids"],
    )
    sim_brief = _summarise_simulation(simulation_result)

    # ---- Stage 4: justification ----
    log.info("[%s] Stage 4 — justification", run_id)
    justification = _write_justification(
        intent=intent,
        proposal=proposal,
        validation=validation,
        simulation=simulation_result,
        sim_brief=sim_brief,
        llm_client=llm_client,
    )

    return {
        "run_id": run_id,
        "scenario_id": scenario_id,
        "intent": intent,
        "context": _summarise_context(context_pack),
        "proposal": proposal,
        "validation": validation.to_dict(),
        "simulation": simulation_result,
        "simulation_brief": sim_brief,
        "justification": justification,
        "meta": {
            "attempts": attempt,
            "asset_count": len(intent["target_asset_ids"]),
            "model": getattr(llm_client, "model", None),
        },
    }


# ------------------------------------------------------------------
# Stage 0: intent parsing
# ------------------------------------------------------------------


def _parse_intent(user_query: str, selected_asset_ids: list,
                  llm_client, base_year: int) -> dict:
    """
    Parse the user's question into a structured intent.
    Falls back to a minimal default on failure.
    """
    system = _load_prompt("intent_parser.md")
    user = (
        f"User query: {user_query}\n\n"
        f"Selected assets: {selected_asset_ids}\n"
        f"Base year: {base_year}\n\n"
        "Return JSON only."
    )
    try:
        result = llm_client.chat_json(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            schema_hint=INTENT_SCHEMA,
        )
    except Exception as e:
        log.warning("Intent parsing failed: %s", e)
        result = {}

    if not isinstance(result, dict):
        result = {}

    targets = result.get("target_asset_ids") or selected_asset_ids
    if not isinstance(targets, list) or not targets:
        targets = selected_asset_ids

    objective = result.get("objective") or "balanced"
    if objective not in ("financial", "environmental", "social", "balanced"):
        objective = "balanced"

    constraints = result.get("constraints")
    if not isinstance(constraints, dict):
        constraints = None

    return {
        "target_asset_ids": targets,
        "objective": objective,
        "constraints": constraints,
        "question_text": result.get("question_text") or user_query,
        "raw_query": user_query,
    }


# ------------------------------------------------------------------
# Stage 2: proposal generation
# ------------------------------------------------------------------


def _generate_proposal(
    intent: dict,
    context_pack: dict,
    llm_client,
    attempt: int,
    validator_feedback: dict = None,
) -> dict:
    """
    Ask the LLM to produce a plan from the context pack.

    Uses strict structured output (chat_structured) with no thinking
    config — see vertex_client.chat_structured for why. Timing is
    logged so a stalled request is visible immediately.
    """
    import time

    prompt = _load_prompt("proposal_generator.md")

    user_content = {
        "context_pack": context_pack,
        "attempt": attempt,
    }
    if validator_feedback:
        user_content["validator_feedback"] = validator_feedback
        log.info(
            "Passing validator feedback into attempt %d: %s",
            attempt, validator_feedback.get("errors"),
        )

    t0 = time.time()
    try:
        result = llm_client.chat_structured(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(
                    user_content, default=str, indent=2,
                )},
            ],
            response_schema=PROPOSAL_SCHEMA,
        )
        log.info(
            "Stage 2 attempt %d: LLM call returned in %.2fs",
            attempt, time.time() - t0,
        )
    except Exception as e:
        log.error(
            "Stage 2 attempt %d failed after %.2fs: %s",
            attempt, time.time() - t0, e,
        )
        result = {}

    if not isinstance(result, dict):
        result = {}
    if "plan" not in result or not isinstance(result["plan"], list):
        result["plan"] = []
    if "reasoning_trace" not in result:
        result["reasoning_trace"] = ""

    return result


# ------------------------------------------------------------------
# Stage 3b: write interventions and run simulation
# ------------------------------------------------------------------


def _write_interventions(ds: TownshipDataSource, scenario_id: str, plan: list) -> None:
    """
    Append the validated plan to interventions.csv under a fresh
    scenario_id.
    """
    base = ds.repo_root / ds.paths["base"]
    path = base / "business" / "interventions.csv"

    rows = []
    for i, item in enumerate(plan, start=1):
        rows.append({
            "scenario_id": scenario_id,
            "intervention_id": f"INT-LLM-{i:03d}",
            "target_asset_id": item["asset_id"],
            "intervention_type": item["intervention_type"],
            "parameters_json": json.dumps(item.get("parameters") or {}),
            "expected_derived_json": item.get("expected_derived_json"),
            "expected_source": (
                "llm_estimate"
                if item.get("expected_derived_json")
                else None
            ),
            "construction_start_year": item["construction_start_year"],
            "construction_duration_months": item["construction_duration_months"],
            "activation_year": item["activation_year"],
            "during_construction_status": item["during_construction_status"],
            "capex_delta_rm": item.get("capex_delta_rm"),
            "opex_delta_rm": item.get("opex_delta_rm"),
            "validation_status": "pending",
            "status": "simulated",
        })

    new_df = pd.DataFrame(rows)
    if path.exists() and path.stat().st_size > 0:
        existing = pd.read_csv(path)
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df
    combined.to_csv(path, index=False)
    log.info(
        "Wrote %d LLM interventions to %s as scenario %s",
        len(rows), path, scenario_id,
    )


def _run_simulation(scenario_id: str, repo_root: Path,
                    selected_ids: list = None) -> dict:
    """Run the deterministic simulation. Imported lazily."""
    from ..simulation.engine import simulate_scenario
    try:
        return simulate_scenario(
            scenario_id, repo_root=repo_root, selected_ids=selected_ids,
        )
    except Exception as e:
        log.exception("Simulation failed for %s", scenario_id)
        return {"error": f"{type(e).__name__}: {e}"}


# ------------------------------------------------------------------
# Stage 4: justification
# ------------------------------------------------------------------


def _write_justification(
    intent: dict,
    proposal: dict,
    validation,
    simulation: dict,
    sim_brief: dict,
    llm_client,
) -> dict:
    """
    Ask the LLM to write a justification grounded in the simulation
    output.
    """
    prompt = _load_prompt("justification_writer.md")

    user_content = {
        "user_query": intent["question_text"],
        "objective": intent["objective"],
        "plan": validation.normalised_plan,
        "llm_reasoning_trace": proposal.get("reasoning_trace", ""),
        "alternatives_considered": proposal.get("alternatives_considered", []),
        "investment_cases": _extract_investment_cases(
            proposal.get("plan", []),
        ),
        "llm_expected_effects": _extract_expected_effects(
            validation.normalised_plan,
        ),
        "validator_warnings": validation.warnings,
        "simulation_brief": sim_brief,
    }

    try:
        result = llm_client.chat_json(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(
                    user_content, default=str, indent=2,
                )},
            ],
            schema_hint=JUSTIFICATION_SCHEMA,
        )
    except Exception as e:
        log.warning("Justification failed: %s", e)
        result = {"summary": "(justification unavailable)", "error": str(e)}

    if not isinstance(result, dict):
        result = {"summary": "(justification unavailable)"}

    return result


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _summarise_simulation(simulation: dict) -> dict:
    """Reduce a scenario result to the fields the LLM actually needs."""
    if not simulation or simulation.get("error"):
        return {"error": (simulation or {}).get("error", "no simulation result")}

    comparison = simulation.get("comparison", {}) or {}
    township = comparison.get("township_metrics", {}) or {}

    per_asset = comparison.get("per_asset") or {}
    if not per_asset:
        focus = comparison.get("focus_asset_id")
        if focus and comparison.get("metrics"):
            per_asset = {focus: comparison["metrics"]}

    map_diff = simulation.get("map_diff", {}) or {}

    return {
        "per_asset_metrics": per_asset,
        "aggregate": comparison.get("aggregate") or {},
        "township_metrics": township,
        "map_diff": {
            "changed_assets": map_diff.get("changed_assets", []),
            "spillover_assets": map_diff.get("spillover_assets", []),
            "project_schedule": map_diff.get("project_schedule", []),
        },
        "years": list(simulation.get("years", {}).keys()),
    }


def _extract_expected_effects(plan: list) -> dict:
    out = {}
    for item in plan:
        raw = item.get("expected_derived_json")
        if not raw:
            continue
        try:
            out[item["asset_id"]] = (
                json.loads(raw) if isinstance(raw, str) else raw
            )
        except (json.JSONDecodeError, TypeError):
            continue
    return out


def _extract_investment_cases(plan: list) -> dict:
    """Pull the investment_case block out of each plan item so the
    justification writer can reference it directly. Returns
    {asset_id: investment_case}."""
    out = {}
    for item in plan or []:
        aid = item.get("asset_id")
        ic = item.get("investment_case")
        if aid and isinstance(ic, dict):
            out[aid] = ic
    return out


def _summarise_context(context_pack: dict) -> dict:
    """
    Strip the heavy parts of the context pack before returning it in
    the result dict. The full pack is useful for debugging but too
    large to ship in every API response.
    """
    targets = context_pack.get("targets", [])
    return {
        "target_count": len(targets),
        "target_ids": [t["asset_id"] for t in targets],
        "asset_classes": sorted(
            set(t["identity"].get("asset_type") for t in targets
                if t.get("identity"))
        ),
        "objective": context_pack.get("objective"),
        "constraints": context_pack.get("constraints"),
    }


# ------------------------------------------------------------------
# Prompt loading
# ------------------------------------------------------------------


def _load_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    if not path.exists():
        log.warning("Prompt file missing: %s", path)
        return ""
    return path.read_text(encoding="utf-8")