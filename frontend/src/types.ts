export type Tier = 'observed' | 'estimated' | 'scenario'
/** Data tier as served by the backend (field_metadata.yml). Numbers are
 *  accepted for the analyze payload, which still sends 1 / 2 as numbers. */
export type DataTier = 1 | 2 | '1' | '2' | '3a' | '3b' | 'U'

/** One entry of AssetProfile.tiers, keyed by "<section>.<field>". */
export type ServedTier = {
  tier: '1' | '2' | '3a' | '3b' | 'U'
  source: string | null
  mock?: boolean
}

/** Per-subtype row of a mixed-use asset (profile.subunits). */
export type Subunit = {
  subtype: string
  area_m2: number | null
  design_count: number | null
  /** Observed occupancy, owned assets only. */
  occupancy: number | null
  /** Google Places proxies, sold assets only. */
  operational_count: number | null
  presence_ratio: number | null
  vitality_score: number | null
  allocated_carbon_tco2e: number | null
  allocated_noi_rm: number | null
}

/* ---------- Diagnosis (B6) ---------- */

export type AssetStatus =
  | 'healthy'
  | 'monitor'
  | 'deadspace_candidate'
  | 'underperforming_facility'
  | 'development_risk'
  | 'improvement_opportunity'
  | 'community_value_gap'
  | 'strategic_learning'
  | 'intervened'

export type InterventionMode = 'direct' | 'collaborative' | 'advisory'

export type DeadspaceLayer = {
  triggered: boolean
  reasons: string[]
}

export type ActionabilityLayer = {
  has_legal_actions?: boolean
  actionable: boolean
  candidate_interventions: string[]
  diagnosis_active?: boolean
  reason?: string
}

export type ContributingFactor = {
  factor: string
  contribution: number
}

export type Layer3a = {
  proxied_occupancy: number | null
  proxied_occupancy_source: string | null
  triggered: boolean | null
  reasons: string[]
  flow_island_threshold: number | null
}

export type Diagnosis = {
  asset_id?: string
  year?: number
  status: AssetStatus
  flags: string[]
  urgency_index: number
  intervention_mode?: InterventionMode
  layer1?: DeadspaceLayer
  layer2?: DeadspaceLayer
  layer3?: ActionabilityLayer
  contributing_factors: ContributingFactor[]
  evidence: string[]
  model_version?: string
  authority?: string
  evaluation_mode?: string
  flag_tiers?: Record<string, string>
  layer3a?: Layer3a | null
}

/* ---------- API: /api/assets/profiles ---------- */

