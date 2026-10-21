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
    FINAL_DECISION_SCHEMA,  # 替换原本的两个
)
from .tool_service import TownshipDataSource
from .validator import ProposalValidator
from ..derived.environmental import MATERIAL_INTENSITY_REPURPOSE
from ..simulation.engine import (
    PROJECT_ID_PREFIX,
    simulate_scenario,
    write_scenario_result,
)

log = logging.getLogger(__name__)


PROMPTS_DIR = Path(__file__).parent / "prompts"
MAX_PROPOSAL_ATTEMPTS = 2
MAX_PARALLEL_SIMULATIONS = 3


# P2-5 fix — new-build CAPEX reference rates (RM per m² GFA).
#
# Used ONLY to size the "what if we rebuilt instead of reused"
# counterfactual on the frontend card. This table intentionally
# mirrors `bukit_jelutong/build_mock_data.CAPEX_PER_M2`, but that
# module is a preprocessing script and must not be imported by
# runtime code. Keeping a local copy at the orchestration layer
# makes the dependency explicit and reviewable.
#
# Material intensity for the repurpose side is NOT duplicated —
# it comes from `derived.environmental.MATERIAL_INTENSITY_REPURPOSE`.
_NEW_BUILD_CAPEX_RM_PER_M2 = {
    "commercial":         3500.0,
    "community_facility": 3000.0,
    "residential":        2500.0,
    "green_space":         400.0,
    "undeveloped_parcel":    0.0,
}


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
    attachments: list = None,
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
    intent = _parse_intent(
        user_query, selected_asset_ids, llm_client, base_year,
        attachments=attachments,
    )

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

    # Phase 15 — verify every catalytic claim against the simulation
    # before the selection stage sees it.
    _verify_catalytic_links(valid_candidates)

    # Phase E — build the structured catalytic evidence block so the
    # selection stage can compare effect magnitude across candidates.
    _build_catalytic_evidence(valid_candidates)

    # ---- Stage 2.7: Final Selection & Justification ---- #
    log.info("[%s] Stage 2.7 — final selection and justification", run_id)
    final_decision = _select_and_justify(
        intent=intent,
        candidates=valid_candidates,
        llm_client=llm_client,
    )

    selected_name = final_decision.get("selected_candidate_name")
    selected = next(
        (c for c in valid_candidates if c["name"] == selected_name),
        valid_candidates[0],
    )
    if selected["name"] != selected_name:
        log.warning(
            "[%s] LLM selected unknown candidate '%s'; falling back to '%s'",
            run_id, selected_name, selected["name"],
        )

    # ---- Extract Results ---- #
    validation = selected["validation"]
    simulation_result = selected["simulation"]
    sim_brief = selected["simulation_brief"]
    scenario_id = selected["scenario_id"]

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

    # Format the final justification text
    justification = {
        "summary": final_decision.get("executive_summary", ""),
        "why_this_plan": final_decision.get("why_this_plan", ""),
        "what_simulation_shows": final_decision.get("what_simulation_shows", ""),
        "beyond_the_model": final_decision.get("beyond_the_model"),
        "recommendation": final_decision.get("recommendation", ""),
    }

    # Build frontend-ready payload
    frontend_payload = _build_frontend_payload(
        simulation=simulation_result,
        comparison=simulation_result.get("comparison", {}),
        intent=intent,
        final_decision={
            **final_decision,
            "run_id": run_id,
        }
    )
    
    # Construct the heavy debug payload for local storage only
    debug_payload = {
        "run_id": run_id,
        "frontend": frontend_payload,
        "intent": intent,
        "candidates_raw": valid_candidates,
        "validation": validation.to_dict(),
    }

    # Write the heavy data to disk
    _write_orchestration_result(debug_payload, repo_root)

    # Attach a lightweight candidate summary to the API response
    # so run_llm_real2.py can print it without fetching the heavy file.
    frontend_payload["candidates_summary"] = [
        {
            "name": c["name"],
            "strategy_summary": c.get("strategy_summary", ""),
            "plan": c["plan"],
        }
        for c in valid_candidates
    ]
    
    return frontend_payload


# ------------------------------------------------------------------
# Stage 0: intent parsing
# ------------------------------------------------------------------


