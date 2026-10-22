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


def _print_results(result, mock_file_path):
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
    
    print("\n--- 3. Asset Summary Cards (From Simulation) ---")
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

    print("\n" + "="*80)
    print(f"✅ MOCK DATA EXPORTED to: {mock_file_path}")
    print("   You can directly copy the contents of this file into your frontend 'mockData.ts'")
    print("="*80 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Golden Demo Scenarios")
    parser.add_argument("--scenario", type=int, choices=[1, 2, 3], required=True,
                        help="1: Subunit Repurpose, 2: Catalytic Link, 3: Expert Reasoning")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    ds = TownshipDataSource(repo_root, year=2026)
    client = VertexGeminiClient(thinking_level="MEDIUM", temperature=0.2)

    target_ids = []
    query = ""
    title = ""

    if args.scenario == 1:
        title = "Scenario 1: Precision Medicine (Subunit Repurpose w/ PDF Context)"
        
        # 1. Dynamically find a mixed-use asset with dead subtypes
        mixed_assets = []
        for aid in ds.deadspace.keys():
            _a = ds._asset_row(aid) or {}
            if _a.get("asset_type") != "commercial":
                continue
            _mix_raw = _a.get("unit_mix_json")
            if _mix_raw is None:
                continue
            try:
                _mix = json.loads(_mix_raw) if isinstance(_mix_raw, str) else _mix_raw
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(_mix, dict) or len(_mix) < 2:
                continue

            _m = ds._metric_row(aid, ds.year) or {}
            _occ_by_raw = _m.get("occupancy_by_subtype_calc_json")
            if not _occ_by_raw:
                continue
            try:
                _occ_by = json.loads(_occ_by_raw) if isinstance(_occ_by_raw, str) else _occ_by_raw
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(_occ_by, dict):
                continue
            if any(float(v) < 0.30 for v in _occ_by.values() if v is not None):
                mixed_assets.append(aid)

        target_ids = [mixed_assets[0]] if mixed_assets else ["BLD-0183"]

        # 2. The "Attached PDF" content (Mocked as text for now)
        pdf_content = """
[CONFIDENTIAL] ASSET FEASIBILITY & CONSTRAINTS SUMMARY
Project: BLD-0183 Commercial Block (Bukit Jelutong)
Date: October 2026
Prepared By: Urban Planning & Asset Management Team

1.0 Executive Summary
The asset currently suffers from a significant internal performance divergence. While gross aggregate footfall remains acceptable, the internal tenancy mix exhibits severe spatial inefficiencies. This document outlines the non-negotiable constraints for any proposed intervention in the upcoming fiscal year.

2.0 Financial Constraints
- Capex Envelope: The board has approved a maximum capital expenditure of RM 2,000,000 for the 2027 fiscal year. Any proposal exceeding this requires tier-1 board approval, causing a 6-month delay.
- Payback Period: Interventions must demonstrate a projected net operating income (NOI) stabilization or improvement within 36 months of commissioning.
- Holding Costs: Current emergency maintenance and security overheads for vacant bays are bleeding RM 45,000/month.

3.0 Operational & Legal Constraints
- Continuous Operation Mandate: The property must remain 100% operational during any works. Full building closures or temporary asset shutdowns are strictly prohibited due to existing contractual obligations.
- Anchor Tenant Protection: The primary supermarket anchor (Area: 1,400 m²) holds a non-disruption clause in its lease, running until Q4 2031. Any works generating heavy structural vibration, dust, or utility interruptions to the anchor's zone will trigger immediate lease default penalties.
- Authority & Ownership: The asset is fully owned by Sime Darby Property (Full Control). However, local municipal (MBSJ) zoning regulations restrict any change of land use that alters the primary commercial classification.

4.0 Physical & Structural Constraints
- Structural Integrity: A recent structural audit (2026) mandates that the existing reinforced concrete (RC) frame and load-bearing shear walls must be retained.
- Demolition Restriction: Total or partial structural demolition is not permitted. The carbon footprint of new structural materials violates the group's 2025 ESG mandate.
- MEP Limitations: The existing main electrical substation is operating near 85% capacity. Heavy medical or industrial-grade equipment requiring massive MEP upgrades cannot be accommodated without a separate RM 1.5M infrastructure grant, which is currently unavailable.

5.0 Market & Demand Context
- Internal Spatial Anomaly: The aggregate occupancy is misleading. The ground-floor F&B and retail zones are experiencing prolonged vacancy (>18 months), while upper-floor services and the anchor tenant maintain strong utilization.
- Catchment Reality: Walking catchment within 10 minutes is limited (approx. 12,000 residents), but the surrounding demographic is skewing towards an aging population and young working families.
        """

        # 3. The simple user query mimicking an executive's instruction
        raw_query = (
            f"Review the attached feasibility summary for {target_ids[0]}. "
            "We need to stop the financial bleeding immediately. "
            "Generate the best intervention plan that complies strictly with all the constraints."
        )

        # 4. Simulate the frontend augmentation (appending PDF text)
        query = (
            f"{raw_query}\n\n"
            f"--- ATTACHED DOCUMENTS ---\n"
            f"[Attached PDF Document: BLD-0183_Feasibility_Summary.pdf]\n"
            f"{pdf_content}"
        )

    elif args.scenario == 2:
        title = "Scenario 2: The Catalyst (Spatial Synergy)"
        comm_targets = [aid for aid, r in ds.deadspace.items() if aid.startswith("BLD") and r.get("status") == "deadspace_candidate"]
        vacants = ds.assets[ds.assets["asset_type"] == "undeveloped_parcel"]["asset_id"].tolist()
        
        if comm_targets and vacants:
            target_ids = [comm_targets[0], vacants[0]]
        else:
            target_ids = ["BLD-0193", "P-VAC-01"]
            
        query = (
            f"{target_ids[0]} is suffering from low footfall and a thin catchment. "
            f"Nearby, we have an empty parcel {target_ids[1]}. We have a budget of RM 8M. "
            f"We want to rescue {target_ids[0]}. Think outside the box: can we use the empty parcel "
            f"to inject new residents or a complementary anchor that boosts the demand for {target_ids[0]}? "
            f"Propose a catalytic intervention on the parcel that benefits the commercial asset."
        )

    elif args.scenario == 3:
        title = "Scenario 3: The Master Planner (Trajectory & Lease Awareness)"
        res_pool, comm_pool = [], []
        for aid, r in ds.deadspace.items():
            if r.get("status") != "deadspace_candidate":
                continue
            _a = ds._asset_row(aid) or {}
            atype = _a.get("asset_type")
            if atype == "residential":
                res_pool.append(aid)
            elif atype == "commercial":
                comm_pool.append(aid)

        res_ids = res_pool[:1]
        comm_ids = comm_pool[:1]

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
    print(f"Query:    {query[:150]}... (truncated for console)\n")

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

    frontend_dir = repo_root / "frontend" / "src"
    mock_file = frontend_dir / f"mock_scenario_{args.scenario}.json"
    
    if frontend_dir.exists():
        with open(mock_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        _print_results(result, mock_file)
    else:
        fallback_file = repo_root / f"mock_scenario_{args.scenario}.json"
        with open(fallback_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        _print_results(result, fallback_file)


if __name__ == "__main__":
    main()