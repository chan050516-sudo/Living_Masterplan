import type { AnalyzeResult } from './types'

export const MOCK_SCENARIO_CASE2: AnalyzeResult = {
  run_id: "LLM-demo-case2",
  scenario_id: "SC-demo-case2",
  interventions: [
    {
      target_asset_id: "BLD-0736",
      type: "tenant_matching",
      role: "primary",
      beneficiary_asset_id: null,
    },
    {
      target_asset_id: "BLD-0736",
      type: "tactical_placemaking",
      role: "primary",
      beneficiary_asset_id: null,
    },
    {
      target_asset_id: "BLD-0067",
      type: "tenant_matching",
      role: "primary",
      beneficiary_asset_id: null,
    },
    {
      target_asset_id: "BLD-0067",
      type: "tactical_placemaking",
      role: "primary",
      beneficiary_asset_id: null,
    },
    {
      // BLD-0734 sits 72m from BLD-0736 and benefits from the
      // weekend market without any direct intervention of its own.
      target_asset_id: "BLD-0736",
      type: "tactical_placemaking",
      role: "catalytic",
      beneficiary_asset_id: "BLD-0734",
    },
  ],
  decision: {
    selected_candidate: "Tenant Match, Street Activation, and Landlord Negotiation",
    reasoning:
      "Neither target is under SDP's control, so no structural intervention is available. The two failures have different root causes and need different treatments. BLD-0736 is a flow island: its flow-island ratio of 0.549 sits below the 0.6 threshold, meaning nearby footfall exists but the street network does not deliver it to the shop. Its kopitiam tenant has a proxied occupancy of 2.9%, effectively closed. A tenant match to a convenience_retail or services business, paired with a weekend market that gives pedestrians a reason to come, addresses both the tenant and the network problem. BLD-0067 is a demand mismatch: its cafe targets a young-adult demographic that is not present in the local catchment (mismatch 0.50), and its business presence is zero — no operating business at all. A tenant match toward medical_retail or services matches the surrounding seniors-and-families profile. Because the two assets sit 450m apart, we recommend two small-scale placemaking events rather than one large one: a weekend market next to BLD-0736 and a pop-up family sports court next to BLD-0067. The two events serve different demographic profiles. BLD-0734, 72m from BLD-0736, picks up the weekend market's uplift as a side benefit without any direct SDP action.",
    key_trade_offs: [
      "Neither asset sees occupancy recovery as fast as a full repurpose would deliver — tenant matching relies on landlord consent and takes 2–3 years to converge, not 18 months.",
      "The placemaking events are temporary: the weekend market runs for three years by default, after which its footfall uplift ends unless a permanent anchor is placed.",
      "BLD-0004-equivalent impact on BLD-0734 is not directly controlled — SDP cannot force the weekend market to benefit the neighbouring unit, it merely happens to fall inside the 400m radius.",
    ],
    justification: {
      summary:
        "Two independent failures need two independent soft treatments. BLD-0736 is a flow island with a dead kopitiam tenant; SDP can offer the landlord a tenant match and run a three-year weekend market on adjacent public land. BLD-0067 is a demographic mismatch with zero business presence; SDP can offer a tenant match toward a family-medical provider and run a pop-up family sports court. Together the two interventions cover a 600m commercial corridor where neither SDP nor any single landlord can act alone.",
      why_this_plan:
        "A pedestrian upgrade or green corridor on either asset was rejected because the flow-island rule in our system explicitly forbids it: building footbridges or crossings for a flow island is slow, costly, and in the simulation it barely moves footfall because most homes already have some route. Only placemaking plus tenant matching changes the reason to come. For BLD-0067, a physical intervention was rejected outright because the problem is demand, not access — a sidewalk does not make a specialty cafe attractive to a senior-heavy catchment. The two-event design was chosen over a single 400m-radius event because the two assets sit 450m apart and no single radius covers both without over-reaching into unrelated properties.",
      what_simulation_shows:
        "BLD-0736's proxied occupancy rises from 2.9% to a projected 68% by 2033 under tenant matching, and street survival within 300m rises from 42% to 61% during the weekend market's three-year run. Its LBS daily footfall moves from 11 to 34. BLD-0067's proxied occupancy rises from 45.7% to 72.1% — a smaller absolute move because the cafe was not fully vacant, but the tenant-type change removes the mismatch flag entirely. BLD-0734, receiving the weekend-market uplift without any direct intervention, sees its proxied occupancy rise 2.4 percentage points. None of these outcomes turns either asset into a strong performer; the goal is stabilisation, not transformation.",
      beyond_the_model:
        "Landlord consent is the binding constraint in both cases. SDP's tenant matching service is a recommendation, not an order: the landlord can decline the tenant or accept a different one. Our simulation assumes SDP's leasing team presents the recommendation and the landlord accepts 75% of the time per year. A real leasing campaign with a strong tenant data pack can raise this, but it is not guaranteed.",
      recommendation:
        "Begin the tenant-match conversation with BLD-0736's landlord immediately, since the kopitiam has effectively closed and the landlord has nothing to lose. Approach BLD-0067's owner with the medical-tenant case, and stage the pop-up sports court to open in the same quarter as the new tenant. Review at the 24-month mark whether both assets have crossed 50% occupancy; if not, escalate to a second tenant match.",
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
          main_metric: {
            label: "Counterfactual NOI (if SDP had retained)",
            baseline: null,
            intervention: null,
            unit: "RM",
            tier: "3b",
          },
          counterfactual: {
            capex_if_new_build_rm: 0,
            capex_if_repurpose_rm: 0,
            capex_saved_rm: 0,
          },
        },
        social: {
          main_metric: {
            label: "Space Utilization",
            baseline: 0.029,
            intervention: 0.68,
            unit: "ratio",
            tier: "3a",
          },
          metrics: {
            coverage_ratio_5min_walk: { baseline: 0.041, intervention: 0.041 },
            coverage_ratio_15min_walk: { baseline: 0.318, intervention: 0.318 },
            reachable_population_walk: { baseline: 8470, intervention: 8470 },
            effective_demand_m2: { baseline: 128.4, intervention: 648.2 },
          },
        },
        environmental: {
          main_metrics: [
            {
              label: "Operational Carbon",
              baseline: 42.8,
              intervention: 31.4,
              unit: "tCO2e/yr",
            },
            {
              label: "Stranded Carbon",
              baseline: 41.6,
              intervention: 13.3,
              unit: "tCO2e/yr",
            },
          ],
          counterfactual: null,
        },
        subunits: null,
        authority: "advisory",
        evaluation_mode: "developer_realization",
        community: {
          lbs: {
            unique_users: { baseline: 11, intervention: 34 },
            dwell_minutes: 18,
            flow_island_ratio: 0.549,
            tier: "3a",
            source: "LBS / Kido Dynamics (mock, sample-based)",
          },
          business_presence_ratio: 1.0,
          business_turnover_count: 2,
          occupancy_seed_source: "kido_dynamics_mock",
        },
        counterfactual: {
          label: "If SDP retained this asset",
          metrics: [
            { label: "Counterfactual NOI", value: 48200, unit: "RM", tier: "3b" },
            { label: "Counterfactual NOI Yield", value: 0.082, unit: "ratio", tier: "3b" },
            { label: "Estimated Revenue", value: 128400, unit: "RM", tier: "3a" },
            { label: "Survival OPEX Floor", value: 96200, unit: "RM", tier: "3a" },
          ],
        },
      },
      timeline: {
        years: ["2026", "2027", "2028", "2030", "2033"],
        metrics: {
          noi_rm: {
            baseline: [null, null, null, null, null],
            intervention: [null, null, null, null, null],
          },
          carbon_operational_tco2e: {
            baseline: [42.8, 43.2, 43.6, 44.4, 46.1],
            intervention: [42.8, 40.1, 36.8, 32.9, 31.4],
          },
          space_utilization: {
            baseline: [0.029, 0.024, 0.019, 0.011, 0.004],
            intervention: [0.029, 0.18, 0.38, 0.56, 0.68],
          },
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
          main_metric: {
            label: "Counterfactual NOI (if SDP had retained)",
            baseline: null,
            intervention: null,
            unit: "RM",
            tier: "3b",
          },
          counterfactual: {
            capex_if_new_build_rm: 0,
            capex_if_repurpose_rm: 0,
            capex_saved_rm: 0,
          },
        },
        social: {
          main_metric: {
            label: "Space Utilization",
            baseline: 0.457,
            intervention: 0.721,
            unit: "ratio",
            tier: "3a",
          },
          metrics: {
            coverage_ratio_5min_walk: { baseline: 0.062, intervention: 0.062 },
            coverage_ratio_15min_walk: { baseline: 0.401, intervention: 0.401 },
            reachable_population_walk: { baseline: 13480, intervention: 13480 },
            effective_demand_m2: { baseline: 274.1, intervention: 612.8 },
          },
        },
        environmental: {
          main_metrics: [
            {
              label: "Operational Carbon",
              baseline: 68.2,
              intervention: 58.1,
              unit: "tCO2e/yr",
            },
            {
              label: "Stranded Carbon",
              baseline: 37.0,
              intervention: 16.2,
              unit: "tCO2e/yr",
            },
          ],
          counterfactual: null,
        },
        subunits: null,
        authority: "advisory",
        evaluation_mode: "developer_realization",
        community: {
          lbs: {
            unique_users: { baseline: 35, intervention: 52 },
            dwell_minutes: 24,
            flow_island_ratio: 1.0,
            tier: "3a",
            source: "LBS / Kido Dynamics (mock, sample-based)",
          },
          business_presence_ratio: 0.0,
          business_turnover_count: 3,
          occupancy_seed_source: "kido_dynamics_mock",
        },
        counterfactual: {
          label: "If SDP retained this asset",
          metrics: [
            { label: "Counterfactual NOI", value: 84200, unit: "RM", tier: "3b" },
            { label: "Counterfactual NOI Yield", value: 0.134, unit: "ratio", tier: "3b" },
            { label: "Estimated Revenue", value: 196400, unit: "RM", tier: "3a" },
            { label: "Survival OPEX Floor", value: 112200, unit: "RM", tier: "3a" },
          ],
        },
      },
      timeline: {
        years: ["2026", "2027", "2028", "2030", "2033"],
        metrics: {
          noi_rm: {
            baseline: [null, null, null, null, null],
            intervention: [null, null, null, null, null],
          },
          carbon_operational_tco2e: {
            baseline: [68.2, 68.9, 69.7, 71.2, 74.0],
            intervention: [68.2, 66.4, 63.8, 60.4, 58.1],
          },
          space_utilization: {
            baseline: [0.457, 0.438, 0.412, 0.348, 0.214],
            intervention: [0.457, 0.512, 0.588, 0.652, 0.721],
          },
        },
      },
    },
  ],
  township_metrics: {
    walk_15min_avg_coverage_before: 0.418,
    walk_15min_avg_coverage_after: 0.418,
    walk_15min_coverage_delta: 0.0,
    total_carbon_before_tco2e: 130922.25,
    total_carbon_after_tco2e: 130915.80,
    carbon_delta_pct: -0.00005,
    project_carbon_after_tco2e: null,
    project_carbon_cumulative_tco2e: null,
    sequestration_by_year_tco2e_year: {
      "2026": 312.4,
      "2027": 312.4,
      "2028": 312.4,
      "2030": 312.4,
      "2033": 312.4,
    },
    sequestration_before_tco2e_year: 312.4,
    sequestration_after_tco2e_year: 312.4,
    sequestration_delta_tco2e_year: 0.0,
    sequestration_cumulative_tco2e: 1562.0,
    canopy_uptake_rate_tco2e_per_m2_year: 0.0015,
    operational_carbon_by_year_tco2e_year: {
      "2026": 130922.25,
      "2027": 130921.40,
      "2028": 130920.30,
      "2030": 130918.10,
      "2033": 130915.80,
    },
    net_carbon_by_year_tco2e_year: {
      "2026": 130609.85,
      "2027": 130609.00,
      "2028": 130607.90,
      "2030": 130605.70,
      "2033": 130603.40,
    },
  },
}