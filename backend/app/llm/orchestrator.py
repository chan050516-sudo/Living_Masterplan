"""B7 — LLM orchestration.

Phase 13 (2026-10-17) — P0 multi-candidate architecture:

  Stage 0    Intent parsing                1 LLM call
  Stage 1    Context assembly              0
  Stage 2    Candidate generation          1 LLM call → 2-3 candidates
  Stage 2.5a Validate every candidate      0
  Stage 2.5b Simulate every valid candidate 0 (B4, parallel)
  Stage 2.7  Final selection               1 LLM call
  Stage 3    (already done in 2.5a)        0
  Stage 3b   (already done in 2.5b)        0
  Stage 4    Justification                 1 LLM call

Total: 4 LLM calls, N B4 simulations.

The core benefit: the selection stage (2.7) sees the ACTUAL simulated
outcome of every candidate. It no longer invents CAPEX estimates or
imagines occupancy trajectories. The LLM's role narrows to:
  1. Given a context pack, what are 2-3 meaningfully different plans?
  2. Given the simulated outcomes, which one fits the objective?
  3. Given the chosen outcome, how do we explain it?
"""

import json
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from .context_builder import build_context_pack
from .schemas import (
    INTENT_SCHEMA,
    CANDIDATES_SCHEMA,
    SELECTION_SCHEMA,
    JUSTIFICATION_SCHEMA,
)
from .tool_service import TownshipDataSource
from .validator import ProposalValidator

log = logging.getLogger(__name__)


