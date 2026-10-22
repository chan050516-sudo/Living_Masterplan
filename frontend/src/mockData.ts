import type { AnalyzeResult } from './types'

export const MOCK_SCENARIO_1: AnalyzeResult = {
  run_id: "LLM-demo-1",
  scenario_id: "SC-demo-1",
  interventions: [
    {
      target_asset_id: "BLD-0183",
      type: "repurpose",
      role: "primary",
      beneficiary_asset_id: null
    },
    {
      target_asset_id: "BLD-0183",
      type: "pedestrian_upgrade",
      role: "primary",
      beneficiary_asset_id: null
    },
    {
      target_asset_id: "BLD-0183",
      type: "retrofit",
      role: "primary",
      beneficiary_asset_id: null
    }
  ],
  decision: {
    selected_candidate: "Surgical Subtype Repurpose & Pedestrian Link",
    reasoning: "The attached PDF imposes strict constraints: RM 2M cap, continuous operation, and anchor protection. Full demolition is impossible. Furthermore, our spatial data reveals a 0% 5-minute walk coverage, making it impossible to capture local footfall. Thus, we rejected a full repurpose. Instead, we propose a targeted intervention: converting the dead cafe and entertainment zones into high-demand medical/office spaces, while simultaneously linking the asset to the pedestrian network and retrofitting the 2003-era HVAC system. Due to the heavy OPEX of the aging structure, full positive NOI is not immediately achievable, but this strategy materially slows the financial deterioration.",
    key_trade_offs: [
      "Capex reaches RM 1.95M (just under the RM 2M limit), leaving only RM 50k for contingency.",
      "Retains the 84.2% supermarket anchor without disruption, but sacrifices the potential larger scale of a full mall rebuild."
    ],
    justification: {
      summary: "We recommend a dual strategy: partial subtype repurpose combined with a spatial pedestrian upgrade and energy retrofit. By aligning dead space with the strong medical demand and fixing the 0% walkability deficit, we elevate asset occupancy to 85.1%, slash operational carbon by 24.1%, and reduce annual NOI losses by RM 1.2M. The asset remains slightly negative in 2033 but avoids impending insolvency.",
      why_this_plan: "The alternative full-building repurpose was rejected because it would breach the PDF's continuous-operation mandate and the anchor lease. A pure energy retrofit was rejected because it cannot fix the underlying demand decay in the F&B zones. Our selected plan is the only one that complies with the PDF constraints while directly addressing the structural footfall issue.",
      what_simulation_shows: "At the asset level, NOI improves from -RM 2.34M to -RM 1.14M annually. Space utilization jumps from 69.8% to 85.1%. The pedestrian upgrade expands 5-min walk coverage from 0% to 18.5%. Operational carbon drops from 1,660 to 1,295 tCO2e/yr, and the project avoids 2,462 tCO2e in embodied carbon by preserving the shell.",
      beyond_the_model: "Medical tenants generate stable, non-discretionary daytime footfall that naturally supports the remaining ground-floor convenience retail, creating a self-reinforcing commercial ecosystem.",
      recommendation: "Proceed immediately by executing the pedestrian link in Q1 2027, followed by the partial F&B zone conversion. However, subsequent tenant leasing and cost control remain critical to reach break-even."
    }
  },
  assets_analysis: [
    {
      asset_id: "BLD-0183",
      summary_card: {
        financial: {
          main_metric: {
            label: "Annual NOI",
            baseline: -2342226.25,
            intervention: -1140522.84,
            unit: "RM"
          },
          counterfactual: {
            capex_if_new_build_rm: 23292220.0,
            capex_if_repurpose_rm: 1950000.0,
            capex_saved_rm: 21342220.0
          }
        },
        social: {
          main_metric: {
            label: "Space Utilization",
            baseline: 0.698,
            intervention: 0.851,
            unit: "ratio"
          },
          metrics: {
            coverage_ratio_5min_walk: {
              baseline: 0.0,
              intervention: 0.185
            },
            coverage_ratio_15min_walk: {
              baseline: 0.3244,
              intervention: 0.4512
            },
            effective_demand_m2: {
              baseline: 3125.9,
              intervention: 3825.3
            }
          }
        },
        environmental: {
          main_metrics: [
            {
              label: "Operational Carbon",
              baseline: 1660.45,
              intervention: 1295.15,
              unit: "tCO2e/yr"
            },
            {
              label: "Stranded Carbon",
              baseline: 501.45,
              intervention: 193.05,
              unit: "tCO2e/yr"
            }
          ],
          counterfactual: {
            embodied_if_new_build_tco2e: 2994.7,
            embodied_if_repurpose_tco2e: 532.4,
            net_carbon_averted_tco2e: 2462.3
          }
        },
        subunits: [
          {
            subtype: "cafe",
            area_m2: 325.8,
            occupancy_baseline: 0.511,
            occupancy_intervention: 0.0,
            allocated_carbon_tco2e: 0,
            allocated_noi_rm: 0
          },
          {
            subtype: "medical_retail",
            area_m2: 651.6,
            occupancy_baseline: 0.863,
            occupancy_intervention: 0.921,
            allocated_carbon_tco2e: 120,
            allocated_noi_rm: 450000
          },
          {
            subtype: "entertainment",
            area_m2: 610.9,
            occupancy_baseline: 0.572,
            occupancy_intervention: 0.0,
            allocated_carbon_tco2e: 0,
            allocated_noi_rm: 0
          },
          {
            subtype: "office",
            area_m2: 1303.3,
            occupancy_baseline: 0.831,
            occupancy_intervention: 0.948,
            allocated_carbon_tco2e: 250,
            allocated_noi_rm: 850000
          },
          {
            subtype: "supermarket",
            area_m2: 1583.9,
            occupancy_baseline: 0.842,
            occupancy_intervention: 0.845,
            allocated_carbon_tco2e: 601,
            allocated_noi_rm: 120000
          },
          {
            subtype: "restaurant",
            area_m2: 896.0,
            occupancy_baseline: 0.539,
            occupancy_intervention: 0.682,
            allocated_carbon_tco2e: 200,
            allocated_noi_rm: -150000
          }
        ]
      },
      timeline: {
        years: ["2026", "2027", "2028", "2030", "2033"],
        metrics: {
          noi_rm: {
            baseline: [-2342226.25, -2410550.12, -2495233.88, -2601449.21, -2735902.67],
            intervention: [-2342226.25, -2210441.30, -1654220.15, -1320550.87, -1140522.84]
          },
          carbon_operational_tco2e: {
            baseline: [1660.45, 1668.22, 1675.10, 1689.55, 1704.32],
            intervention: [1660.45, 1554.30, 1382.50, 1320.15, 1295.15]
          },
          carbon_stranded_tco2e: {
            baseline: [501.45, 515.22, 532.10, 550.55, 568.32],
            intervention: [501.45, 420.30, 280.50, 220.15, 193.05]
          },
          space_utilization: {
            baseline: [0.698, 0.6882, 0.6741, 0.6552, 0.6321],
            intervention: [0.698, 0.7050, 0.7805, 0.8255, 0.8510]
          },
          coverage_ratio_5min_walk: {
            baseline: [0.0, 0.0, 0.0, 0.0, 0.0],
            intervention: [0.0, 0.0, 0.185, 0.185, 0.185]
          }
        }
      }
    }
  ],
  township_metrics: {
    total_carbon_before_tco2e: 130922.25,
    total_carbon_after_tco2e: 128519.88,
    carbon_delta_pct: -0.01835
  }
}

