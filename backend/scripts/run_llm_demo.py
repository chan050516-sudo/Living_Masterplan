"""Run the B7 LLM reasoning layer against a fake or real LLM client.

Usage:
    python backend/scripts/run_llm_demo.py

By default, uses a stub client that returns canned responses. Replace
with a real client (OpenAI, Anthropic, local) to actually reason.

To wire a real client, implement the two methods:
    chat_with_tools(messages, tools) -> {"content": str|None, "tool_calls": list|None}
    chat_json(messages, schema_hint) -> dict
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.orchestrator import orchestrate


# ------------------------------------------------------------------
# Stub LLM client — canned responses for demo / testing.
# Replace with a real client.
# ------------------------------------------------------------------


class StubLLMClient:
    """
    A deterministic stub. It exercises every code path without needing
    an external API key. Replace the methods with real LLM calls.
    """

    model = "stub-v1"

    def chat_with_tools(self, messages, tools):
        # First turn: call two read tools.
        # Second turn: return no tool calls, signalling completion.
        already = sum(1 for m in messages if m.get("role") == "tool")
        if already == 0:
            return {
                "content": None,
                "tool_calls": [
                    {"id": "t1", "name": "get_asset_evidence",
                     "arguments": {"asset_id": "B-03"}},
                    {"id": "t2", "name": "get_catchment_profile",
                     "arguments": {"asset_id": "B-03", "mode": "walk"}},
                ],
            }
        return {"content": "I have enough context.", "tool_calls": []}

    def chat_json(self, messages, schema_hint):
        # Detect the stage by the schema we were asked for.
        if "target_asset_ids" in schema_hint:
            return {
                "target_asset_ids": ["B-03"],
                "objective": "balanced",
                "constraints": {"capex_limit": 2000000},
                "question_text": "What should we do with B-03?",
            }
        if "plan" in schema_hint:
            return {
                "reasoning_trace": (
                    "B-03 has been vacant for 14 months with an "
                    "extremely low DSR. The catchment is dominated "
                    "by working-age residents. Nearby there is one "
                    "community hall already underutilised. A clinic "
                    "fills a genuine gap."
                ),
                "plan": [{
                    "asset_id": "B-03",
                    "type": "repurpose",
                    "parameters": {"to_subtype": "clinic", "new_capacity": 200},
                    "expected_effects": {"utilisation": 0.72},
                    "rationale": "Retail demand is saturated. A clinic serves the elderly catchment and avoids duplicating the existing community hall.",
                }],
            }
        # Justification stage
        return {
            "summary": "B-03 is repurposed to a clinic, reducing carbon by 92% and improving elderly catchment coverage.",
            "why_this_plan": "Retail demand is saturated. The catchment skews older and lacks a nearby clinic.",
            "what_simulation_shows": "See the simulation brief for exact numbers.",
            "beyond_the_model": None,
            "recommendation": "Proceed if social return is prioritised.",
        }


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------


def main():
    repo_root = Path(__file__).resolve().parents[2]

    print("\n" + "=" * 72)
    print("  B7 — LLM Reasoning Layer Demo")
    print("=" * 72)

    client = StubLLMClient()

    result = orchestrate(
        user_query="What should we do with B-03? Budget is RM 2 million.",
        selected_asset_ids=["B-03"],
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
    comp = sim.get("comparison", {})
    township = comp.get("township_metrics", {}) if isinstance(comp, dict) else {}
    print(f"  scenario_id: {result.get('scenario_id')}")
    print(f"  carbon_delta_pct: {township.get('carbon_delta_pct')}")

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