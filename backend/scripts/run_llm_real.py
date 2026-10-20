"""Run the LLM reasoning layer against real Vertex AI Gemini.

Phase 13 architecture: multi-candidate pipeline, 4 LLM calls
(Stage 0, 2, 2.7, 4) plus N parallel B4 simulations.

Requires:
  - google-genai installed
  - gcloud auth application-default login
  - GOOGLE_CLOUD_PROJECT env var set
"""
import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.orchestrator import orchestrate_and_simulate_batch
from app.llm.tool_service import TownshipDataSource
from app.llm.vertex_client import VertexGeminiClient


def _print_candidate_summary(cand):
    brief = cand.get("simulation_brief") or {}
    agg = brief.get("aggregate") or {}
    tm = brief.get("township_metrics") or {}
    print(f"\n  [{cand.get('name', '?')}]")
    print(f"    strategy: {cand.get('strategy_summary', '')[:120]}")
    for item in cand.get("plan", []):
        print(f"      {item.get('asset_id')} -> {item.get('type')}")
    print(f"    carbon_delta_pct:        {agg.get('carbon_delta_pct')}")
    print(f"    avoided_embodied_carbon: {agg.get('avoided_embodied_carbon_tco2e')}")
    print(f"    township_carbon_after:   {tm.get('total_carbon_after_tco2e')}")


def main():
    repo_root = Path(__file__).resolve().parents[2]
    ds = TownshipDataSource(repo_root, year=2026)

    candidates = [
        aid for aid, r in ds.deadspace.items()
        if r.get("status") == "deadspace_candidate"
    ]
    selected = candidates[:2]
    print(f"Selected: {selected}")
    print(f"Start:    {time.strftime('%H:%M:%S')}\n")

    client = VertexGeminiClient(
        thinking_level="MEDIUM",
        temperature=0.2,
    )
    print(f"Model:    {client.model}")
    print(f"Thinking: {client.thinking_level}\n")

    t0 = time.time()
    result = orchestrate_and_simulate_batch(
        user_query=(
            f"What should we do with {', '.join(selected)}? "
            f"We have RM 3 million and cannot demolish any structure."
        ),
        selected_asset_ids=selected,
        llm_client=client,
        repo_root=repo_root,
        base_year=2026,
    )
    elapsed = time.time() - t0

    print(f"\n{'=' * 72}")
    print(f"  PIPELINE COMPLETE in {elapsed:.1f}s")
    print(f"{'=' * 72}\n")

    print("--- Intent ---")
    print(json.dumps(result.get("intent"), indent=2, default=str))

    print("\n--- Context summary ---")
    print(json.dumps(result.get("context"), indent=2, default=str))

    print(f"\n--- Candidates ({result.get('meta', {}).get('candidate_count')}) ---")
    for cand in result.get("candidates", []):
        _print_candidate_summary(cand)

    print("\n--- Selection ---")
    sel = result.get("selection") or {}
    print(f"  selected:  {sel.get('selected_candidate_name')}")
    print(f"  reasoning: {sel.get('selection_reasoning', '')[:400]}")
    for tf in sel.get("key_trade_offs", []):
        print(f"  trade-off: {tf}")

    print("\n--- Validation (selected) ---")
    v = result.get("validation") or {}
    print(f"  valid:    {v.get('valid')}")
    print(f"  attempts: {result.get('meta', {}).get('attempts')}")
    for e in v.get("errors", []):
        print(f"  ERROR: {e}")
    for w in v.get("warnings", []):
        print(f"  WARN:  {w}")

    print("\n--- Selected plan ---")
    for item in (result.get("proposal") or {}).get("plan", []):
        print(f"  {item.get('asset_id')} -> {item.get('type')}")
        print(f"    params: {json.dumps(item.get('parameters'), default=str)[:200]}")
        ic = item.get("investment_case") or {}
        if ic:
            print(f"    invest: {ic.get('capital_invested', '')[:100]}")
            print(f"    return: {ic.get('return_delivered', '')[:100]}")

    print("\n--- Simulation (selected) ---")
    sim = result.get("simulation") or {}
    if sim.get("error"):
        print(f"  ERROR: {sim['error']}")
    else:
        brief = result.get("simulation_brief") or {}
        agg = brief.get("aggregate", {})
        tm = brief.get("township_metrics", {})
        print(f"  scenario_id:             {result.get('scenario_id')}")
        print(f"  carbon_delta_pct:        {agg.get('carbon_delta_pct')}")
        print(f"  avoided_embodied_carbon: {agg.get('avoided_embodied_carbon_tco2e')}")
        print(f"  township_carbon_after:   {tm.get('total_carbon_after_tco2e')}")

    print("\n--- Justification ---")
    j = result.get("justification") or {}
    for k in ("summary", "why_this_plan", "what_simulation_shows",
              "beyond_the_model", "recommendation"):
        val = j.get(k)
        if val:
            print(f"\n  {k}:")
            print(f"    {val}")

    print(f"\n{'=' * 72}\n")


if __name__ == "__main__":
    main()