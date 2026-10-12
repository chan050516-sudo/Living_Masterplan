"""B7 — LLM orchestration.

Implements the four-stage reasoning loop:

  Stage 1  Context gathering        LLM calls read tools freely
  Stage 2  Reasoning and proposal   LLM outputs a plan
  Stage 3  Validation and sim       Deterministic; may reject and loop
  Stage 4  Review and justification LLM writes the explanation

Two entry points are exposed:

  orchestrate(...)
      Single-focus variant. Writes a plan as a scenario, runs the
      simulation, and returns the full transcript. Kept for backward
      compatibility.

  orchestrate_and_simulate_batch(...)
      Multi-asset variant. The LLM produces ONE plan covering every
      selected asset in a single inference call. The plan is written
      as a single scenario and simulated in one pass with
      selected_ids set, so comparison.per_asset reports each asset's
      own before/after.

The orchestrator is LLM-client agnostic. It expects a client that
implements two methods:

  chat_with_tools(messages, tools) -> {
      "content": str | None,
      "tool_calls": [{"id": str, "name": str, "arguments": dict}] | None,
  }

  chat_json(messages, schema_hint) -> dict
"""

import json
import logging
import uuid
from pathlib import Path

import pandas as pd

from .tool_service import TownshipDataSource, dispatch
from .validator import ProposalValidator

log = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

PROMPTS_DIR = Path(__file__).parent / "prompts"
TOOLS_SCHEMA_PATH = Path(__file__).parent / "tools_schema.json"

MAX_TOOL_ROUNDS = 8           # limit runaway tool calling
MAX_PROPOSAL_ATTEMPTS = 3     # validator feedback loop


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
    """
    Single-focus variant kept for backward compatibility. Delegates to
    the batch implementation; the underlying simulation now returns
    both per_asset and focus_asset_id, so callers see no regression.
    """
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
    Run the full reasoning loop for a user query against a set of
    selected assets.

    The LLM produces ONE plan that covers every selected asset. That
    plan is written to interventions.csv as a single scenario and
    simulated in one pass with selected_ids set. The comparison block
    then reports per-asset before/after metrics, and the justification
    stage sees the entire multi-asset result at once.

    Parameters
    ----------
    user_query : str
        The user's natural-language question.
    selected_asset_ids : list[str]
        Assets the user selected on the map.
    llm_client :
        An object implementing chat_with_tools() and chat_json().
    repo_root : Path, optional
        Project root. Defaults to the repo containing this file.
    base_year : int
        The year the query is being made in.

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
    intent = _parse_intent(user_query, selected_asset_ids, llm_client, base_year)

    # ---- Stage 1: context gathering ----
    context = _gather_context(intent, ds, llm_client)

    # ---- Stage 2 + 3: proposal loop ----
    proposal = None
    validation = None
    attempt = 0
    for attempt in range(1, MAX_PROPOSAL_ATTEMPTS + 1):
        proposal = _generate_proposal(intent, context, ds, llm_client, attempt)
        validation = validator.validate(
            proposal.get("plan", []),
            constraints=intent.get("constraints") or {},
        )
        if validation.valid:
            break
        context = _append_validation_feedback(context, validation)
        log.info(
            "Proposal attempt %d rejected: %s",
            attempt, "; ".join(validation.errors),
        )

    if not validation.valid:
        return {
            "run_id": run_id,
            "scenario_id": None,
            "intent": intent,
            "context": _context_to_dict(context),
            "proposal": proposal,
            "validation": validation.to_dict(),
            "simulation": None,
            "simulation_brief": None,
            "justification": None,
            "error": "max_proposal_attempts_reached",
            "meta": {
                "attempts": MAX_PROPOSAL_ATTEMPTS,
                "asset_count": len(intent["target_asset_ids"]),
                "model": getattr(llm_client, "model", None),
            },
        }

    # ---- Stage 3b: write interventions + simulate (single pass) ----
    scenario_id = f"SC-{run_id}"
    _write_interventions(ds, scenario_id, validation.normalised_plan)

    simulation_result = _run_simulation(
        scenario_id, repo_root,
        selected_ids=intent["target_asset_ids"],
    )

    sim_brief = _summarise_simulation(simulation_result)

    # ---- Stage 4: review and justification ----
    justification = _write_justification(
        intent=intent,
        proposal=proposal,
        validation=validation,
        simulation=simulation_result,
        ds=ds,
        llm_client=llm_client,
    )

    return {
        "run_id": run_id,
        "scenario_id": scenario_id,
        "intent": intent,
        "context": _context_to_dict(context),
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
    Parse the user's question into a structured intent. If the LLM
    fails to return valid JSON, fall back to a minimal default that
    still lets the pipeline run.
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
            schema_hint={
                "target_asset_ids": "list[str]",
                "objective": "financial|environmental|social|balanced",
                "constraints": "object | null",
                "question_text": "str",
            },
        )
    except Exception as e:
        log.warning("Intent parsing failed: %s", e)
        result = {}

    if not isinstance(result, dict):
        result = {}
    targets = result.get("target_asset_ids") or selected_asset_ids
    if not isinstance(targets, list):
        targets = selected_asset_ids
    objective = result.get("objective") or "balanced"
    if objective not in ("financial", "environmental", "social", "balanced"):
        objective = "balanced"
    constraints = result.get("constraints")
    if constraints is not None and not isinstance(constraints, dict):
        constraints = None

    return {
        "target_asset_ids": targets,
        "objective": objective,
        "constraints": constraints,
        "question_text": result.get("question_text") or user_query,
        "raw_query": user_query,
    }


