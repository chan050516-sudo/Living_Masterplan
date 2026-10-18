"""Golden Demo script for the LLM reasoning layer.

Three distinct scenarios to showcase:
  1. Subunit Repurpose (partial conversion)
  2. Catalytic Intervention (spatial synergy)
  3. Expert Reasoning (long-term trajectory & lease constraints)

Usage:
    python backend/scripts/run_llm_real2.py --scenario 1
    python backend/scripts/run_llm_real2.py --scenario 2
    python backend/scripts/run_llm_real2.py --scenario 3
"""
import argparse
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


def _print_header(title):
    print(f"\n{'=' * 80}")
    print(f" 🚀 {title}")
    print(f"{'=' * 80}\n")


def _print_results(result):
    print(f"PIPELINE COMPLETE.\n")
    
    decision = result.get("decision", {})
    
    print("--- 1. LLM Strategic Reasoning (Internal) ---")
    print(decision.get("reasoning", "(none)"))
    
    print("\n--- 2. Candidates Summary ---")
    for c in result.get("candidates_summary", []):
        plan_summary = ", ".join([f"{i.get('asset_id')}({i.get('type')})" for i in c.get("plan", [])])
        is_winner = c["name"] == decision.get("selected_candidate")
        tag = " 👑 [WINNER]" if is_winner else ""
        print(f"  [{c['name']}]{tag} -> {plan_summary}")
    
    print("\n--- 3. Asset Summary Cards ---")
    for asset in result.get("assets_analysis", []):
        aid = asset["asset_id"]
        card = asset["summary_card"]
        
        print(f"  Asset: {aid}")
        
        # Financial
        fin = card["financial"]
        print(f"    NOI (Annual): RM {fin['main_metric']['baseline']} -> RM {fin['main_metric']['intervention']}")
        print(f"    Counterfactual CAPEX Saved: RM {fin['counterfactual']['capex_saved_rm']}")
        
        # Social
        soc = card["social"]
        util = soc["main_metric"]
        print(f"    Space Utilization: {util['baseline']*100:.1f}% -> {util['intervention']*100:.1f}%")
        
        # Environmental
        env = card["environmental"]
        op_carbon = env["main_metrics"][0]
        print(f"    Operational Carbon: {op_carbon['baseline']} -> {op_carbon['intervention']} tCO2e/yr")
        print(f"    Carbon Averted: {env['counterfactual']['net_carbon_averted_tco2e']} tCO2e")
        
        # Subunits
        if card.get("subunits"):
            print(f"    [!! SUBUNITS !!] {len(card['subunits'])} specific retail zones detailed.")
            for sub in card['subunits']:
                print(f"      - {sub['subtype']} ({sub['area_m2']}m2): Occ {sub['occupancy_baseline']*100:.0f}% -> {sub['occupancy_intervention']*100:.0f}%")

    print("\n--- 4. Executive Justification ---")
    j = decision.get("justification") or {}
    for k in ("summary", "why_this_plan", "what_simulation_shows", "beyond_the_model", "recommendation"):
        if j.get(k):
            print(f"\n  [{k}]")
            print(f"  {j[k]}")
            

