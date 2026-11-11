import type { AnalyzeResult } from './types'

export const MOCK_SCENARIO_CASE2: AnalyzeResult = {
  run_id: "LLM-demo-case2",
  scenario_id: "SC-demo-case2",
  interventions: [
    // 1. Primary soft interventions on BLD-0736
    { target_asset_id: "BLD-0736", type: "tenant_matching", role: "primary", beneficiary_asset_id: null },
    { target_asset_id: "BLD-0736", type: "tactical_placemaking", role: "primary", beneficiary_asset_id: null },
    
    // 2. The weekly market at BLD-0736 spills over to BLD-0734 (catalytic link)
    { 
      target_asset_id: "BLD-0736", 
      type: "tactical_placemaking", 
      role: "catalytic", 
      beneficiary_asset_id: "BLD-0734" 
    },
    // Seeing the success, the owner of BLD-0734 asks SDP for tenant matching too
    { target_asset_id: "BLD-0734", type: "tenant_matching", role: "primary", beneficiary_asset_id: null },

    // 3. Primary soft interventions on BLD-0067
    { target_asset_id: "BLD-0067", type: "tenant_matching", role: "primary", beneficiary_asset_id: null },
    { target_asset_id: "BLD-0067", type: "tactical_placemaking", role: "primary", beneficiary_asset_id: null }
  ],
  decision: {
    selected_candidate: "Tenant Match & Neighbourhood Activation",
    reasoning:
      "Neither target is under SDP's control, so no structural intervention is available. BLD-0736 is a flow island with a dead kopitiam. BLD-0067 has a demographic mismatch with zero business presence. A tenant match to a convenience_retail or medical_retail business, paired with a weekend market, addresses both. Crucially, the market at BLD-0736 sits 72m from BLD-0734, a struggling neighbor. The catalytic spillover is immediate: BLD-0734's footfall rises simply because people are drawn to the market. Seeing this, the owner of BLD-0734 proactively requests SDP's tenant matching service to complete the street's revival.",
    key_trade_offs: [
      "Tenant matching relies on landlord consent and takes 2–3 years to converge.",
      "The weekend market is temporary (3 years); after it ends, the street must survive on the strength of the matched tenants."
    ],
    justification: {
      summary:
        "We recommend a coordinated soft-intervention package across three shoplots. We offer BLD-0736 and BLD-0067 owners SDP's tenant matching to find compatible businesses, supported by a three-year weekend market and pop-up sports court to inject immediate footfall. The market at BLD-0736 generates a spillover benefit for the adjacent BLD-0734, prompting its owner to opt into the tenant matching service as well. This proves SDP can revive an entire street without owning a single shoplot.",
      why_this_plan:
        "A pedestrian upgrade was rejected because the flow-island rule forbids building footbridges for isolated assets. For BLD-0067, a physical intervention was rejected because the problem is demand mismatch, not access. We chose a cluster approach rather than isolated interventions because placemaking creates positive externalities — one market can anchor multiple shops.",
      what_simulation_shows:
        "BLD-0736's proxied occupancy rises from 2.9% to 68% by 2033. BLD-0067's proxied occupancy rises from 45.7% to 72.1%. For the adjacent BLD-0734, the catalytic spillover alone pushes its occupancy up by 4.2 percentage points, and with its own tenant matching, it recovers from 17.3% to 61.5%. Street survival within 300m rises from 42% to 65%.",
      beyond_the_model:
        "Landlord consent is the binding constraint. Our simulation assumes a 75% yearly acceptance rate. The visual success of the weekend market is often the catalyst that convinces neighbouring landlords to accept SDP's tenant recommendations.",
      recommendation:
        "Launch the weekend market at BLD-0736 immediately. Use its foot traffic to pitch the tenant-match package to the owners of BLD-0067 and BLD-0734 in the same quarter.",
    },
  },
  assets_analysis: [
    // ============================================================
    // BLD-0736 — Flow Island (kopitiam)
    // ============================================================
    {
      asset_id: "BLD-0736",
      engineering_spec: null,
      summary_card: {
        financial: {
          main_metric: { label: "Counterfactual NOI (if SDP had retained)", baseline: null, intervention: null, unit: "RM", tier: "3b" },
          counterfactual: null,
        },
        social: {
          main_metric: { label: "Space Utilization", baseline: 0.029, intervention: 0.68, unit: "ratio", tier: "3a" },
          metrics: {
            coverage_ratio_5min_walk: { baseline: 0.041, intervention: 0.041 },
            effective_demand_m2: { baseline: 128.4, intervention: 648.2 },
          },
        },
        environmental: {
          main_metrics: [
            { label: "Operational Carbon", baseline: 42.8, intervention: 31.4, unit: "tCO2e/yr" },
            { label: "Stranded Carbon", baseline: 41.6, intervention: 13.3, unit: "tCO2e/yr" },
          ],
          counterfactual: null,
        },
        subunits: null,
        authority: "advisory",
        evaluation_mode: "developer_realization",
        community: {
          lbs: { unique_users: { baseline: 11, intervention: 34 }, dwell_minutes: 18, flow_island_ratio: 0.549, tier: "3a", source: "LBS / Kido Dynamics" },
          business_presence_ratio: 1.0,
          business_turnover_count: 2,
          occupancy_seed_source: "kido_dynamics_mock",
        },
        counterfactual: {
          label: "If SDP retained this asset",
          metrics: [
            { label: "Counterfactual NOI", value: 48200, unit: "RM", tier: "3b" },
            { label: "Estimated Revenue", value: 128400, unit: "RM", tier: "3a" },
            { label: "Survival OPEX Floor", value: 96200, unit: "RM", tier: "3a" },
          ],
        },
      },
      timeline: {
        years: ["2026", "2027", "2028", "2030", "2033"],
        metrics: {
          noi_rm: { baseline: [null, null, null, null, null], intervention: [null, null, null, null, null] },
          carbon_operational_tco2e: { baseline: [42.8, 43.2, 43.6, 44.4, 46.1], intervention: [42.8, 40.1, 36.8, 32.9, 31.4] },
          space_utilization: { baseline: [0.029, 0.024, 0.019, 0.011, 0.004], intervention: [0.029, 0.18, 0.38, 0.56, 0.68] },
        },
      },
    },
    // ============================================================
    // BLD-0734 — Catalytic Beneficiary + New Tenant Match
    // ============================================================
    {
      asset_id: "BLD-0734",
      engineering_spec: null,
      summary_card: {
        financial: {
          main_metric: { label: "Counterfactual NOI", baseline: null, intervention: null, unit: "RM", tier: "3b" },
          counterfactual: null,
        },
        social: {
          main_metric: { label: "Space Utilization", baseline: 0.173, intervention: 0.615, unit: "ratio", tier: "3a" },
          metrics: {
            coverage_ratio_5min_walk: { baseline: 0.052, intervention: 0.052 },
            effective_demand_m2: { baseline: 212.3, intervention: 580.1 },
          },
        },
        environmental: {
          main_metrics: [
            { label: "Operational Carbon", baseline: 55.1, intervention: 42.3, unit: "tCO2e/yr" },
            { label: "Stranded Carbon", baseline: 45.6, intervention: 17.5, unit: "tCO2e/yr" },
          ],
          counterfactual: null,
        },
        subunits: null,
        authority: "advisory",
        evaluation_mode: "developer_realization",
        community: {
          lbs: { unique_users: { baseline: 28, intervention: 52 }, dwell_minutes: 22, flow_island_ratio: 0.85, tier: "3a", source: "LBS / Kido Dynamics" },
          business_presence_ratio: 0.0,
          business_turnover_count: 2,
          occupancy_seed_source: "kido_dynamics_mock",
        },
        counterfactual: {
          label: "If SDP retained this asset",
          metrics: [
            { label: "Counterfactual NOI", value: 72400, unit: "RM", tier: "3b" },
            { label: "Estimated Revenue", value: 165000, unit: "RM", tier: "3a" },
            { label: "Survival OPEX Floor", value: 102000, unit: "RM", tier: "3a" },
          ],
        },
      },
      timeline: {
        years: ["2026", "2027", "2028", "2030", "2033"],
        metrics: {
          noi_rm: { baseline: [null, null, null, null, null], intervention: [null, null, null, null, null] },
          carbon_operational_tco2e: { baseline: [55.1, 55.8, 56.4, 58.1, 60.2], intervention: [55.1, 50.2, 46.8, 44.1, 42.3] },
          space_utilization: { baseline: [0.173, 0.16, 0.14, 0.10, 0.05], intervention: [0.173, 0.25, 0.40, 0.55, 0.615] },
        },
      },
    },
    // ============================================================
    // BLD-0067 — Demographic Mismatch (cafe)
    // ============================================================
    {
      asset_id: "BLD-0067",
      engineering_spec: null,
      summary_card: {
        financial: {
          main_metric: { label: "Counterfactual NOI", baseline: null, intervention: null, unit: "RM", tier: "3b" },
          counterfactual: null,
        },
        social: {
          main_metric: { label: "Space Utilization", baseline: 0.457, intervention: 0.721, unit: "ratio", tier: "3a" },
          metrics: {
            coverage_ratio_5min_walk: { baseline: 0.062, intervention: 0.062 },
            effective_demand_m2: { baseline: 274.1, intervention: 612.8 },
          },
        },
        environmental: {
          main_metrics: [
            { label: "Operational Carbon", baseline: 68.2, intervention: 58.1, unit: "tCO2e/yr" },
            { label: "Stranded Carbon", baseline: 37.0, intervention: 16.2, unit: "tCO2e/yr" },
          ],
          counterfactual: null,
        },
        subunits: null,
        authority: "advisory",
        evaluation_mode: "developer_realization",
        community: {
          lbs: { unique_users: { baseline: 35, intervention: 52 }, dwell_minutes: 24, flow_island_ratio: 1.0, tier: "3a", source: "LBS / Kido Dynamics" },
          business_presence_ratio: 0.0,
          business_turnover_count: 3,
          occupancy_seed_source: "kido_dynamics_mock",
        },
        counterfactual: {
          label: "If SDP retained this asset",
          metrics: [
            { label: "Counterfactual NOI", value: 84200, unit: "RM", tier: "3b" },
            { label: "Estimated Revenue", value: 196400, unit: "RM", tier: "3a" },
            { label: "Survival OPEX Floor", value: 112200, unit: "RM", tier: "3a" },
          ],
        },
      },
      timeline: {
        years: ["2026", "2027", "2028", "2030", "2033"],
        metrics: {
          noi_rm: { baseline: [null, null, null, null, null], intervention: [null, null, null, null, null] },
          carbon_operational_tco2e: { baseline: [68.2, 68.9, 69.7, 71.2, 74.0], intervention: [68.2, 66.4, 63.8, 60.4, 58.1] },
          space_utilization: { baseline: [0.457, 0.438, 0.412, 0.348, 0.214], intervention: [0.457, 0.512, 0.588, 0.652, 0.721] },
        },
      },
    }
  ],
  township_metrics: {
    walk_15min_avg_coverage_before: 0.418,
    walk_15min_avg_coverage_after: 0.418,
    walk_15min_coverage_delta: 0.0,
    total_carbon_before_tco2e: 130922.25,
    total_carbon_after_tco2e: 130861.80,
    carbon_delta_pct: -0.00046,
    project_carbon_after_tco2e: null,
    project_carbon_cumulative_tco2e: null,
    sequestration_by_year_tco2e_year: { "2026": 312.4, "2027": 312.4, "2028": 312.4, "2030": 312.4, "2033": 312.4 },
    sequestration_before_tco2e_year: 312.4,
    sequestration_after_tco2e_year: 312.4,
    sequestration_delta_tco2e_year: 0.0,
    sequestration_cumulative_tco2e: 1562.0,
    canopy_uptake_rate_tco2e_per_m2_year: 0.0015,
    operational_carbon_by_year_tco2e_year: { "2026": 130922.25, "2027": 130870.40, "2028": 130868.30, "2030": 130864.10, "2033": 130861.80 },
    net_carbon_by_year_tco2e_year: { "2026": 130609.85, "2027": 130558.00, "2028": 130555.90, "2030": 130551.70, "2033": 130549.40 },
  },
}