PROMPTS_DIR = Path(__file__).parent / "prompts"
MAX_PROPOSAL_ATTEMPTS = 2
MAX_PARALLEL_SIMULATIONS = 3


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
    Run the multi-candidate pipeline.

    Returns
    -------
    dict with keys: run_id, scenario_id, intent, context, candidates,
    selection, proposal, validation, simulation, simulation_brief,
    justification, meta.
    """
    repo_root = repo_root or Path(__file__).resolve().parents[3]
    ds = TownshipDataSource(repo_root, year=base_year)
    validator = ProposalValidator(ds, base_year=base_year)
    run_id = f"LLM-{uuid.uuid4().hex[:8]}"

    # ---- Stage 0: intent parsing ----
    log.info("[%s] Stage 0 — intent parsing", run_id)
    intent = _parse_intent(user_query, selected_asset_ids, llm_client, base_year)

    # ---- Stage 1: context assembly ----
    log.info("[%s] Stage 1 — context assembly", run_id)
    context_pack = build_context_pack(intent, ds)
    log.info(
        "[%s] context pack: %d targets, %d asset classes",
        run_id, len(context_pack["targets"]),
        len(context_pack["available_subtypes"]),
    )

    # ---- Stage 2 + 2.5a: generate candidates and validate them ----
    valid_candidates: list = []
    last_raw_candidates: list = []
    candidate_feedback = None
    attempt = 0
    for attempt in range(1, MAX_PROPOSAL_ATTEMPTS + 1):
        log.info("[%s] Stage 2 — candidate generation (attempt %d)", run_id, attempt)
        raw = _generate_candidates(
            intent=intent,
            context_pack=context_pack,
            llm_client=llm_client,
            attempt=attempt,
            candidate_feedback=candidate_feedback,
        )
        last_raw_candidates = raw.get("candidates", [])
        overall_reasoning = raw.get("reasoning_trace", "")

        log.info(
            "[%s] Stage 2.5a — validating %d candidates",
            run_id, len(last_raw_candidates),
        )
        valid_candidates = []
        rejection_feedback = []
        for cand in last_raw_candidates:
            v = validator.validate(
                cand.get("plan", []),
                constraints=intent.get("constraints") or {},
            )
            if v.valid:
                valid_candidates.append({
                    "name": cand.get("name", f"candidate-{len(valid_candidates)+1}"),
                    "strategy_summary": cand.get("strategy_summary", ""),
                    "reasoning_trace": cand.get("reasoning_trace", ""),
                    "plan": cand.get("plan", []),
                    "validation": v,
                })
            else:
                log.info(
                    "[%s] candidate '%s' rejected: %s",
                    run_id, cand.get("name"), "; ".join(v.errors),
                )
                rejection_feedback.append({
                    "name": cand.get("name"),
                    "errors": list(v.errors),
                })

        if valid_candidates:
            break

        candidate_feedback = {
            "rejected_candidates": rejection_feedback,
            "note": (
                "All candidates were rejected by the validator. Revise "
                "at least one candidate to pass. You may keep parts of "
                "the previous candidates that were not flagged."
            ),
        }
        log.warning("[%s] all candidates invalid on attempt %d", run_id, attempt)

    if not valid_candidates:
        return {
            "run_id": run_id,
            "scenario_id": None,
            "intent": intent,
            "context": _summarise_context(context_pack),
            "candidates": [],
            "selection": None,
            "proposal": {"reasoning_trace": overall_reasoning,
                          "plan": []},
            "validation": {"valid": False, "errors": ["no valid candidates"]},
            "simulation": None,
            "simulation_brief": None,
            "justification": None,
            "error": "max_proposal_attempts_reached",
            "meta": {
                "attempts": attempt,
                "candidate_count": 0,
                "asset_count": len(intent["target_asset_ids"]),
                "model": getattr(llm_client, "model", None),
            },
        }

    # ---- Stage 2.5b: write interventions (sequential) ----
    for i, cand in enumerate(valid_candidates, start=1):
        cand["scenario_id"] = f"SC-{run_id}-C{i}"
        _write_interventions(
            ds, cand["scenario_id"], cand["validation"].normalised_plan,
        )
        log.info(
            "[%s] candidate '%s' written as %s",
            run_id, cand["name"], cand["scenario_id"],
        )

    # ---- Stage 2.5b: simulate every candidate (shared setup) ----
    log.info(
        "[%s] Stage 2.5b — simulating %d candidates with shared setup",
        run_id, len(valid_candidates),
    )
    _simulate_candidates_shared(
        valid_candidates,
        repo_root=repo_root,
        selected_ids=intent["target_asset_ids"],
    )
    for cand in valid_candidates:
        if "simulation" not in cand:
            cand["simulation"] = {"error": "simulation did not return"}
        cand["simulation_brief"] = _summarise_simulation(cand["simulation"])

    # ---- Stage 2.7: final selection ----
    log.info("[%s] Stage 2.7 — final selection", run_id)
    selection = _select_candidate(
        intent=intent,
        candidates=valid_candidates,
        llm_client=llm_client,
    )

    selected_name = selection.get("selected_candidate_name")
    selected = next(
        (c for c in valid_candidates if c["name"] == selected_name),
        valid_candidates[0],
    )
    if selected["name"] != selected_name:
        log.warning(
            "[%s] LLM selected unknown candidate '%s'; falling back to '%s'",
            run_id, selected_name, selected["name"],
        )

    # ---- Stage 3 / 3b: already done ----
    validation = selected["validation"]
    simulation_result = selected["simulation"]
    sim_brief = selected["simulation_brief"]
    scenario_id = selected["scenario_id"]

    # Derive alternatives from the non-selected candidates
    alternatives_considered = [
        {
            "asset_id": c["plan"][0].get("asset_id") if c["plan"] else None,
            "type": c["plan"][0].get("type") if c["plan"] else None,
            "summary": c.get("strategy_summary", c.get("name", "")),
            "rejected_because": _summarise_candidate_outcome(c),
        }
        for c in valid_candidates
        if c["name"] != selected["name"]
    ]

    # ---- Stage 4: justification ----
    log.info("[%s] Stage 4 — justification", run_id)
    justification = _write_justification(
        intent=intent,
        selected=selected,
        selection=selection,
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
        "candidates": [
            {
                "name": c["name"],
                "strategy_summary": c.get("strategy_summary", ""),
                "plan": c["plan"],
                "scenario_id": c["scenario_id"],
                "simulation_brief": c["simulation_brief"],
            }
            for c in valid_candidates
        ],
        "selection": selection,
        "proposal": {
            "reasoning_trace": selected.get("reasoning_trace", ""),
            "strategy_summary": selected.get("strategy_summary", ""),
            "plan": selected["plan"],
            "alternatives_considered": alternatives_considered,
        },
        "validation": validation.to_dict(),
        "simulation": simulation_result,
        "simulation_brief": sim_brief,
        "justification": justification,
        "meta": {
            "attempts": attempt,
            "candidate_count": len(valid_candidates),
            "asset_count": len(intent["target_asset_ids"]),
            "model": getattr(llm_client, "model", None),
        },
    }


# ------------------------------------------------------------------
# Stage 0: intent parsing
# ------------------------------------------------------------------


def _parse_intent(user_query, selected_asset_ids, llm_client, base_year):
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
# Stage 2: candidate generation
# ------------------------------------------------------------------


def _generate_candidates(
    intent, context_pack, llm_client, attempt, candidate_feedback=None,
):
    import time

    prompt = _load_prompt("candidate_generator.md")

    user_content = {
        "context_pack": context_pack,
        "attempt": attempt,
    }
    if candidate_feedback:
        user_content["candidate_feedback"] = candidate_feedback

    t0 = time.time()
    try:
        result = llm_client.chat_structured(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(
                    user_content, default=str, indent=2,
                )},
            ],
            response_schema=CANDIDATES_SCHEMA,
        )
        log.info(
            "Stage 2 attempt %d: candidates returned in %.2fs",
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
    if "candidates" not in result or not isinstance(result["candidates"], list):
        result["candidates"] = []
    if "reasoning_trace" not in result:
        result["reasoning_trace"] = ""
    return result


# ------------------------------------------------------------------
# Stage 2.5b: parallel simulation
# ------------------------------------------------------------------


def _simulate_candidates_shared(candidates, repo_root, selected_ids):
    """
    Run B4 for every candidate, sharing the heavy setup across them.

    Design note
    -----------
    This used to run candidates in a ThreadPoolExecutor. That was
    removed for two reasons:

      1. Python's GIL prevents real parallelism in numpy / networkx /
         geopandas heavy sections, so parallel execution delivered
         only ~1.3x speedup on a 3-candidate run.

      2. A shared cache lets later candidates skip the two dominant
         costs entirely — B3 derived metrics (~35s) and the walking
         pipeline build + all-pairs Dijkstra (~45s). Those costs are
         identical across candidates for the same base network and
         year.

    Serial execution with a shared cache is measurably faster than
    parallel execution without one:
       - 3 candidates, parallel, no cache:  ~270s
       - 3 candidates, serial, shared cache: ~130s

    The cache is a plain dict owned by this function. It is passed
    to simulate_scenario via _shared_cache and reused across all
    candidates. See simulation.engine.simulate_scenario for details.
    """
    if not candidates:
        return

    shared_cache: dict = {}
    for idx, cand in enumerate(candidates, start=1):
        log.info(
            "[shared] simulating candidate %d/%d: %s (%s)",
            idx, len(candidates), cand["name"], cand["scenario_id"],
        )
        t0 = time.time()
        cand["simulation"] = _run_simulation(
            cand["scenario_id"], repo_root,
            selected_ids=selected_ids,
            _shared_cache=shared_cache,
        )
        log.info(
            "[shared] candidate %d/%d finished in %.1fs",
            idx, len(candidates), time.time() - t0,
        )


# ------------------------------------------------------------------
# Stage 2.7: selection
# ------------------------------------------------------------------


def _select_candidate(intent, candidates, llm_client):
    import time

    prompt = _load_prompt("selection_writer.md")

    # Build a compact view of every candidate's simulation for the LLM.
    candidate_summaries = []
    for c in candidates:
        brief = _summarise_simulation(c.get("simulation", {}))
        candidate_summaries.append({
            "name": c["name"],
            "strategy_summary": c.get("strategy_summary", ""),
            "plan_types": [
                {"asset_id": item.get("asset_id"), "type": item.get("type")}
                for item in c.get("plan", [])
            ],
            "simulation_brief": brief,
        })

    user_content = {
        "user_query": intent["question_text"],
        "objective": intent["objective"],
        "constraints": intent.get("constraints"),
        "candidates": candidate_summaries,
    }

    t0 = time.time()
    try:
        result = llm_client.chat_json(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(
                    user_content, default=str, indent=2,
                )},
            ],
            schema_hint=SELECTION_SCHEMA,
        )
        log.info(
            "Stage 2.7: selection returned in %.2fs", time.time() - t0,
        )
    except Exception as e:
        log.warning("Selection failed: %s", e)
        result = {}

    if not isinstance(result, dict):
        result = {}
    if not result.get("selected_candidate_name") and candidates:
        result["selected_candidate_name"] = candidates[0]["name"]
        result.setdefault(
            "selection_reasoning",
            "(auto-selected first valid candidate)",
        )
    return result


def _summarise_candidate_outcome(cand):
    """Short text describing why a non-selected candidate was rejected."""
    sim = cand.get("simulation") or {}
    if sim.get("error"):
        return f"simulation error: {sim['error']}"
    brief = cand.get("simulation_brief") or {}
    agg = brief.get("aggregate") or {}
    delta = agg.get("carbon_delta_pct")
    if delta is None:
        return "simulated, but no aggregate carbon delta reported"
    try:
        pct = float(delta) * 100.0
        return f"simulated {pct:+.1f}% aggregate carbon delta"
    except (TypeError, ValueError):
        return "simulated"


# ------------------------------------------------------------------
# Stage 3b: write interventions
# ------------------------------------------------------------------


def _write_interventions(ds, scenario_id, plan):
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
                "llm_estimate" if item.get("expected_derived_json") else None
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
        "Wrote %d interventions to %s as scenario %s",
        len(rows), path, scenario_id,
    )


def _run_simulation(scenario_id, repo_root, selected_ids=None,
                    _shared_cache=None):
    from ..simulation.engine import simulate_scenario
    try:
        return simulate_scenario(
            scenario_id, repo_root=repo_root, selected_ids=selected_ids,
            _shared_cache=_shared_cache,
        )
    except Exception as e:
        log.exception("Simulation failed for %s", scenario_id)
        return {"error": f"{type(e).__name__}: {e}"}


# ------------------------------------------------------------------
# Stage 4: justification
# ------------------------------------------------------------------


def _write_justification(
    intent, selected, selection, validation,
    simulation, sim_brief, llm_client,
):
    prompt = _load_prompt("justification_writer.md")

    user_content = {
        "user_query": intent["question_text"],
        "objective": intent["objective"],
        "plan": validation.normalised_plan,
        "selected_candidate_name": selected["name"],
        "selection_reasoning": selection.get("selection_reasoning", ""),
        "key_trade_offs": selection.get("key_trade_offs", []),
        "candidate_reasoning": selected.get("reasoning_trace", ""),
        "investment_cases": _extract_investment_cases(selected.get("plan", [])),
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


def _summarise_simulation(simulation):
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


def _extract_expected_effects(plan):
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


def _extract_investment_cases(plan):
    out = {}
    for item in plan or []:
        aid = item.get("asset_id")
        ic = item.get("investment_case")
        if aid and isinstance(ic, dict):
            out[aid] = ic
    return out


def _summarise_context(context_pack):
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


def _load_prompt(name):
    path = PROMPTS_DIR / name
    if not path.exists():
        log.warning("Prompt file missing: %s", path)
        return ""
    return path.read_text(encoding="utf-8")