def _parse_intent(user_query, selected_asset_ids, llm_client, base_year, attachments=None):
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
            attachments=attachments,
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
    Run B4 for the baseline and every candidate, sharing the heavy setup.

    Multi-asset support: B4 natively simulates all assets in the township,
    but the comparison block will filter down to the `selected_ids`.
    We first run the baseline (SC-CURRENT) so we have a valid comparison
    for the frontend dashboard.

    P2-4 fix — the baseline `years` dict was copied verbatim into every
    candidate's scenario JSON, producing N_candidates × N_years ×
    N_assets duplication. It is now trimmed to the union of:

      - `selected_ids`
      - catalytic beneficiaries across every candidate
      - PRJ::* project pseudo-entries

    The catalytic beneficiaries are not known until AFTER candidate
    generation, so the union is computed here, before the simulation
    loop, from the candidates that have already been validated.
    """
    if not candidates:
        return

    shared_cache: dict = {}

    # Run baseline (SC-CURRENT) first to provide comparison data
    log.info("[shared] simulating BASELINE (SC-CURRENT)")
    baseline_sim = _run_simulation(
        "SC-CURRENT", repo_root, selected_ids=selected_ids,
        _shared_cache=shared_cache,
    )
    baseline_years_full = baseline_sim.get("years", {})

    # P2-4 fix — collect every asset the frontend needs to render,
    # not the whole township state.
    extra_ids: set = set()
    for cand in candidates:
        for item in cand.get("plan", []):
            if item.get("role") != "catalytic":
                continue
            b_id = (item.get("catalytic_link") or {}).get(
                "beneficiary_asset_id",
            )
            if b_id:
                extra_ids.add(b_id)

    keep_ids = set(selected_ids or []) | extra_ids
    baseline_years = _filter_years_to_ids(baseline_years_full, keep_ids)

    log.info(
        "[shared] baseline trimmed to %d asset ids (from %d)",
        len(next(iter(baseline_years.values()), {}).get("assets", {}))
            if baseline_years else 0,
        len(next(iter(baseline_years_full.values()), {}).get("assets", {}))
            if baseline_years_full else 0,
    )

    # Run all candidates
    for idx, cand in enumerate(candidates, start=1):
        log.info(
            "[shared] simulating candidate %d/%d: %s (%s)",
            idx, len(candidates), cand["name"], cand["scenario_id"],
        )
        t0 = time.time()
        cand["simulation"] = _run_simulation(
            cand["scenario_id"], repo_root, selected_ids=selected_ids,
            _shared_cache=shared_cache,
        )

        # Inject baseline data into the simulation result
        if not cand["simulation"].get("error"):
            cand["simulation"]["_baseline_years"] = baseline_years
            try:
                write_scenario_result(
                    cand["simulation"], repo_root=repo_root,
                )
            except Exception as e:
                log.warning(
                    f"Failed to write scenario "
                    f"{cand['scenario_id']}: {e}"
                )

        log.info(
            "[shared] candidate %d/%d finished in %.1fs",
            idx, len(candidates), time.time() - t0,
        )


def _verify_catalytic_links(candidates):
    """
    Phase 15 — post-simulation catalytic verification.

    For every plan item with role='catalytic', compare the actual
    simulated delta on the beneficiary against the declared
    verification_level. Where the delta is absent or contradicts the
    claim, downgrade the level and record a warning on the candidate.

    The function never removes an item. It only annotates.

    Mechanism → metric contract
    ---------------------------
    Each mechanism has a PRIMARY metric that must move for the claim
    to be fully confirmed, and optionally a SECONDARY metric that is
    weaker evidence.

      walkability_improvement
        primary   coverage_ratio_10min_walk
        The walk coverage ratio is a physical measurement of the
        network, independent of the Huff allocation. A positive delta
        confirms the mechanism.

      catchment_growth
        primary   reachable_population_walk
        secondary effective_demand_m2
        The primary metric is a physical resident count within the
        walking catchment. It does not pass through Huff, so a
        positive delta confirms the mechanism at 'verified'.
        The secondary metric is the Huff-assigned demand; because
        Huff carries un-calibrated assumptions, it can only support
        'partially_verified'.

      competition_relief
        primary   effective_demand_m2
        Entirely Huff-dependent. The declaration ceiling is already
        'partially_verified' (set by the validator); this function
        can only downgrade further.

    Levels are strictly capped downward by simulation evidence:
      - declared > achievable  →  set to achievable
      - declared <= achievable →  unchanged

    P3-a fix — verification notes are now attached to the candidate
    (as `_verification_notes`), not to the catalytic_link dict. This
    keeps `catalytic_link` structurally aligned with
    `CATALYTIC_LINK_SCHEMA` so a future strict schema pass cannot
    flag the extra `_verification_notes` key.
    """
    _LEVEL_ORDER = {"verified": 2, "partially_verified": 1, "claimed": 0}

    _MECHANISM_SPEC = {
        "walkability_improvement": {
            "primary":   ["coverage_ratio_10min_walk"],
            "secondary": [],
        },
        "catchment_growth": {
            "primary":   ["reachable_population_walk"],
            "secondary": ["effective_demand_m2"],
        },
        "competition_relief": {
            "primary":   ["effective_demand_m2"],
            "secondary": [],
        },
    }

    for cand in candidates:
        sim = cand.get("simulation") or {}
        if sim.get("error"):
            continue
        brief = cand.get("simulation_brief") or {}
        per_asset = brief.get("per_asset_metrics") or {}

        notes: list = []

        for item in cand.get("plan", []):
            if item.get("role") != "catalytic":
                continue
            link = item.get("catalytic_link") or {}
            beneficiary = link.get("beneficiary_asset_id")
            if not beneficiary:
                continue

            metrics = per_asset.get(beneficiary) or {}
            if not metrics:
                # B4 produced no row for this beneficiary. Downgrade
                # the claim to "claimed" — nothing was measured.
                if link.get("verification_level") != "claimed":
                    link["verification_level"] = "claimed"
                    notes.append(
                        f"{beneficiary}: beneficiary not in simulation "
                        f"brief; downgraded to 'claimed'"
                    )
                continue

            spec = _MECHANISM_SPEC.get(link.get("mechanism"))
            if not spec:
                continue

            def _improved(key):
                delta = metrics.get(key) or {}
                before = delta.get("before")
                after = delta.get("after")
                if before is None or after is None:
                    return None
                try:
                    return float(after) > float(before)
                except (TypeError, ValueError):
                    return None

            primary = {k: _improved(k) for k in spec["primary"]}
            secondary = {k: _improved(k) for k in spec["secondary"]}

            primary_true = any(v is True for v in primary.values())
            primary_present = any(v is not None for v in primary.values())
            secondary_true = any(v is True for v in secondary.values())
            secondary_present = any(v is not None for v in secondary.values())

            # Achievable level from simulation evidence alone.
            if primary_true:
                achievable = "verified"
            elif secondary_true:
                achievable = "partially_verified"
            elif primary_present or secondary_present:
                # Metrics exist but did not improve (flat or worse).
                achievable = "claimed"
            else:
                # Metrics not exposed on this beneficiary.
                achievable = "claimed"

            declared = link.get("verification_level", "claimed")
            if _LEVEL_ORDER.get(declared, 0) > _LEVEL_ORDER.get(achievable, 0):
                link["verification_level"] = achievable
                notes.append(
                    f"{beneficiary}: simulation only supports "
                    f"'{achievable}' for mechanism "
                    f"'{link.get('mechanism')}'; downgraded from "
                    f"'{declared}'"
                )

        if notes:
            cand["_verification_notes"] = notes


def _build_catalytic_evidence(candidates):
    """
    Phase E — extract structured evidence for every catalytic claim.

    For each catalytic plan item, walks the simulation brief for the
    beneficiary and pulls the before/after for the mechanism's
    primary and secondary metric. Computes an `effect_score` that
    encodes both the direction of the effect and how well the
    simulation can verify it.

    The score is used purely as a comparison key by the selection
    stage. It is not shown to the user.

    effect_score formula:
        (primary_delta_pct * 0.6 + secondary_delta_pct * 0.4)
        * verification_weight

    verification_weight: verified = 1.0, partially_verified = 0.5,
                         claimed = 0.1

    A candidate whose catalytic claim cannot be measured (claimed)
    receives a tenth of the weight of a verified claim with the same
    delta. This is deliberate: un-measurable claims must not dominate
    the selection reasoning.
    """
    _VERIFICATION_WEIGHT = {
        "verified": 1.0,
        "partially_verified": 0.5,
        "claimed": 0.1,
    }
    _SPEC = {
        "walkability_improvement": {
            "primary":   "coverage_ratio_10min_walk",
            "secondary": None,
        },
        "catchment_growth": {
            "primary":   "reachable_population_walk",
            "secondary": "effective_demand_m2",
        },
        "competition_relief": {
            "primary":   "effective_demand_m2",
            "secondary": None,
        },
    }

    def _delta(metrics, key):
        if key is None:
            return None
        entry = (metrics or {}).get(key)
        if not entry:
            return None
        before = entry.get("before")
        after = entry.get("after")
        if before is None or after is None:
            return None
        try:
            before = float(before)
            after = float(after)
        except (TypeError, ValueError):
            return None
        pct = ((after - before) / before * 100.0) if before > 0 else None
        return {
            "metric": key,
            "before": round(before, 2),
            "after": round(after, 2),
            "delta_pct": round(pct, 2) if pct is not None else None,
        }

    for cand in candidates:
        sim = cand.get("simulation") or {}
        if sim.get("error"):
            continue
        brief = cand.get("simulation_brief") or {}
        per_asset = brief.get("per_asset_metrics") or {}

        evidence_list = []
        for item in cand.get("plan", []):
            if item.get("role") != "catalytic":
                continue
            link = item.get("catalytic_link") or {}
            beneficiary = link.get("beneficiary_asset_id")
            mechanism = link.get("mechanism")
            if not beneficiary or mechanism not in _SPEC:
                continue

            metrics = per_asset.get(beneficiary) or {}
            spec = _SPEC[mechanism]
            primary = _delta(metrics, spec["primary"])
            secondary = _delta(metrics, spec["secondary"])

            primary_pct = (
                primary["delta_pct"]
                if primary and primary.get("delta_pct") is not None
                else 0.0
            )
            secondary_pct = (
                secondary["delta_pct"]
                if secondary and secondary.get("delta_pct") is not None
                else 0.0
            )
            weight = _VERIFICATION_WEIGHT.get(
                link.get("verification_level", "claimed"), 0.1,
            )
            effect_score = round(
                (primary_pct * 0.6 + secondary_pct * 0.4) * weight, 2,
            )

            evidence_list.append({
                "acting_on": item.get("asset_id"),
                "beneficiary": beneficiary,
                "mechanism": mechanism,
                "declared_level": link.get("verification_level"),
                "primary": primary,
                "secondary": secondary,
                "effect_score": effect_score,
            })

        cand["simulation_brief"]["catalytic_evidence"] = evidence_list
        cand["catalytic_effect_total"] = round(
            sum(e["effect_score"] for e in evidence_list), 2,
        )

def _build_frontend_payload(simulation, comparison, intent, final_decision):
    """
    Transforms the raw simulation output into a multi-asset, frontend-ready JSON.
    """
    if not simulation or simulation.get("error"):
        return {"error": simulation.get("error", "Simulation failed")}

    scenario_id = simulation.get("scenario_id")
    baseline_years = simulation.get("_baseline_years", {})
    intervention_years = simulation.get("years", {})
    years_list = list(intervention_years.keys())
    final_year = years_list[-1] if years_list else "2033"

    # Collect all target assets and catalytic beneficiaries
    targets = set(comparison.get("per_asset", {}).keys())
    
    # NEW: Extract clean intervention list for map visualization
    clean_interventions = []
    for intv in simulation.get("interventions", []):
        try:
            params = json.loads(intv.get("parameters_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            params = {}
            
        role = params.get("_role", "primary")
        catalytic = params.get("_catalytic", {})
        
        # Add beneficiary to targets so it gets rendered in frontend cards
        if role == "catalytic" and catalytic.get("beneficiary_asset_id"):
            targets.add(catalytic["beneficiary_asset_id"])
            
        clean_interventions.append({
            "target_asset_id": intv.get("target_asset_id"),
            "type": intv.get("intervention_type"),
            "role": role,
            "beneficiary_asset_id": catalytic.get("beneficiary_asset_id") if role == "catalytic" else None
        })

    assets_payload = []

    for aid in targets:
        final_state = intervention_years.get(final_year, {}).get("assets", {}).get(aid, {})
        base_final_state = baseline_years.get(final_year, {}).get("assets", {}).get(aid, {})

        if not final_state or final_state.get("carbon_operational_tco2e", 0) == 0:
            for key, state in intervention_years.get(final_year, {}).get("assets", {}).items():
                if key.startswith("PRJ::") and state.get("_project_target_asset_id") == aid:
                    final_state = state
                    break

        if not final_state and not base_final_state:
            continue

        def _get(state, key, default=0.0):
            val = state.get(key)
            return float(val) if val is not None and not pd.isna(val) else default

        def _get_util(state):
            """
            Return the primary utilisation metric for this state row,
            distinguishing "missing" from "genuinely zero".

            P3-b fix — the old `or` chain treated a legitimate
            0-occupancy asset as falsy and fell through to
            utilisation_rate. That happened to produce 0 for
            residential today (utilisation_rate is None there), but
            the intent was opaque and the behaviour would change the
            moment utilisation_rate became populated for a
            residential row. Explicit None check.
            """
            occ = _get(state, "occupancy_rate", default=None)
            if occ is not None: return occ
            util = _get(state, "utilisation_rate", default=None)
            if util is not None: return util
            return 0.0

        # --- 1. Counterfactual Calculation ---
        asset_intv = next(
            (i for i in simulation.get("interventions", [])
             if i.get("target_asset_id") == aid),
            None,
        )
        avoided_embodied = (
            comparison.get("per_asset", {})
            .get(aid, {})
            .get("avoided_embodied_carbon_tco2e", {})
            .get("after", 0.0)
        )

        floor_area = (
            _get(final_state, "floor_area_m2", 0.0)
            or _get(final_state, "_effective_lettable", 0.0) / 0.85
            or _get(final_state, "_project_gfa_m2", 0.0)
        )
        capex_invested = (
            float(asset_intv.get("capex_delta_rm") or 0)
            if asset_intv else 0.0
        )

        carbon_repurpose = (
            floor_area * MATERIAL_INTENSITY_REPURPOSE
            if floor_area > 0 else 0.0
        )
        carbon_new_build = (
            carbon_repurpose + avoided_embodied
            if avoided_embodied > 0 else 0.0
        )

        _new_build_rate = _NEW_BUILD_CAPEX_RM_PER_M2.get(
            final_state.get("_effective_asset_type", "commercial"),
            _NEW_BUILD_CAPEX_RM_PER_M2["commercial"],
        )
        capex_new_build = (
            floor_area * _new_build_rate if floor_area > 0 else 0.0
        )   

        # --- 2. Subunit Breakdown ---
        subunits = []
        raw_mix = final_state.get("unit_mix_json")
        if raw_mix and isinstance(raw_mix, str):
            try:
                mix = json.loads(raw_mix)
                total_mix_area = sum(float(v.get("area_m2", 0)) for v in mix.values())
                if total_mix_area <= 0: total_mix_area = 1.0
                
                occ_by_subtype = json.loads(final_state.get("occupancy_by_subtype_calc_json", "{}"))
                base_occ_by_subtype = json.loads(base_final_state.get("occupancy_by_subtype_calc_json", "{}"))

                for st, v in mix.items():
                    area = float(v.get("area_m2", 0))
                    ratio = area / total_mix_area if total_mix_area > 0 else 0
                    
                    subunits.append({
                        "subtype": st,
                        "area_m2": area,
                        "occupancy_baseline": base_occ_by_subtype.get(st, _get_util(base_final_state)),
                        "occupancy_intervention": occ_by_subtype.get(st, _get_util(final_state)),
                        "allocated_carbon_tco2e": round(_get(final_state, "carbon_operational_tco2e") * ratio, 1),
                        "allocated_noi_rm": round(_get(final_state, "noi_rm") * ratio, 0)
                    })
            except Exception:
                pass

        # --- 3. Assemble Summary Card ---
        card = {
            "financial": {
                "main_metric": {
                    "label": "Annual NOI",
                    "baseline": _get(base_final_state, "noi_rm"),
                    "intervention": _get(final_state, "noi_rm"),
                    "unit": "RM"
                },
                "counterfactual": {
                    "capex_if_new_build_rm": round(capex_new_build),
                    "capex_if_repurpose_rm": round(capex_invested),
                    "capex_saved_rm": round(max(0, capex_new_build - capex_invested))
                }
            },
            "social": {
                "main_metric": {
                    "label": "Space Utilization",
                    "baseline": _get_util(base_final_state),
                    "intervention": _get_util(final_state),
                    "unit": "ratio"
                },
                "metrics": {
                    "coverage_ratio_15min_walk": {
                        "baseline": _get(base_final_state, "coverage_ratio_15min_walk"),
                        "intervention": _get(final_state, "coverage_ratio_15min_walk")
                    },
                    "effective_demand_m2": {
                        "baseline": _get(base_final_state, "effective_demand_m2"),
                        "intervention": _get(final_state, "effective_demand_m2")
                    }
                }
            },
            "environmental": {
                "main_metrics": [
                    {
                        "label": "Operational Carbon",
                        "baseline": _get(base_final_state, "carbon_operational_tco2e"),
                        "intervention": _get(final_state, "carbon_operational_tco2e"),
                        "unit": "tCO2e/yr"
                    },
                    {
                        "label": "Stranded Carbon",
                        "baseline": _get(base_final_state, "carbon_stranded_tco2e"),
                        "intervention": _get(final_state, "carbon_stranded_tco2e"),
                        "unit": "tCO2e/yr"
                    }
                ],
                "counterfactual": {
                    "embodied_if_new_build_tco2e": round(carbon_new_build, 1),
                    "embodied_if_repurpose_tco2e": round(carbon_repurpose, 1),
                    "net_carbon_averted_tco2e": round(avoided_embodied, 1)
                }
            },
            "subunits": subunits if subunits else None
        }

        # --- 4. Timeline Data ---
        timeline_metrics = {
            "noi_rm": {"baseline": [], "intervention": []},
            "carbon_operational_tco2e": {"baseline": [], "intervention": []},
            "carbon_stranded_tco2e": {"baseline": [], "intervention": []},
            "space_utilization": {"baseline": [], "intervention": []}
        }

        for y in years_list:
            b_asset = baseline_years.get(y, {}).get("assets", {}).get(aid, {})
            i_asset = intervention_years.get(y, {}).get("assets", {}).get(aid, {})

            timeline_metrics["noi_rm"]["baseline"].append(_get(b_asset, "noi_rm"))
            timeline_metrics["noi_rm"]["intervention"].append(_get(i_asset, "noi_rm"))
            
            timeline_metrics["carbon_operational_tco2e"]["baseline"].append(_get(b_asset, "carbon_operational_tco2e"))
            timeline_metrics["carbon_operational_tco2e"]["intervention"].append(_get(i_asset, "carbon_operational_tco2e"))
            
            timeline_metrics["carbon_stranded_tco2e"]["baseline"].append(_get(b_asset, "carbon_stranded_tco2e"))
            timeline_metrics["carbon_stranded_tco2e"]["intervention"].append(_get(i_asset, "carbon_stranded_tco2e"))
            
            timeline_metrics["space_utilization"]["baseline"].append(_get_util(b_asset))
            timeline_metrics["space_utilization"]["intervention"].append(_get_util(i_asset))

        assets_payload.append({
            "asset_id": aid,
            "summary_card": card,
            "timeline": {
                "years": years_list,
                "metrics": timeline_metrics
            }
        })

    return {
        "run_id": final_decision.get("run_id"),
        "scenario_id": scenario_id,
        "interventions": clean_interventions,
        "decision": {
            "selected_candidate": final_decision.get("selected_candidate_name"),
            "reasoning": final_decision.get("selection_reasoning", ""),
            "key_trade_offs": final_decision.get("key_trade_offs", []),
            "justification": {
                "summary": final_decision.get("executive_summary", ""),
                "why_this_plan": final_decision.get("why_this_plan", ""),
                "what_simulation_shows": final_decision.get("what_simulation_shows", ""),
                "beyond_the_model": final_decision.get("beyond_the_model"),
                "recommendation": final_decision.get("recommendation", "")
            }
        },
        "assets_analysis": assets_payload,
        "township_metrics": comparison.get("township_metrics", {})
    }

# ------------------------------------------------------------------
# Stage 2.7: selection
# ------------------------------------------------------------------


def _select_and_justify(intent, candidates, llm_client):
    import time
    prompt = _load_prompt("final_decision_writer.md")

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
            "catalytic_effect_total": c.get("catalytic_effect_total", 0.0),
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
                {"role": "user", "content": json.dumps(user_content, default=str, indent=2)},
            ],
            schema_hint=FINAL_DECISION_SCHEMA,
        )
        log.info("Stage 2.7: final decision returned in %.2fs", time.time() - t0)
    except Exception as e:
        log.warning("Final decision failed: %s", e)
        result = {}

    if not isinstance(result, dict):
        result = {}
    if not result.get("selected_candidate_name") and candidates:
        result["selected_candidate_name"] = candidates[0]["name"]
        result.setdefault("selection_reasoning", "(auto-selected first candidate)")
        result.setdefault("executive_summary", "(justification unavailable)")
    
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
        # Phase 14 — stow capacity_ratio for the DURING phase.
        # Phase 15 — stow role and catalytic_link for downstream
        # analysis. All auxiliary data travels in parameters_json so
        # the interventions.csv schema stays unchanged.
        params = dict(item.get("parameters") or {})
        if "capacity_ratio" in item and item["capacity_ratio"] is not None:
            params["_capacity_ratio"] = item["capacity_ratio"]
        if item.get("role"):
            params["_role"] = item["role"]
        if item.get("role") == "catalytic" and item.get("catalytic_link"):
            params["_catalytic"] = item["catalytic_link"]

        rows.append({
            "scenario_id": scenario_id,
            "intervention_id": f"INT-LLM-{i:03d}",
            "target_asset_id": item["asset_id"],
            "intervention_type": item["intervention_type"],
            "parameters_json": json.dumps(params),
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
        "Wrote %d interventions to %s as scenario %s",
        len(rows), path, scenario_id,
    )


def _run_simulation(scenario_id, repo_root, selected_ids=None,
                    _shared_cache=None):
    try:
        return simulate_scenario(
            scenario_id, repo_root=repo_root, selected_ids=selected_ids,
            _shared_cache=_shared_cache,
        )
    except Exception as e:
        log.exception("Simulation failed for %s", scenario_id)
        return {"error": f"{type(e).__name__}: {e}"}


def _filter_years_to_ids(years_dict: dict, keep_ids: set) -> dict:
    """
    P2-4 fix — trim the baseline `years` payload to the assets the
    frontend actually renders.

    The full SC-CURRENT `years` dict carries every township asset for
    every simulated year. Copying it verbatim into each candidate's
    scenario JSON means N_candidates × N_years × N_assets duplicate
    state. Two classes of ids are retained:

      - keep_ids  : selected targets + catalytic beneficiaries
      - PRJ::*    : project pseudo-entries, needed by the
                    new_development frontend fallback in
                    `_build_frontend_payload`

    An empty `keep_ids` returns the input unchanged (so a caller that
    passes no filter gets the full baseline, matching the pre-fix
    behaviour).
    """
    if not keep_ids:
        return years_dict

    out: dict = {}
    for year_key, year_data in years_dict.items():
        assets = year_data.get("assets", {})
        filtered = {
            aid: st
            for aid, st in assets.items()
            if aid in keep_ids or aid.startswith(PROJECT_ID_PREFIX)
        }
        out[year_key] = {**year_data, "assets": filtered}
    return out


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


def _write_orchestration_result(result: dict, repo_root: Path) -> Path:
    """Persist the full orchestration result for debugging."""
    import json as _json
    import math as _math
    from ..config import load_paths

    paths = load_paths()
    base = repo_root / paths["base"]
    out_dir = base / "business" / "llm_runs"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Safely resolve run_id even if nested
    run_id = (
        result.get("run_id") 
        or result.get("frontend", {}).get("run_id") 
        or "unknown"
    )
    out = out_dir / f"{run_id}.json"

    def _sanitize(obj):
        if isinstance(obj, dict):
            return {k: _sanitize(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_sanitize(v) for v in obj]
        if isinstance(obj, float) and _math.isnan(obj):
            return None
        return obj

    with open(out, "w", encoding="utf-8") as f:
        _json.dump(_sanitize(result), f, indent=2, default=str)
    log.info("Wrote orchestration result to %s", out)
    return out