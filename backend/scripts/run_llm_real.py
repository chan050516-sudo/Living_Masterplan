"""Run the LLM reasoning layer against real Vertex AI Gemini.

Requires:
  - google-genai installed
  - gcloud auth application-default login
  - GOOGLE_CLOUD_PROJECT env var set
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.orchestrator import orchestrate_and_simulate_batch
from app.llm.tool_service import TownshipDataSource
from app.llm.clients.vertex_client import VertexGeminiClient


def main():
    repo_root = Path(__file__).resolve().parents[2]
    ds = TownshipDataSource(repo_root, year=2026)

    candidates = [
        aid for aid, r in ds.deadspace.items()
        if r.get("status") == "deadspace_candidate"
    ]
    selected = candidates[:2]
    print(f"Selected: {selected}\n")

    client = VertexGeminiClient(
        thinking_level="MEDIUM",
        temperature=0.2,
    )
    print(f"Model: {client.model}\n")

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

    import json
    print("\n" + "=" * 72)
    print("RESULT")
    print("=" * 72)
    print(json.dumps({
        "run_id": result.get("run_id"),
        "scenario_id": result.get("scenario_id"),
        "intent": result.get("intent"),
        "proposal_plan": result.get("proposal", {}).get("plan"),
        "validation": result.get("validation"),
        "justification": result.get("justification"),
    }, indent=2, default=str))


if __name__ == "__main__":
    main()