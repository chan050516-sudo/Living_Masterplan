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

    The stub is aware of the multi-asset demo: it produces a two-asset
    plan (B-03 -> clinic, F-02 -> retrofit) and exercises the per-asset
    comparison path.
    """

    model = "stub-v1"

    def chat_with_tools(self, messages, tools):
        # First turn: call a couple of read tools for each asset.
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
                    {"id": "t3", "name": "get_deadspace_status",
                     "arguments": {"asset_id": "F-02"}},
                    {"id": "t4", "name": "get_nearby_assets",
                     "arguments": {"asset_id": "B-03", "radius_m": 800}},
                ],
            }
        return {"content": "I have enough context.", "tool_calls": []}

    def chat_json(self, messages, schema_hint):
        # Intent stage
        if "target_asset_ids" in schema_hint:
            return {
                "target_asset_ids": ["B-03", "F-02"],
                "objective": "balanced",
                "constraints": {"capex_limit": 3000000},
                "question_text": (
                    "What should we do with B-03 and F-02? "
                    "Budget is RM 3 million."
                ),
            }
        # Proposal stage
        if "plan" in schema_hint:
            return {
                "reasoning_trace": (
                    "B-03 has been vacant for 14 months with an extremely "
                    "low DSR. The catchment is dominated by working-age "
                    "residents but has a meaningful elderly minority. "
                    "Nearby there is one community hall already "
                    "underutilised (F-02 at 22%). Repurposing B-03 into a "
                    "clinic fills a genuine gap that the catchment "
                    "supports. F-02 does not benefit from a change of "
                    "use; its problem is operational, not structural, so "
                    "a retrofit that cuts energy cost and refreshes the "
                    "space is the right lever."
                ),
                "plan": [
                    {
                        "asset_id": "B-03",
                        "type": "repurpose",
                        "parameters": {
                            "to_subtype": "clinic",
                            "new_capacity": 200,
                        },
                        "expected_effects": {"utilisation": 0.72},
                        "rationale": (
                            "Retail demand is saturated. A clinic serves "
                            "the elderly catchment and avoids duplicating "
                            "the existing community hall."
                        ),
                    },
                    {
                        "asset_id": "F-02",
                        "type": "retrofit",
                        "parameters": {},
                        "expected_effects": {"utilisation": 0.30},
                        "rationale": (
                            "F-02's issue is operational, not structural. "
                            "Retrofit improves the space and reduces "
                            "energy cost without changing land use."
                        ),
                    },
                ],
            }
        # Justification stage
        return {
            "summary": (
                "B-03 is repurposed to a clinic, cutting its carbon by "
                "about 92% and improving elderly catchment coverage. "
                "F-02 is retrofitted to improve operating efficiency. "
                "Combined, township carbon falls and service coverage "
                "improves."
            ),
            "why_this_plan": (
                "B-03's retail demand is saturated; the catchment skews "
                "older and lacks a nearby clinic. F-02 is structurally "
                "fine but operationally weak, so it needs a retrofit "
                "rather than a change of use."
            ),
            "what_simulation_shows": (
                "See the simulation brief for exact per-asset figures. "
                "The key numbers to read: B-03's carbon and utilisation "
                "shift; F-02's utilisation remains low but its carbon "
                "declines modestly."
            ),
            "beyond_the_model": None,
            "recommendation": (
                "Proceed if social return is prioritised over near-term "
                "cash flow."
            ),
        }


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------


def main():
    repo_root = Path(__file__).resolve().parents[2]

    print("\n" + "=" * 72)
    print("  B7 — LLM Reasoning Layer Demo (multi-asset batch)")
    print("=" * 72)

    client = StubLLMClient()

    result = orchestrate_and_simulate_batch(
        user_query=(
            "What should we do with B-03 and F-02? "
            "Budget is RM 3 million."
        ),
        selected_asset_ids=["B-03", "F-02"],
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