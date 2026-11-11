import type { AnalyzeResult } from './types'

export const MOCK_SCENARIO_CASE1: AnalyzeResult = {
  run_id: "LLM-demo-case1",
  scenario_id: "SC-demo-case1",
  interventions: [
    {
      target_asset_id: "BLD-0037",
      type: "repurpose",
      role: "primary",
      beneficiary_asset_id: null,
    },
    {
      target_asset_id: "BLD-0037",
      type: "retrofit",
      role: "primary",
      beneficiary_asset_id: null,
    },
    {
      target_asset_id: "BLD-0037",
      type: "pedestrian_upgrade",
      role: "primary",
      beneficiary_asset_id: null,
    },
    {
      // The pedestrian upgrade acts on BLD-0037's own frontage. The
      // second entry repeats it as a catalytic link so the map draws
      // the arc to BLD-0004 and the beneficiary panel lights up.
      target_asset_id: "BLD-0037",
      type: "pedestrian_upgrade",
      role: "catalytic",
      beneficiary_asset_id: "BLD-0004",
    },
    {
      target_asset_id: "BLD-0260",
      type: "renovation",
      role: "primary",
      beneficiary_asset_id: null,
    },
  ],
  decision: {
    selected_candidate: "Medical Hub Anchor, Structural Retention, and Network Repair",
    reasoning:
      "BLD-0037's failure is structural: seven subtypes, all below 15% occupancy, a rapid decline from 86% peak one year ago, and a negative NOI of RM 2.01M/yr. The attached feasibility summary caps CAPEX at RM 2M and prohibits full closure, which rules out a rebuild. The asset's primary label is supermarket but the actual tenancy is a dead 7-subtype mix. A partial repurpose of the three dead subtypes (convenience_retail 3.1%, cafe 3.6%, services 13.2%) into a consolidated medical anchor exploits the township's existing medical demand and complements the struggling BLD-0004 medical_retail 286m away rather than competing with it. A deep retrofit with green roof and rooftop PV addresses the 89% stranded-carbon ratio without touching the shell. The pedestrian upgrade on BLD-0037's frontage extends into BLD-0004's walking catchment, so a single intervention raises the beneficiary's 5-minute coverage from 5% to a projected 14%. We also recommend a residential renovation on BLD-0260 — four developer-held units, with owner consent for the eleven sold units — because the asset's high_uhi_exposure flag would otherwise remain unaddressed at the township scale.",
    key_trade_offs: [
      "CAPEX reaches RM 1.79M against the RM 2M ceiling, leaving only RM 0.21M for contingency — the retrofit is sized to the ceiling, not to the ideal.",
      "BLD-0037's NOI improves from -RM 2.01M to -RM 0.99M, but does not turn positive by 2033: the retained 2003-era shell still carries high maintenance. We prioritise carbon and occupancy over immediate profitability.",
      "BLD-0004's catalytic benefit is partial, not full: its occupancy moves from a proxied 8% to a projected 19%, which is a meaningful improvement but does not save the asset on its own. The simulation cannot measure the final tenant conversion.",
    ],
    justification: {
      summary:
        "We recommend a three-asset coordinated plan: a partial repurpose that consolidates three dead subtypes in BLD-0037 into a medical anchor, a deep retrofit that preserves the 2003 concrete shell while cutting operational carbon by 42% and addressing the UHI exposure, and a pedestrian upgrade whose canopy extends into the neighbouring BLD-0004's walking catchment. A separate renovation on BLD-0260 converts four developer-held houses into affordable rental stock, addressing a township-level UHI hotspot the user did not raise in the brief. The combined plan uses 89.5% of the RM 2M CAPEX ceiling and reduces stranded operational carbon across the two primary assets by 71%.",
      why_this_plan:
        "A full repurpose of BLD-0037 to a single subtype was rejected because it would breach the feasibility summary's continuous-operation mandate and destroy the four healthy subtypes (kopitiam at 11%, office at 15%, medical_retail at 12%, restaurant at 15%) that still pay rent. A standalone retrofit was rejected because it cannot cure the 89% stranded-carbon ratio on its own — the empty floor still costs energy. The selected plan is the only option that complies with the PDF constraints, preserves the twelve-month anchor protection, and simultaneously addresses BLD-0004's reachability. The BLD-0260 renovation was added because the user brief focused only on BLD-0037 but the township-level UHI narrative requires a residential asset with an observed heat signature.",
      what_simulation_shows:
        "BLD-0037's aggregate occupancy rises from 11% to 77% by 2033. NOI improves from -RM 2.01M to -RM 0.99M annually — a 51% reduction in losses, but not a return to profitability. Operational carbon falls from 865 to 502 tCO2e/yr, and stranded carbon from 772 to 89 tCO2e/yr. The retrofit's green roof alone contributes an estimated 2.2°C of ambient relief. BLD-0004's 5-minute walking coverage expands from 5% to 14%, and its proxied occupancy estimate moves from 8% to 19% — a genuine but partial improvement. BLD-0260's four developer-held units reach 94% occupancy under affordable_housing benchmarks. Township-wide stranded carbon falls from 31,011 to 26,388 tCO2e/yr.",
      beyond_the_model:
        "The medical anchor benefits from a healthcare system still consolidating toward outpatient and specialist care. BLD-0004 and BLD-0037 together give the township a medical cluster, but the simulation cannot model insurance network effects, patient catchment behaviour, or the licensing timeline — real medical tenant fit-out adds 6–9 months to the modelled 18-month activation.",
      recommendation:
        "Proceed with the BLD-0037 retrofit and pedestrian upgrade in Q1 2027. Stage the partial repurpose to medical tenant fit-out after the retrofit activates. Approach BLD-0260's eleven sold-unit owners as a single strata block before the residential renovation, because the mixed-ownership warning will otherwise constrain execution.",
    },
  },
  assets_analysis: [
    // ============================================================
    // BLD-0037 — Primary Commercial Asset
    // ============================================================
    {
      asset_id: "BLD-0037",
      engineering_spec: {
        structure_retention_ratio: 0.95,
        facade_action: "insulated_overclad",
        primary_material: "ggbs_concrete",
        roof_intervention: "green_roof",
        hvac_cop: 4.2,
        operating_hours_per_week: 84,
        rooftop_pv_coverage: 0.35,
        pv_yield_kwh_year: 324870,
      },
      summary_card: {
        financial: {
          main_metric: {
            label: "Annual NOI",
            baseline: -2011729.78,
            intervention: -992442.0,
            unit: "RM",
          },
          counterfactual: {
            capex_if_new_build_rm: 23292220.0,
            capex_if_repurpose_rm: 1789200.0,
            capex_saved_rm: 21503020.0,
          },
        },
        social: {
          main_metric: {
            label: "Space Utilization",
            baseline: 0.11,
            intervention: 0.766,
            unit: "ratio",
          },
          metrics: {
            coverage_ratio_5min_walk: { baseline: 0.168, intervention: 0.352 },
            coverage_ratio_15min_walk: { baseline: 0.446, intervention: 0.612 },
            reachable_population_walk: { baseline: 23499, intervention: 31620 },
            effective_demand_m2: { baseline: 1279.2, intervention: 3142.5 },
          },
        },
        environmental: {
          main_metrics: [
            {
              label: "Operational Carbon",
              baseline: 865.39,
              intervention: 502.18,
              unit: "tCO2e/yr",
            },
            {
              label: "Stranded Carbon",
              baseline: 771.93,
              intervention: 89.44,
              unit: "tCO2e/yr",
            },
            {
              label: "Surface Temp ΔT",
              baseline: null,
              intervention: null,
              unit: "°C",
              cooling_source: "roof",
              cooling_from_roof_c: 2.2,
            },
            {
              label: "Perceived Temp (AT)",
              baseline: null,
              intervention: null,
              unit: "°C",
            },
          ],
          counterfactual: {
            embodied_if_new_build_tco2e: 3612.4,
            embodied_if_repurpose_tco2e: 419.2,
            net_carbon_averted_tco2e: 3193.2,
          },
        },
        subunits: [
          {
            subtype: "restaurant",
            area_m2: 408.8,
            occupancy_baseline: 0.146,
            occupancy_intervention: 0.62,
            allocated_carbon_tco2e: 50.2,
            allocated_noi_rm: 61148,
          },
          {
            subtype: "kopitiam",
            area_m2: 817.6,
            occupancy_baseline: 0.112,
            occupancy_intervention: 0.72,
            allocated_carbon_tco2e: 100.4,
            allocated_noi_rm: 96627,
          },
          {
            subtype: "cafe",
            area_m2: 408.8,
            occupancy_baseline: 0.036,
            occupancy_intervention: 0.0,
            allocated_carbon_tco2e: 0,
            allocated_noi_rm: 0,
          },
          {
            subtype: "convenience_retail",
            area_m2: 613.2,
            occupancy_baseline: 0.031,
            occupancy_intervention: 0.0,
            allocated_carbon_tco2e: 0,
            allocated_noi_rm: 0,
          },
          {
            subtype: "services",
            area_m2: 613.2,
            occupancy_baseline: 0.132,
            occupancy_intervention: 0.0,
            allocated_carbon_tco2e: 0,
            allocated_noi_rm: 0,
          },
          {
            subtype: "medical_retail",
            area_m2: 2043.8,
            occupancy_baseline: 0.121,
            occupancy_intervention: 0.92,
            allocated_carbon_tco2e: 251.1,
            allocated_noi_rm: 535890,
          },
          {
            subtype: "office",
            area_m2: 817.6,
            occupancy_baseline: 0.152,
            occupancy_intervention: 0.50,
            allocated_carbon_tco2e: 100.4,
            allocated_noi_rm: 98635,
          },
        ],
        authority: "full_control",
        evaluation_mode: "operating_performance",
        counterfactual: null,
      },
      timeline: {
        years: ["2026", "2027", "2028", "2030", "2033"],
        metrics: {
          noi_rm: {
            baseline: [
              -2011729.78, -2105100.0, -2206890.0, -2420450.0, -2801400.0,
            ],
            intervention: [
              -2011729.78, -2104880.0, -1840620.0, -1345120.0, -992442.0,
            ],
          },
          carbon_operational_tco2e: {
            baseline: [865.39, 878.2, 891.6, 918.3, 962.7],
            intervention: [865.39, 752.4, 621.8, 545.2, 502.18],
          },
          carbon_stranded_tco2e: {
            baseline: [771.93, 785.4, 799.1, 825.5, 868.2],
            intervention: [771.93, 664.5, 380.4, 152.1, 89.44],
          },
          space_utilization: {
            baseline: [0.11, 0.095, 0.08, 0.055, 0.025],
            intervention: [0.11, 0.28, 0.512, 0.68, 0.766],
          },
          surface_temp_delta_c: {
            baseline: [null, null, null, null, null],
            intervention: [null, null, null, null, null],
          },
        },
      },
    },
    // ============================================================
    // BLD-0260 — Residential Renovation (user did not consider)
    // ============================================================
    {
      asset_id: "BLD-0260",
      engineering_spec: {
        structure_retention_ratio: 1.0,
        facade_action: "retain",
        primary_material: "standard_concrete",
        roof_intervention: "green_roof",
        hvac_cop: 3.5,
        operating_hours_per_week: 168,
        rooftop_pv_coverage: 0.2,
        pv_yield_kwh_year: 110376,
      },
      summary_card: {
        financial: {
          main_metric: {
            label: "Annual NOI",
            baseline: 0.0,
            intervention: 216800.0,
            unit: "RM",
          },
          counterfactual: {
            capex_if_new_build_rm: 6300000.0,
            capex_if_repurpose_rm: 216000.0,
            capex_saved_rm: 6084000.0,
          },
        },
        social: {
          main_metric: {
            label: "Space Utilization",
            baseline: 0.0,
            intervention: 0.94,
            unit: "ratio",
          },
          metrics: {
            coverage_ratio_15min_walk: { baseline: 0.388, intervention: 0.388 },
            reachable_population_walk: { baseline: 18740, intervention: 18740 },
            effective_demand_m2: { baseline: 0.0, intervention: 0.0 },
          },
        },
        environmental: {
          main_metrics: [
            {
              label: "Operational Carbon",
              baseline: 0.0,
              intervention: 62.4,
              unit: "tCO2e/yr",
            },
            {
              label: "Stranded Carbon",
              baseline: 0.0,
              intervention: 3.74,
              unit: "tCO2e/yr",
            },
            {
              label: "Surface Temp ΔT",
              baseline: 3.42,
              intervention: 1.28,
              unit: "°C",
              cooling_source: "canopy+roof",
              cooling_from_roof_c: 2.2,
              cooling_from_canopy_c: -0.04,
            },
          ],
          counterfactual: {
            embodied_if_new_build_tco2e: 1680.0,
            embodied_if_repurpose_tco2e: 42.0,
            net_carbon_averted_tco2e: 1638.0,
          },
        },
        subunits: null,
        authority: "full_control",
        evaluation_mode: "operating_performance",
        counterfactual: null,
      },
      timeline: {
        years: ["2026", "2027", "2028", "2030", "2033"],
        metrics: {
          noi_rm: {
            baseline: [0, 0, 0, 0, 0],
            intervention: [0, -86400, 108400, 175200, 216800],
          },
          carbon_operational_tco2e: {
            baseline: [0, 0, 0, 0, 0],
            intervention: [0, 31.2, 54.6, 60.1, 62.4],
          },
          space_utilization: {
            baseline: [0, 0, 0, 0, 0],
            intervention: [0, 0.42, 0.78, 0.91, 0.94],
          },
          surface_temp_delta_c: {
            baseline: [3.42, 3.42, 3.42, 3.42, 3.42],
            intervention: [3.42, 3.42, 2.82, 1.85, 1.28],
          },
        },
      },
    },
    // ============================================================
    // BLD-0004 — Catalytic Beneficiary (no direct intervention)
    // ============================================================
    {
      asset_id: "BLD-0004",
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
            baseline: 0.082,
            intervention: 0.19,
            unit: "ratio",
            tier: "3a",
          },
          metrics: {
            coverage_ratio_5min_walk: { baseline: 0.05, intervention: 0.142 },
            coverage_ratio_15min_walk: { baseline: 0.412, intervention: 0.478 },
            reachable_population_walk: { baseline: 14680, intervention: 18920 },
            effective_demand_m2: { baseline: 342.5, intervention: 892.3 },
          },
        },
        environmental: {
          main_metrics: [
            {
              label: "Operational Carbon",
              baseline: 124.5,
              intervention: 118.8,
              unit: "tCO2e/yr",
            },
            {
              label: "Stranded Carbon",
              baseline: 114.3,
              intervention: 96.3,
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
            unique_users: { baseline: 5, intervention: 18 },
            dwell_minutes: 12,
            flow_island_ratio: 0.995,
            tier: "3a",
            source: "LBS / Kido Dynamics (mock, sample-based)",
          },
          business_presence_ratio: 0.0,
          business_turnover_count: 1,
          occupancy_seed_source: "kido_dynamics_mock",
        },
        counterfactual: {
          label: "If SDP retained this asset",
          metrics: [
            { label: "Counterfactual NOI", value: -182400, unit: "RM", tier: "3b" },
            { label: "Counterfactual NOI Yield", value: -0.041, unit: "ratio", tier: "3b" },
            { label: "Estimated Revenue", value: 64800, unit: "RM", tier: "3a" },
            { label: "Survival OPEX Floor", value: 132000, unit: "RM", tier: "3a" },
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
            baseline: [124.5, 126.8, 129.1, 133.4, 141.2],
            intervention: [124.5, 123.1, 121.4, 119.8, 118.8],
          },
          space_utilization: {
            baseline: [0.082, 0.071, 0.059, 0.038, 0.015],
            intervention: [0.082, 0.112, 0.148, 0.175, 0.19],
          },
          coverage_ratio_5min_walk: {
            baseline: [0.05, 0.05, 0.05, 0.05, 0.05],
            intervention: [0.05, 0.05, 0.142, 0.142, 0.142],
          },
        },
      },
    },
  ],
  township_metrics: {
    walk_15min_avg_coverage_before: 0.418,
    walk_15min_avg_coverage_after: 0.462,
    walk_15min_coverage_delta: 0.044,
    total_carbon_before_tco2e: 130922.25,
    total_carbon_after_tco2e: 129358.40,
    carbon_delta_pct: -0.01194,
    project_carbon_after_tco2e: null,
    project_carbon_cumulative_tco2e: null,
    sequestration_by_year_tco2e_year: {
      "2026": 312.4,
      "2027": 321.8,
      "2028": 331.5,
      "2030": 351.2,
      "2033": 384.6,
    },
    sequestration_before_tco2e_year: 312.4,
    sequestration_after_tco2e_year: 384.6,
    sequestration_delta_tco2e_year: 72.2,
    sequestration_cumulative_tco2e: 1721.8,
    canopy_uptake_rate_tco2e_per_m2_year: 0.0015,
    operational_carbon_by_year_tco2e_year: {
      "2026": 130922.25,
      "2027": 130450.10,
      "2028": 129870.30,
      "2030": 129540.80,
      "2033": 129358.40,
    },
    net_carbon_by_year_tco2e_year: {
      "2026": 130609.85,
      "2027": 130128.30,
      "2028": 129538.80,
      "2030": 129189.60,
      "2033": 128973.80,
    },
  },
}