export type AssetProfile = {
  identity: {
    asset_id: string
    asset_name: string
    asset_type: string
    subtype: string | null
    land_use: string
    status: string
    completion_year: number | null
  }
  physical: {
    floor_area_m2: number | null
    lettable_area_m2: number | null
    land_area_m2: number | null
    capacity: number | null
    unit_count?: number | null
    developer_held_units?: number | null
    developable_area_m2?: number | null
    potential_gfa_m2?: number | null
  }
  authority: {
    level: string
    ownership_status: string
    data_confidence?: string | null
  }
  financial: {
    capex_initial_rm: number | null
    opex_annual_rm: number | null
    maintenance_annual_rm: number | null
    rental_income_rm: number | null
    noi_rm: number | null
    noi_yield: number | null
    dsr: number | null
    sale_price_rm?: number | null
    sale_date?: string | null
    sale_data_source?: string | null
    sale_profit_rm?: number | null
    sale_return_ratio?: number | null
    estimated_revenue_rm?: number | null
    survival_opex_floor_rm?: number | null
    hemorrhage_ratio?: number | null
    cost_per_user_rm?: number | null
    demand_supply_gap?: number | null
    infrastructure_cost_rm?: number | null
  }
  social: {
    occupancy_rate: number | null
    utilisation_rate: number | null
    footfall_daily: number | null
    vacancy_duration_months?: number | null
    occupied_units?: number | null
    service_coverage?: number | null
    coverage_ratio_10min_drive?: number | null
    coverage_ratio_5min_walk: number | null
    coverage_ratio_10min_walk: number | null
    coverage_ratio_15min_walk: number | null
    reachable_population_walk: number | null
    effective_demand_m2: number | null
    demographic_mismatch: number | null
    neighborhood_diversity: number | null
    // Tier-3a proxy fields (sold/advisory only)
    proxied_occupancy?: number | null
    proxied_occupancy_source?: string | null
    external_demand_ratio?: number | null
    lbs_unique_users_daily?: number | null
    lbs_dwell_minutes?: number | null
    business_presence_ratio?: number | null
    lbs_visit_frequency_monthly?: number | null
    proxied_occupancy_lbs?: number | null
    flow_island_ratio?: number | null
    traffic_exposure_vpd?: number | null
    proxied_occupancy_google?: number | null
    operational_place_count?: number | null
    unit_mix_unit_count?: number | null
    business_vitality_score?: number | null
    proxied_vacancy_duration?: number | null
    business_turnover_count?: number | null
  }
  environmental: {
    carbon_operational_tco2e: number | null
    carbon_productive_tco2e: number | null
    carbon_stranded_tco2e: number | null
    stranded_carbon_ratio: number | null
    embodied_carbon_tco2e: number | null
    energy_kwh_total: number | null
    energy_kwh_hvac: number | null
    energy_kwh_lighting: number | null
    energy_kwh_base_load: number | null
    t_asset_c: number | null
    t_township_c: number | null
    surface_temp_delta_c: number | null
    apparent_temp_c: number | null
    surface_temp_provenance: string | null
    surface_temp_collection_id: string | null
    surface_temp_band: string | null
    surface_temp_source_catalog: string | null
    surface_temp_valid_pixel_count: number | null
    surface_temp_period_start: string | null
    surface_temp_period_end: string | null
    surface_temp_source_image_count: number | null
    green_coverage?: number | null
    canopy_coverage?: number | null
    green_per_capita_m2?: number | null
  }
  trajectory: {
    class: string | null
    peak_occupancy: number | null
    years_since_peak: number | null
    occupancy_trend_3yr: number | null
    vacancy_streak_months: number | null
  } | null
  deadspace_diagnosis: Diagnosis | null
  leases: Record<string, unknown> | null
  subunits: Subunit[] | null
  /** Tier + source of every non-null metric, resolved for this asset's authority. */
  tiers?: Record<string, ServedTier>
}

/** How a value from a simulated year (/api/map/geometry metrics_json)
 *  replaces the 2026 profile value. Built by applyYearMetrics(). */
export type MetricOverride = {
  year: number
  tier: ServedTier['tier']
  /** Short qualifier appended to the label, e.g. "estimated". */
  qualifier: string
  /** Where the value came from, shown in the tier tooltip. */
  source: string
}

/* ---------- The merged object the UI works with ---------- */

export type Asset = {
  id: string
  name: string
  subtype: string | null
  assetType: string
  mapStatus: string
  profile: AssetProfile | null
  diagnosis: Diagnosis | null
  center: [number, number]
  height: number
  /** Year the currently loaded diagnosis actually comes from. Differs
   *  from the selected year when the backend fell back to 2026. */
  diagnosisYear?: number | null
  /** Year selected in the UI when this asset list was built. */
  selectedYear?: number
  /** Profile paths whose value was replaced by a simulated-year value. */
  metricOverrides?: Record<string, MetricOverride>
}

/* ---------- API: /api/analyze ---------- */

export type Justification = {
  summary: string
  why_this_plan: string
  what_simulation_shows: string
  beyond_the_model: string | null
  recommendation: string
}