def main():
    parser = argparse.ArgumentParser(description="Golden Demo Scenarios")
    parser.add_argument("--scenario", type=int, choices=[1, 2, 3], required=True,
                        help="1: Subunit Repurpose, 2: Catalytic Link, 3: Expert Reasoning")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    ds = TownshipDataSource(repo_root, year=2026)
    client = VertexGeminiClient(thinking_level="MEDIUM", temperature=0.2)

    # Default fallbacks if dynamic discovery fails
    target_ids = []
    query = ""
    title = ""

    if args.scenario == 1:
        # SCENARIO 1: Subunit Repurpose
        # Find a mixed-use asset with dead subtypes, but don't force the model to fully repurpose it.
        title = "Scenario 1: Precision Medicine (Subunit Repurpose)"
        
        # Find an asset with a subtype_mix
        mixed_assets = [aid for aid, r in ds.deadspace.items() if r.get("subtype_mix") and r.get("status") in ["deadspace_candidate", "monitor"]]
        if mixed_assets:
            target_ids = [mixed_assets[0]]
        else:
            target_ids = ["BLD-0183"] # fallback
            
        query = (
            f"We are looking at {target_ids[0]}. The aggregate occupancy might look okay, "
            f"but the subtype mix tells a different story. Some retail units are completely dead, "
            f"while the anchor tenants are thriving. We have a budget of RM 2M. "
            f"Do NOT demolish or fully close the asset. Propose a surgical intervention that "
            f"converts only the dead space into something high-demand, while preserving the healthy tenants. "
            f"Avoid the 18-month closure penalty of a full repurpose."
        )

    elif args.scenario == 2:
        # SCENARIO 2: Catalytic Intervention
        # Find a struggling asset that is near an undeveloped parcel
        title = "Scenario 2: The Catalyst (Spatial Synergy)"
        
        # Find a commercial target and an undeveloped parcel nearby
        comm_targets = [aid for aid, r in ds.deadspace.items() if aid.startswith("BLD") and r.get("status") == "deadspace_candidate"]
        vacants = ds.assets[ds.assets["asset_type"] == "undeveloped_parcel"]["asset_id"].tolist()
        
        if comm_targets and vacants:
            target_ids = [comm_targets[0], vacants[0]]
        else:
            target_ids = ["BLD-0193", "P-VAC-01"] # fallback
            
        query = (
            f"{target_ids[0]} is suffering from low footfall and a thin catchment. "
            f"Nearby, we have an empty parcel {target_ids[1]}. We have a budget of RM 8M. "
            f"We want to rescue {target_ids[0]}. Think outside the box: can we use the empty parcel "
            f"to inject new residents or a complementary anchor that boosts the demand for {target_ids[0]}? "
            f"Propose a catalytic intervention on the parcel that benefits the commercial asset."
        )

    elif args.scenario == 3:
        # SCENARIO 3: Expert Reasoning
        # Give it two assets: a residential with lease constraints, and a commercial with demographic mismatch.
        title = "Scenario 3: The Master Planner (Trajectory & Lease Awareness)"
        
        # We need a residential asset and a commercial asset
        res_ids = [aid for aid, r in ds.deadspace.items() if aid.startswith("BLD-0") and r.get("status") == "deadspace_candidate"][:1]
        comm_ids = [aid for aid, r in ds.deadspace.items() if aid.startswith("BLD-0") and r.get("status") == "deadspace_candidate" and aid not in res_ids][:1]
        
        if res_ids and comm_ids:
            target_ids = [comm_ids[0], res_ids[0]]
        else:
            target_ids = ["BLD-0183", "BLD-0151"]
            
        query = (
            f"We have RM 4M for a multi-year strategy for {target_ids[0]} and {target_ids[1]}. "
            f"The township demographic is aging, but we also have a lot of young families. "
            f"Look closely at the lease schedules, the anchor tenants, and the 5-year trajectories. "
            f"If an anchor tenant is locked in for 5 more years, a heavy structural change right now is foolish. "
            f"Propose a phased strategy: maybe a retrofit now, a catalytic green corridor to link the assets, "
            f"and a structural pivot later when the lease expires. Show me you understand time, leases, and demographics."
        )

    print(f"Start:    {time.strftime('%H:%M:%S')}")
    print(f"Model:    {client.model}")
    print(f"Targets:  {target_ids}")
    print(f"Query:    {query}\n")

    _print_header(title)

    t0 = time.time()
    result = orchestrate_and_simulate_batch(
        user_query=query,
        selected_asset_ids=target_ids,
        llm_client=client,
        repo_root=repo_root,
        base_year=2026,
    )
    elapsed = time.time() - t0

    print(f"\nPIPELINE FINISHED in {elapsed:.1f}s")
    _print_results(result)

if __name__ == "__main__":
    main()