import type { AnalyzeResult } from './types'

export const MOCK_ANALYZE_RESULT: AnalyzeResult = {
  run_id: "LLM-mock-1234",
  scenario_id: "SC-LLM-mock-1234-C1",
  decision: {
    selected_candidate: "Surgical Subtype Repurpose",
    reasoning: "Surgical Subtype Repurpose wins because it successfully activates dead space where renovation fails. It increases asset occupancy from 0.0% to 13.3% and expands effective demand from 269.8 m² to 856.1 m², compared to only 331.4 m² under Targeted Commercial Renovation.",
    key_trade_offs: [
      "Sacrifices RM 200k of near-term cash flow to eliminate 800 tCO2e/yr of stranded carbon.",
      "Requires 6 months of partial closure for the targeted floors, whereas a full retrofit could be done without shutting down tenants."
    ],
    justification: {
      summary: "We recommend the Surgical Subtype Repurpose for BLD-0193 under the RM 2M allocation.",
      why_this_plan: "The user mandate requires eliminating dead space without shutting down thriving anchors. Targeted Commercial Renovation was rejected because commercial refurbishment fails to alter demand fundamentals.",
      what_simulation_shows: "At the asset level, the simulation confirms occupancy rises from 0.0% to 13.3%, supported by an effective demand surge from 269.8 m² to 856.1 m². Asset operational carbon drops 7.14% from 676.8 to 628.4 tCO2e.",
      beyond_the_model: "Phased surgical partitioning contains construction dust and noise, preventing lease-default claims from operating anchors.",
      recommendation: "Proceed immediately with architectural partitioning and tenant pre-leasing, provided tenant commitments cover at least 600 m² of converted space before executing fit-out contracts."
    }
  },
  assets_analysis: [
    {
      asset_id: "BLD-0193",
      summary_card: {
        financial: {
          main_metric: { label: "Annual NOI", baseline: -1383363, intervention: -1383363, unit: "RM" },
          counterfactual: { capex_if_new_build_rm: 10843520, capex_if_repurpose_rm: 2000000, capex_saved_rm: 8843520 }
        },
        social: {
          main_metric: { label: "Space Utilization", baseline: 0.0, intervention: 0.133, unit: "ratio" },
          metrics: {
            coverage_ratio_15min_walk: { baseline: 0.135, intervention: 0.135 },
            effective_demand_m2: { baseline: 269.8, intervention: 856.1 }
          }
        },
        environmental: {
          main_metrics: [
            { label: "Operational Carbon", baseline: 676.78, intervention: 628.44, unit: "tCO2e/yr" },
            { label: "Stranded Carbon", baseline: 676.78, intervention: 586.44, unit: "tCO2e/yr" }
          ],
          counterfactual: {
            embodied_if_new_build_tco2e: 1500.0,
            embodied_if_repurpose_tco2e: 1148.2,
            net_carbon_averted_tco2e: 351.8
          }
        },
        subunits: [
          { subtype: "f_and_b", area_m2: 600, occupancy_baseline: 0.08, occupancy_intervention: 0.85, allocated_carbon_tco2e: 200, allocated_noi_rm: -400000 },
          { subtype: "supermarket", area_m2: 1400, occupancy_baseline: 0.95, occupancy_intervention: 0.95, allocated_carbon_tco2e: 428, allocated_noi_rm: -983363 }
        ]
      },
      timeline: {
        years: ["2026", "2027", "2028", "2030", "2033"],
        metrics: {
          // 下面这些数组是折线图的核心！
          "noi_rm": {
            baseline: [-1383363, -1400000, -1450000, -1500000, -1550000],
            intervention: [-1383363, -1500000, -800000, -200000, 150000]
          },
          "carbon_operational_tco2e": {
            baseline: [676.78, 690.0, 705.0, 740.0, 800.0],
            intervention: [676.78, 650.0, 600.0, 500.0, 420.0]
          },
          "carbon_stranded_tco2e": {
            baseline: [676.78, 690.0, 705.0, 740.0, 800.0],
            intervention: [676.78, 600.0, 400.0, 200.0, 100.0]
          },
          "space_utilization": {
            baseline: [0.0, 0.0, 0.05, 0.10, 0.15],
            intervention: [0.133, 0.25, 0.45, 0.65, 0.85]
          }
        }
      }
    }
  ],
  township_metrics: {
    total_carbon_before_tco2e: 133495.8,
    total_carbon_after_tco2e: 133495.8,
    carbon_delta_pct: 0,
  }
}