export const MOCK_SCENARIO_2: AnalyzeResult = {
  run_id: "LLM-demo-2",
  scenario_id: "SC-demo-2",
  interventions: [
    {
      target_asset_id: "P-VAC-07",
      type: "new_development",
      role: "catalytic",
      beneficiary_asset_id: "BLD-0568"
    },
    {
      target_asset_id: "BLD-0568",
      type: "green_corridor",
      role: "primary",
      beneficiary_asset_id: null
    }
  ],
  decision: {
    selected_candidate: "Catalytic Sports Hub & Pedestrian Link",
    reasoning: "Although geographically adjacent, BLD-0568 is a pedestrian island with a 0% walkable catchment due to a disconnected road network. Direct asset intervention cannot fix this physical isolation. By deploying a 1,200m² Community Sports Centre on the adjacent parcel (P-VAC-07) AND constructing a green corridor to bridge the gap, we unlock the flow of local residents. Weekly sports activities create high-frequency destination trips, driving a modelled 4,500-person increase in walkable reachability and transforming the asset's commercial viability.",
    key_trade_offs: [
      "Accepts a 0.4% increase in township operational carbon due to the new construction on P-VAC-07.",
      "The solution relies heavily on the new pedestrian link; without the Green Corridor, the new sports facility would not benefit BLD-0568."
    ],
    justification: {
      summary: "We recommend a dual spatial intervention: constructing a Sports Centre anchor on P-VAC-07 while paving a green corridor to BLD-0568. This synergy expands the modelled walk-reachable population from 0 to over 4,500, lifting retail occupancy from 13.6% to 68.3%, and shifting annual NOI from a deep negative to positive cash flow.",
      why_this_plan: "Doing nothing leaves the asset as a permanent ghost town. A standalone retrofit was rejected because it cannot cure physical isolation. By injecting a high-frequency complementary use next door and fixing the pedestrian network, we create a non-discretionary footfall loop that benefits both sites.",
      what_simulation_shows: "At BLD-0568, effective demand surges to 2,200 m², shifting annual NOI from -RM 838k to +RM 150k. At P-VAC-07, the new sports facility yields an 8.5% return on the RM 1.5M capex. Note that the link between reachable population and actual leasing velocity depends on market absorption rates.",
      beyond_the_model: "Sports facilities generate recurring weekly visits from local residents, creating steady weekday evening and weekend footfall. Integrating convenience retail and F&B into this routine creates an inelastic demand loop.",
      recommendation: "Proceed immediately with the green corridor engineering to align with the sports facility's targeted opening in Q3 2027."
    }
  },
  assets_analysis: [
    {
      asset_id: "BLD-0568",
      summary_card: {
        financial: {
          main_metric: { label: "Annual NOI", baseline: -838515.48, intervention: 150450.20, unit: "RM" },
          counterfactual: { capex_if_new_build_rm: 11062695.0, capex_if_repurpose_rm: 2500000.0, capex_saved_rm: 8562695.0 }
        },
        social: {
          main_metric: { label: "Space Utilization", baseline: 0.136, intervention: 0.682, unit: "ratio" },
          metrics: {
            coverage_ratio_5min_walk: { baseline: 0.0, intervention: 0.32 },
            reachable_population_walk: { baseline: 0.0, intervention: 4530.0 },
            effective_demand_m2: { baseline: 0.0, intervention: 2215.4 }
          }
        },
        environmental: {
          main_metrics: [
            { label: "Operational Carbon", baseline: 566.53, intervention: 420.15, unit: "tCO2e/yr" },
            { label: "Stranded Carbon", baseline: 489.48, intervention: 156.22, unit: "tCO2e/yr" }
          ],
          counterfactual: { embodied_if_new_build_tco2e: 1106.27, embodied_if_repurpose_tco2e: 215.12, net_carbon_averted_tco2e: 891.15 }
        },
        subunits: [
          { subtype: "cafe", area_m2: 413.3, occupancy_baseline: 0.127, occupancy_intervention: 0.85, allocated_carbon_tco2e: 120.5, allocated_noi_rm: 50000 },
          { subtype: "convenience_retail", area_m2: 413.3, occupancy_baseline: 0.138, occupancy_intervention: 0.75, allocated_carbon_tco2e: 150.2, allocated_noi_rm: 60000 },
          { subtype: "medical_retail", area_m2: 206.7, occupancy_baseline: 0.067, occupancy_intervention: 0.80, allocated_carbon_tco2e: 80.2, allocated_noi_rm: 40000 },
          { subtype: "office", area_m2: 620.0, occupancy_baseline: 0.173, occupancy_intervention: 0.65, allocated_carbon_tco2e: 150.5, allocated_noi_rm: 10000 },
          { subtype: "services", area_m2: 413.3, occupancy_baseline: 0.155, occupancy_intervention: 0.65, allocated_carbon_tco2e: 100.2, allocated_noi_rm: 10000 },
          { subtype: "restaurant", area_m2: 620.05, occupancy_baseline: 0.154, occupancy_intervention: 0.53, allocated_carbon_tco2e: 120.1, allocated_noi_rm: -19549.80 }
        ]
      },
      timeline: {
        years: ["2026", "2027", "2028", "2030", "2033"],
        metrics: {
          noi_rm: { baseline: [-838515.48, -850123.12, -870543.55, -890123.10, -920453.33], intervention: [-838515.48, -600214.20, -150432.20, 80125.50, 150450.20] },
          carbon_operational_tco2e: { baseline: [566.53, 570.10, 575.50, 590.20, 610.40], intervention: [566.53, 520.10, 480.50, 440.20, 420.15] },
          space_utilization: { baseline: [0.136, 0.12, 0.10, 0.08, 0.05], intervention: [0.136, 0.30, 0.52, 0.65, 0.682] },
          reachable_population_walk: { baseline: [0.0, 0.0, 0.0, 0.0, 0.0], intervention: [0.0, 1520.0, 3540.0, 4530.0, 4530.0] }
        }
      }
    },
    {
      asset_id: "P-VAC-07",
      summary_card: {
        financial: {
          main_metric: { label: "Annual NOI", baseline: 0.0, intervention: 128450.80, unit: "RM" },
          counterfactual: { capex_if_new_build_rm: 1500000.0, capex_if_repurpose_rm: 1500000.0, capex_saved_rm: 0.0 }
        },
        social: {
          main_metric: { label: "Space Utilization", baseline: 0.0, intervention: 0.954, unit: "ratio" },
          metrics: { coverage_ratio_5min_walk: { baseline: 0.0, intervention: 0.0 }, effective_demand_m2: { baseline: 0.0, intervention: 0.0 } }
        },
        environmental: {
          main_metrics: [{ label: "Operational Carbon", baseline: 0.0, intervention: 120.50, unit: "tCO2e/yr" }],
          counterfactual: { embodied_if_new_build_tco2e: 650.0, embodied_if_repurpose_tco2e: 0.0, net_carbon_averted_tco2e: -650.0 }
        },
        subunits: []
      },
      timeline: {
        years: ["2026", "2027", "2028", "2030", "2033"],
        metrics: {
          noi_rm: { baseline: [0, 0, 0, 0, 0], intervention: [0, -154321.0, 42150.5, 105300.2, 128450.8] },
          carbon_operational_tco2e: { baseline: [0, 0, 0, 0, 0], intervention: [0, 0, 120.5, 120.5, 120.5] }
        }
      }
    }
  ],
  township_metrics: { total_carbon_before_tco2e: 130922.25, total_carbon_after_tco2e: 131450.50, carbon_delta_pct: 0.00403 }
}