# ------------------------------------------------------------------
# Stage 1: context gathering
# ------------------------------------------------------------------


def _gather_context(intent: dict, ds: TownshipDataSource, llm_client) -> dict:
    """
    Let the LLM decide what to query. We seed it with a minimal bundle
    (the selected assets' identity + status) and then let it call tools
    to gather more.
    """
    seed = {
        "user_query": intent["question_text"],
        "objective": intent["objective"],
        "constraints": intent["constraints"],
        "selected_assets": [
            {
                "asset_id": aid,
                "state_summary": _compact_state(ds, aid),
                "deadspace_status": _compact_status(ds, aid),
            }
            for aid in intent["target_asset_ids"]
        ],
    }

    tools_schema = _load_tools_schema()
    messages = [
        {"role": "system", "content": _load_prompt("context_gathering.md")},
        {"role": "user", "content": json.dumps(seed, indent=2)},
    ]

    tool_calls_log = []
    notes = []
    validator_feedback = None

    for _ in range(MAX_TOOL_ROUNDS):
        try:
            response = llm_client.chat_with_tools(messages, tools_schema)
        except Exception as e:
            log.warning("chat_with_tools failed: %s", e)
            break

        tool_calls = response.get("tool_calls") or []
        content = response.get("content")

        messages.append({
            "role": "assistant",
            "content": content,
            "tool_calls": tool_calls,
        })

        if not tool_calls:
            if content:
                notes.append(content)
            break

        for call in tool_calls:
            name = call.get("name")
            args = call.get("arguments") or {}
            outcome = dispatch(ds, name, args)
            tool_calls_log.append({
                "name": name,
                "arguments": args,
                "ok": outcome["ok"],
                "result_summary": _summarise(outcome),
            })
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", name),
                "name": name,
                "content": json.dumps(outcome, default=str)[:8000],
            })

    return {
        "seed": seed,
        "messages": messages,
        "tool_calls": tool_calls_log,
        "notes": notes,
        "validator_feedback": validator_feedback,
    }