export type MainMetric = {
  label: string
  baseline?: number | null
  intervention?: number | null
  value?: number | null       // for counterfactual "single-value" metrics
  unit: string
  tier?: DataTier
  // Surface Temp attribution
  cooling_from_canopy_c?: number | null
  cooling_from_roof_c?: number | null
  cooling_source?: string
}

export type EngineeringSpec = {
  structure_retention_ratio: number | null
  facade_action: string | null
  primary_material: string | null
  roof_intervention: string | null
  hvac_cop: number | null
  operating_hours_per_week: number | null
  rooftop_pv_coverage: number | null
  pv_yield_kwh_year: number | null
}

export type Observed2026 = {
  surface_temp_delta_c: number | null
  t_asset_c: number | null
  t_township_c: number | null
  label: string
}

export type LBSBlock = {
  unique_users: { baseline: number | null; intervention: number | null }
  dwell_minutes: number | null
  flow_island_ratio: number | null
  tier: string
  source: string | null
}

export type CommunityBlock = {
  lbs: LBSBlock
  business_presence_ratio: number | null
  business_turnover_count: number | null
  occupancy_seed_source: string | null
}

export type CounterfactualMetric = {
  label: string
  value: number | null
  unit: string
  tier: DataTier
}

export type CounterfactualBlock = {
  label: string
  metrics: CounterfactualMetric[]
}

export type SummaryCard = {
  financial?: {
    main_metric?: MainMetric
    counterfactual?: Record<string, number>
  }
  social?: {
    main_metric?: MainMetric
    metrics?: Record<string, { baseline: number | null; intervention: number | null }>
  }
  environmental?: {
    observed_2026?: Observed2026
    main_metrics?: MainMetric[]
    counterfactual?: Record<string, number>
  }
  subunits?: Array<{
    subtype: string
    area_m2: number
    design_count?: number
    operational_count?: number
    presence_ratio?: number
    vitality_score?: number | null
    occupancy?: number | null // Keep for backward compatibility if needed
    allocated_carbon_tco2e?: number
    allocated_noi_rm?: number
  }> | null
  authority?: string
  evaluation_mode?: string
  community?: CommunityBlock
  counterfactual?: CounterfactualBlock | null
}

export type AssetAnalysis = {
  asset_id: string
  engineering_spec?: EngineeringSpec | null
  summary_card: SummaryCard
  timeline?: {
    years: string[]
    metrics: Record<string, { baseline: number[]; intervention: number[] }>
  }
}

export type TownshipMetrics = {
  walk_15min_avg_coverage_before: number | null
  walk_15min_avg_coverage_after: number | null
  walk_15min_coverage_delta: number | null
  total_carbon_before_tco2e: number | null
  total_carbon_after_tco2e: number | null
  carbon_delta_pct: number | null
  project_carbon_after_tco2e: number | null
  project_carbon_cumulative_tco2e: number | null
  sequestration_by_year_tco2e_year: Record<string, number>
  sequestration_before_tco2e_year: number | null
  sequestration_after_tco2e_year: number | null
  sequestration_delta_tco2e_year: number | null
  sequestration_cumulative_tco2e: number | null
  canopy_uptake_rate_tco2e_per_m2_year: number | null
  operational_carbon_by_year_tco2e_year: Record<string, number | null>
  net_carbon_by_year_tco2e_year: Record<string, number | null>
}

export type CandidateSummary = {
  name: string
  strategy_summary: string
  plan: Array<{ asset_id: string; type: string; role?: string }>
}

export type AnalyzeResult = {
  run_id: string
  scenario_id: string
  decision: {
    selected_candidate: string
    reasoning: string
    key_trade_offs: string[]
    justification: Justification
  }
  assets_analysis: AssetAnalysis[]
  township_metrics: TownshipMetrics
  candidates_summary?: CandidateSummary[]
  project_schedule?: any[]
  interventions?: Array<{
    target_asset_id: string
    type: string
    role: 'primary' | 'catalytic'
    beneficiary_asset_id?: string | null
  }>
}