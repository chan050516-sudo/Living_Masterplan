"""Run the B7 LLM reasoning layer against a fake or real LLM client.

Usage:
    python backend/scripts/run_llm_demo.py

By default, uses a stub client that returns canned responses. Replace
with a real client (OpenAI, Anthropic, Vertex AI Gemini) to actually
reason.

To wire a real client, implement the two methods:
    chat_with_tools(messages, tools) -> {"content": str|None, "tool_calls": list|None}
    chat_json(messages, schema_hint) -> dict
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.orchestrator import orchestrate_and_simulate_batch


# ------------------------------------------------------------------
# Stub LLM client — canned responses for demo / testing.
# Replace with a real client.
# ------------------------------------------------------------------


class StubLLMClient:
    """
    A deterministic stub. It exercises every code path without needing
    an external API key. Replace the methods with real LLM calls.

    Pass `target_asset_ids` at construction time to test against any
    set of real asset IDs.
    """

    model = "stub-v1"

    def __init__(self, target_asset_ids=None):
        self.target_asset_ids = target_asset_ids or ["B-03", "F-02"]

    def chat_with_tools(self, messages, tools):
        already = sum(1 for m in messages if m.get("role") == "tool")
        if already == 0:
            aid_a = self.target_asset_ids[0]
            aid_b = (self.target_asset_ids[1]
                     if len(self.target_asset_ids) > 1
                     else self.target_asset_ids[0])
            return {
                "content": None,
                "tool_calls": [
                    {"id": "t1", "name": "get_asset_evidence",
                     "arguments": {"asset_id": aid_a}},
                    {"id": "t2", "name": "get_catchment_profile",
                     "arguments": {"asset_id": aid_a, "mode": "walk"}},
                    {"id": "t3", "name": "get_deadspace_status",
                     "arguments": {"asset_id": aid_b}},
                    {"id": "t4", "name": "get_nearby_assets",
                     "arguments": {"asset_id": aid_a, "radius_m": 800}},
                ],
            }
        return {"content": "I have enough context.", "tool_calls": []}

    def chat_json(self, messages, schema_hint):
        # Intent stage
        if "target_asset_ids" in schema_hint:
            return {
                "target_asset_ids": self.target_asset_ids,
                "objective": "balanced",
                "constraints": {"capex_limit": 3_000_000},
                "question_text": (
                    "What should we do with these assets? "
                    "Budget is RM 3 million."
                ),
            }
        # Proposal stage
        if "plan" in schema_hint:
            plan = []
            for aid in self.target_asset_ids:
                row = None
                # crude lookup — the stub only needs the asset_type
                # to pick a legal intervention type
                plan.append({
                    "asset_id": aid,
                    "type": "repurpose",
                    "parameters": {
                        "to_subtype": "clinic",
                        "new_capacity": 200,
                    },
                    "expected_effects": {"utilisation": 0.72},
                    "rationale": (
                        "Repurpose to a clinic to eliminate stranded "
                        "carbon and serve the senior catchment."
                    ),
                })
            return {
                "reasoning_trace": (
                    "Target assets show high stranded carbon and low "
                    "utilisation. Repurpose to community facilities "
                    "eliminates the waste and serves the population."
                ),
                "plan": plan,
            }


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------


def main():
    repo_root = Path(__file__).resolve().parents[2]

    print("\n" + "=" * 72)
    print("  B7 — LLM Reasoning Layer Demo (multi-asset batch)")
    print("=" * 72)

    # Pick real assets from the current township data.
    from app.llm.tool_service import TownshipDataSource
    ds = TownshipDataSource(repo_root, year=2026)
    candidates = [
        aid for aid, r in ds.deadspace.items()
        if r.get("status") == "deadspace_candidate"
    ]
    if not candidates:
        print("No deadspace_candidate assets found")
        return
    selected = candidates[:2]
    print(f"Selected assets for the demo: {selected}\n")

    client = StubLLMClient(target_asset_ids=selected)

    result = orchestrate_and_simulate_batch(
        user_query=(
            f"What should we do with {', '.join(selected)}? "
            f"Budget is RM 3 million."
        ),
        selected_asset_ids=selected,
        llm_client=client,
        repo_root=repo_root,
        base_year=2026,
    )

    print("\n--- Intent ---")
    print(json.dumps(result["intent"], indent=2, default=str))

    print("\n--- Context (tool calls made) ---")
    for c in result["context"].get("tool_calls", []):
        print(f"  {c['name']}({c['arguments']}) -> {c['result_summary']}")

    print("\n--- Proposal ---")
    print(f"  reasoning_trace: {result['proposal'].get('reasoning_trace', '')[:200]}...")
    for item in result["proposal"].get("plan", []):
        print(f"  {item.get('asset_id')} -> {item.get('type')} "
              f"({item.get('parameters', {}).get('to_subtype', '')})")

    print("\n--- Validation ---")
    v = result["validation"]
    print(f"  valid: {v['valid']}")
    for e in v["errors"]:
        print(f"  ERROR: {e}")
    for w in v["warnings"]:
        print(f"  WARN:  {w}")

    print("\n--- Simulation (brief) ---")
    sim = result.get("simulation") or {}
    if sim.get("error"):
        print(f"  ERROR: {sim['error']}")
    else:
        brief = result.get("simulation_brief") or {}
        print(f"  scenario_id: {result.get('scenario_id')}")
        agg = brief.get("aggregate", {})
        print(f"  asset_count: {agg.get('asset_count')}")
        print(f"  carbon_delta_pct: {agg.get('carbon_delta_pct')}")

        per_asset = brief.get("per_asset_metrics", {})
        for aid, metrics in per_asset.items():
            print(f"\n  {aid}:")
            for key, val in metrics.items():
                b = val.get("before")
                a = val.get("after")
                unit = val.get("unit", "")
                print(f"    {key:<32} {b!s:>12}  ->  {a!s:<12} {unit}")

        township = brief.get("township_metrics", {})
        if township:
            print(f"\n  Township:")
            print(f"    total_carbon_before_tco2e: {township.get('total_carbon_before_tco2e')}")
            print(f"    total_carbon_after_tco2e:  {township.get('total_carbon_after_tco2e')}")
            print(f"    carbon_delta_pct:          {township.get('carbon_delta_pct')}")

    print("\n--- Justification ---")
    j = result.get("justification") or {}
    for k in ("summary", "why_this_plan", "what_simulation_shows",
              "beyond_the_model", "recommendation"):
        if j.get(k):
            print(f"\n  {k}:")
            print(f"    {j[k]}")

    print("\n" + "=" * 72 + "\n")


if __name__ == "__main__":
    main()