def _compact_state(ds: TownshipDataSource, asset_id: str) -> dict:
    from .tool_service import get_asset_state
    s = get_asset_state(ds, asset_id)
    if "identity" not in s:
        return s
    return {
        "asset_type": s["identity"].get("asset_type"),
        "subtype": s["identity"].get("subtype"),
        "floor_area_m2": s["physical"].get("floor_area_m2"),
        "lettable_area_m2": s["physical"].get("lettable_area_m2"),
        "land_area_m2": s["physical"].get("land_area_m2"),
        "capacity": s["physical"].get("capacity"),
        "key_metrics": {
            k: v for k, v in {
                **s.get("observed_metrics", {}),
                **s.get("derived_metrics", {}),
            }.items() if v is not None
        },
    }


def _compact_status(ds: TownshipDataSource, asset_id: str) -> dict:
    from .tool_service import get_deadspace_status
    s = get_deadspace_status(ds, asset_id)
    return {
        "status": s.get("status"),
        "flags": s.get("flags", []),
        "urgency_index": s.get("urgency_index"),
    }


def _context_to_dict(context: dict) -> dict:
    """
    Strip the raw message list before returning the context to the
    caller. The messages are useful for debugging but heavy to ship.
    """
    return {
        "seed": context.get("seed"),
        "tool_calls": context.get("tool_calls", []),
        "notes": context.get("notes", []),
        "validator_feedback": context.get("validator_feedback"),
    }


# ------------------------------------------------------------------
# Stage 2: proposal generation
# ------------------------------------------------------------------


def _generate_proposal(intent: dict, context: dict, ds: TownshipDataSource,
                       llm_client, attempt: int) -> dict:
    """
    Ask the LLM to produce a plan. The context includes everything it
    gathered plus any validator feedback from a previous attempt.
    """
    prompt = _load_prompt("proposal_generator.md")

    township_snapshot = _build_township_snapshot(ds, intent["target_asset_ids"])

    user_content = {
        "user_query": intent["question_text"],
        "objective": intent["objective"],
        "constraints": intent["constraints"],
        "selected_assets": intent["target_asset_ids"],
        "context_notes": context.get("notes", []),
        "tool_calls_made": [c["name"] for c in context.get("tool_calls", [])],
        "township_snapshot": township_snapshot,
        "attempt": attempt,
        "validator_feedback": context.get("validator_feedback"),
    }

    try:
        result = llm_client.chat_json(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(user_content, default=str, indent=2)},
            ],
            schema_hint={
                "reasoning_trace": "str",
                "plan": [{
                    "asset_id": "str",
                    "type": "str",
                    "parameters": "object",
                    "expected_effects": "object | null",
                    "rationale": "str",
                }],
            },
        )
    except Exception as e:
        log.warning("Proposal generation failed: %s", e)
        result = {}

    if not isinstance(result, dict):
        result = {}
    if "plan" not in result or not isinstance(result["plan"], list):
        result["plan"] = []
    if "reasoning_trace" not in result:
        result["reasoning_trace"] = ""

    return result


def _build_township_snapshot(ds: TownshipDataSource, selected_ids: list) -> dict:
    """
    A compact snapshot the LLM can reason over without additional tool
    calls. Includes the taxonomy summary for the relevant asset classes
    and the selected assets' neighbours.
    """
    from .tool_service import get_nearby_assets, get_available_subtypes

    asset_classes = set()
    for aid in selected_ids:
        row = ds._asset_row(aid)
        if row:
            asset_classes.add(row["asset_type"])

    taxonomy_for_selected = {}
    for cls in asset_classes:
        taxonomy_for_selected[cls] = get_available_subtypes(ds, cls)

    neighbours = {}
    for aid in selected_ids:
        neighbours[aid] = get_nearby_assets(ds, aid, radius_m=800.0)

    return {
        "available_subtypes_by_class": taxonomy_for_selected,
        "nearby_assets_800m": neighbours,
        "model_assumptions": {
            "huff": ds.assumptions.get("huff", {}),
            "occupancy_dynamics": ds.assumptions.get("occupancy_dynamics", {}),
        },
    }