export const MOCK_SCENARIO_3: AnalyzeResult = {
  run_id: "LLM-demo-3",
  scenario_id: "SC-demo-3",
  interventions: [
    {
      target_asset_id: "BLD-0741",
      type: "repurpose",
      role: "primary",
      beneficiary_asset_id: null
    },
    {
      target_asset_id: "BLD-0661",
      type: "repurpose",
      role: "primary",
      beneficiary_asset_id: null
    },
    {
      target_asset_id: "P-VAC-09",
      type: "new_development",
      role: "catalytic",
      beneficiary_asset_id: "BLD-0741"
    }
  ],
  decision: {
    selected_candidate: "Demographic Pivot: Senior Care & Family Hub",
    reasoning: "The township is experiencing a bifurcating demographic shift. We propose a phased public-private synergy within the RM 7.5M allocation. Phase 1 executes the BLD-0741 repurpose into a medical clinic (RM1.2M) and Phase 2 deploys the P-VAC-09 senior living complex (RM6.0M) using Full Control. The combined developer CAPEX of RM 7.2M strictly respects the budget. For BLD-0661, we issue a formal recommendation to the private owner (Advisory) to fund and repurpose their aging detached house into a premium childcare centre (RM0.8M) to complete the 5-minute care loop.",
    key_trade_offs: [
      "The transformation of BLD-0661 relies entirely on the private owner's cooperation and their independent CAPEX of RM 0.8M.",
      "Executing two major developments simultaneously (RM 7.2M) leaves only RM 0.3M contingency budget for the developer."
    ],
    justification: {
      summary: "We recommend a strategic demographic pivot. Using the RM 7.5M budget, we will execute a medical clinic at BLD-0741 and a senior housing complex at P-VAC-09. We strongly recommend the private owner of BLD-0661 to convert their underperforming detached house into a childcare centre. This multi-asset synergy lifts overall precinct occupancy and stabilizes the local economy without exceeding our financial boundaries.",
      why_this_plan: "A standalone retail revival is impossible; the demand is structurally shrinking. The engine calculated that the catchment needs elderly care and childcare. Furthermore, we must respect ownership boundaries. The AI only allocates CAPEX to assets where we hold Full Control, while providing an advisory roadmap for private properties.",
      what_simulation_shows: "The new development on P-VAC-09 injects 450 new residents. At BLD-0741 (Clinic), occupancy jumps from 12.3% to 95.1%, adding RM 180k in NOI. At BLD-0661 (Childcare), if the owner adopts the recommendation, its residential occupancy metric transforms into a high-yield facility utilization rate of 85.2%, increasing asset value by over RM 1.2M.",
      beyond_the_model: "Proximity to a dedicated childcare centre drastically increases the leasing velocity of family-sized residential units nearby. The clinic and childcare share a massive parental/caregiver user base, maximizing daily footfall.",
      recommendation: "Proceed immediately with the P-VAC-09 development and BLD-0741 renovation. Formally present the BLD-0661 childcare proposal to the current property owner within Q1 2027."
    }
  },
  assets_analysis: [
    {
      asset_id: "BLD-0741",
      summary_card: {
        financial: {
          main_metric: { label: "Annual NOI", baseline: -320150.20, intervention: 180450.50, unit: "RM" },
          counterfactual: { capex_if_new_build_rm: 3500000.0, capex_if_repurpose_rm: 1200000.0, capex_saved_rm: 2300000.0 }
        },
        social: {
          main_metric: { label: "Space Utilization", baseline: 0.123, intervention: 0.951, unit: "ratio" },
          metrics: {
            coverage_ratio_5min_walk: { baseline: 0.15, intervention: 0.42 },
            effective_demand_m2: { baseline: 180.0, intervention: 1450.5 }
          }
        },
        environmental: {
          main_metrics: [
            { label: "Operational Carbon", baseline: 210.50, intervention: 180.20, unit: "tCO2e/yr" },
            { label: "Stranded Carbon", baseline: 184.50, intervention: 12.30, unit: "tCO2e/yr" }
          ],
          counterfactual: { embodied_if_new_build_tco2e: 450.0, embodied_if_repurpose_tco2e: 80.0, net_carbon_averted_tco2e: 370.0 }
        },
        subunits: []
      },
      timeline: {
        years: ["2026", "2027", "2028", "2030", "2033"],
        metrics: {
          noi_rm: { baseline: [-320150.20, -330500.10, -350210.60, -380450.30, -400120.10], intervention: [-320150.20, -250200.50, 50120.40, 150450.20, 180450.50] },
          carbon_operational_tco2e: { baseline: [210.50, 215.0, 220.0, 230.0, 240.0], intervention: [210.50, 200.0, 190.0, 185.0, 180.20] },
          space_utilization: { baseline: [0.123, 0.10, 0.08, 0.05, 0.02], intervention: [0.123, 0.40, 0.75, 0.88, 0.951] }
        }
      }
    },
    {
      asset_id: "BLD-0661",
      summary_card: {
        financial: {
          main_metric: { label: "Annual NOI", baseline: 45050.20, intervention: 210150.80, unit: "RM" },
          counterfactual: { capex_if_new_build_rm: 4200000.0, capex_if_repurpose_rm: 800000.0, capex_saved_rm: 3400000.0 }
        },
        social: {
          main_metric: { label: "Space Utilization", baseline: 0.55, intervention: 0.852, unit: "ratio" },
          metrics: {
            coverage_ratio_5min_walk: { baseline: 0.12, intervention: 0.45 },
            effective_demand_m2: { baseline: 0.0, intervention: 1600.0 }
          }
        },
        environmental: {
          main_metrics: [
            { label: "Operational Carbon", baseline: 150.20, intervention: 120.50, unit: "tCO2e/yr" },
            { label: "Stranded Carbon", baseline: 67.59, intervention: 18.07, unit: "tCO2e/yr" }
          ],
          counterfactual: { embodied_if_new_build_tco2e: 520.0, embodied_if_repurpose_tco2e: 40.0, net_carbon_averted_tco2e: 480.0 }
        },
        subunits: []
      },
      timeline: {
        years: ["2026", "2027", "2028", "2030", "2033"],
        metrics: {
          noi_rm: { baseline: [45050.20, 45120.50, 46050.40, 47020.30, 48050.10], intervention: [45050.20, 30020.50, 120400.80, 180200.50, 210150.80] },
          carbon_operational_tco2e: { baseline: [150.20, 150.0, 150.0, 150.0, 150.0], intervention: [150.20, 140.0, 130.0, 125.0, 120.50] },
          space_utilization: { baseline: [0.55, 0.55, 0.54, 0.54, 0.53], intervention: [0.55, 0.50, 0.70, 0.80, 0.852] }
        }
      }
    },
    {
      asset_id: "P-VAC-09",
      summary_card: {
        financial: {
          main_metric: { label: "Annual NOI", baseline: 0.0, intervention: 450200.50, unit: "RM" },
          counterfactual: { capex_if_new_build_rm: 6000000.0, capex_if_repurpose_rm: 6000000.0, capex_saved_rm: 0.0 }
        },
        social: {
          main_metric: { label: "Space Utilization", baseline: 0.0, intervention: 0.921, unit: "ratio" },
          metrics: { coverage_ratio_5min_walk: { baseline: 0.0, intervention: 0.0 }, effective_demand_m2: { baseline: 0.0, intervention: 0.0 } }
        },
        environmental: {
          main_metrics: [{ label: "Operational Carbon", baseline: 0.0, intervention: 320.50, unit: "tCO2e/yr" }],
          counterfactual: { embodied_if_new_build_tco2e: 2500.0, embodied_if_repurpose_tco2e: 0.0, net_carbon_averted_tco2e: -2500.0 }
        },
        subunits: []
      },
      timeline: {
        years: ["2026", "2027", "2028", "2030", "2033"],
        metrics: {
          noi_rm: { baseline: [0, 0, 0, 0, 0], intervention: [0, -150400.20, 200150.50, 400200.80, 450200.50] },
          carbon_operational_tco2e: { baseline: [0, 0, 0, 0, 0], intervention: [0, 0, 320.50, 320.50, 320.50] }
        }
      }
    }
  ],
  township_metrics: { total_carbon_before_tco2e: 130922.25, total_carbon_after_tco2e: 133400.50, carbon_delta_pct: 0.01893 }
}