# ------------------------------------------------------------------
# Stage 3b: write interventions and run simulation
# ------------------------------------------------------------------


def _write_interventions(ds: TownshipDataSource, scenario_id: str, plan: list) -> None:
    """
    Append the validated plan to interventions.csv under a fresh
    scenario_id. The simulation reads that file.
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
            "expected_source": "llm_estimate" if item.get("expected_derived_json") else None,
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
    log.info("Wrote %d LLM interventions to %s as scenario %s", len(rows), path, scenario_id)


def _run_simulation(scenario_id: str, repo_root: Path,
                    selected_ids: list = None) -> dict:
    """
    Run the deterministic simulation. Imported lazily to avoid a
    circular import at module load time.
    """
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


def _write_justification(intent: dict, proposal: dict, validation, simulation: dict,
                         ds: TownshipDataSource, llm_client) -> dict:
    """
    Ask the LLM to write a justification grounded in the simulation
    output. The LLM may add domain insight but must not invent numbers.
    """
    prompt = _load_prompt("justification_writer.md")
    sim_brief = _summarise_simulation(simulation)

    user_content = {
        "user_query": intent["question_text"],
        "objective": intent["objective"],
        "plan": validation.normalised_plan,
        "llm_reasoning_trace": proposal.get("reasoning_trace", ""),
        "llm_expected_effects": _extract_expected_effects(validation.normalised_plan),
        "validator_warnings": validation.warnings,
        "simulation_brief": sim_brief,
    }

    try:
        result = llm_client.chat_json(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(user_content, default=str, indent=2)},
            ],
            schema_hint={
                "summary": "str (≤80 words)",
                "why_this_plan": "str",
                "what_simulation_shows": "str",
                "beyond_the_model": "str | null",
                "recommendation": "str",
            },
        )
    except Exception as e:
        log.warning("Justification failed: %s", e)
        result = {"summary": "(justification unavailable)", "error": str(e)}

    if not isinstance(result, dict):
        result = {"summary": "(justification unavailable)"}

    return result


def _summarise_simulation(simulation: dict) -> dict:
    """
    Reduce a scenario result to the fields the LLM actually needs.

    Priority:
      1. comparison.per_asset  (multi-asset format)
      2. comparison.metrics    (legacy single-focus fallback)
    """
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
            out[item["asset_id"]] = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            continue
    return out


# ------------------------------------------------------------------
# Validator feedback
# ------------------------------------------------------------------


def _append_validation_feedback(context: dict, validation) -> dict:
    """
    Return a new context dict with the validator's errors and warnings
    stored under a key the proposal prompt can read.
    """
    new_context = dict(context)
    new_context["validator_feedback"] = {
        "errors": list(validation.errors),
        "warnings": list(validation.warnings),
        "note": (
            "The previous plan was rejected. Revise the plan to address "
            "each error. You may keep any part of the previous plan that "
            "was not flagged."
        ),
    }
    return new_context


# ------------------------------------------------------------------
# Prompt and schema loading
# ------------------------------------------------------------------


def _load_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    if not path.exists():
        log.warning("Prompt file missing: %s", path)
        return ""
    return path.read_text(encoding="utf-8")


def _load_tools_schema() -> list:
    if not TOOLS_SCHEMA_PATH.exists():
        log.warning("tools_schema.json missing")
        return []
    with open(TOOLS_SCHEMA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("tools", [])


# ------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------


def _summarise(outcome: dict) -> str:
    """Very short summary of a tool result for the audit log."""
    if not outcome.get("ok"):
        return f"ERROR: {outcome.get('error')}"
    r = outcome.get("result")
    if isinstance(r, list):
        return f"list[{len(r)}]"
    if isinstance(r, dict):
        return f"dict({len(r)} keys)"
    return str(type(r).__name__)