export const MOCK_SCENARIO_4: AnalyzeResult = {
  run_id: "LLM-demo-4",
  scenario_id: "SC-demo-4",
  interventions: [
    {
      target_asset_id: "P-VAC-08",
      type: "new_development", // 一期：康养中心
      role: "primary",
      beneficiary_asset_id: null
    },
    {
      target_asset_id: "P-VAC-08",
      type: "delay_development", // 二期：精品酒店延期
      role: "primary",
      beneficiary_asset_id: null
    },
    {
      target_asset_id: "P-VAC-08",
      type: "interim_solar_farm", // 闲置期：太阳能补位
      role: "primary",
      beneficiary_asset_id: null
    }
  ],
  decision: {
    selected_candidate: "Phased Activation: Operational Net-Zero Retreat",
    reasoning: "The architectural blueprint proposes a combined Wellness Retreat and Boutique Resort, requiring an upfront RM 12M. Our system flags this as a high capital risk. Instead, we recommend a phased allocation: Phase 1 executes the Retreat (RM 4M) and an Interim Solar Farm (RM 1M). The Boutique Resort (RM 7M) is deferred to 2029. Based on current energy modeling, the solar farm is designed to offset the Retreat's estimated annual electricity load, targeting operational net-zero for Phase 1.",
    key_trade_offs: [
      "Defers RM 7M of Phase 2 capital to 2029, significantly reducing near-term financial exposure but postponing hotel revenue.",
      "Diverts RM 1M of the original budget to solar infrastructure, which alters the site's long-term energy layout."
    ],
    justification: {
      summary: "We recommend a phased activation. Phase 1 deploys RM 5M of the RM 12M blueprint to build the Wellness Retreat and an Interim Solar Farm. This targets operational net-zero energy for the Retreat. The remaining RM 7M hotel investment is deferred to 2029 to mitigate hospitality market risk, subject to performance review.",
      why_this_plan: "Committing the full RM 12M upfront exposes us to unnecessary stranded carbon and liquidity stress. By phasing the project, we deploy capital only as demand is validated. The solar farm eliminates the temporary land holding cost and directly serves the Retreat's heavy HVAC load.",
      what_simulation_shows: "The Retreat opens in 2027 at an estimated 85% utilization. The solar farm is projected to generate 1,200 MWh annually, balancing the Retreat's estimated energy demand. Note: these are Phase 1 operational assumptions. When the hotel opens in 2029, additional grid capacity will be required.",
      beyond_the_model: "This phased approach gives the developer leverage. If the eco-wellness market underperforms by 2028, the developer can pivot the Phase 2 hotel land into a larger commercial solar array or permanent park.",
      recommendation: "Approve the Phase 1 CAPEX immediately. Establish a gating review in Q4 2028 to evaluate the Retreat's actual ROI and energy data before committing the deferred RM 7M to Phase 2."
    }
  },
  assets_analysis: [
    {
      asset_id: "P-VAC-08",
      summary_card: {
        financial: {
          main_metric: {
            label: "Annual NOI (Phase 1)",
            baseline: 0.0,
            intervention: 450000.0, 
            unit: "RM"
          },
          counterfactual: {
            capex_if_new_build_rm: 12000000.0, // 原始规划总价
            capex_if_repurpose_rm: 5000000.0, // 实际当期执行的 Phase 1
            capex_saved_rm: 7000000.0 // 递延的 Phase 2 资本
          }
        },
        social: {
          main_metric: {
            label: "Space Utilization",
            baseline: 0.0,
            intervention: 0.85, 
            unit: "ratio"
          },
          metrics: {
            coverage_ratio_5min_walk: { baseline: 0.0, intervention: 0.0 },
            effective_demand_m2: { baseline: 0.0, intervention: 0.0 }
          }
        },
        environmental: {
          main_metrics: [
            {
              label: "Operational Carbon (Phase 1)",
              baseline: 0.0,
              intervention: 0.0,
              unit: "tCO2e/yr"
            }
          ],
          counterfactual: {
            embodied_if_new_build_tco2e: 5400.0, 
            embodied_if_repurpose_tco2e: 1800.0,
            net_carbon_averted_tco2e: 3600.0 
          }
        },
        subunits: []
      },
      timeline: {
        years: ["2026", "2027", "2028", "2030", "2033"],
        metrics: {
          noi_rm: {
            baseline: [0, 0, 0, 0, 0],
            intervention: [0, 450000.0, 480000.0, 1200000.0, 1500000.0]
          },
          carbon_operational_tco2e: {
            baseline: [0, 0, 0, 0, 0],
            intervention: [0, 0.0, 0.0, 450.0, 500.0]
          }
        }
      }
    }
  ],
  township_metrics: {
    total_carbon_before_tco2e: 130922.25,
    total_carbon_after_tco2e: 130922.25,
    carbon_delta_pct: 0.0
  }
}

export const MOCK_ANALYZE_RESULT = MOCK_SCENARIO_1