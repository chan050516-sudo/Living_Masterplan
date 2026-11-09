export type Tier = 'observed' | 'estimated' | 'scenario'
export type DataTier = 1 | 2 | '3a' | '3b'

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
  }
  authority: {
    level: string
    ownership_status: string
  }
  financial: {
    capex_initial_rm: number | null
    opex_annual_rm: number | null
    maintenance_annual_rm: number | null
    rental_income_rm: number | null
    noi_rm: number | null
    noi_yield: number | null
    dsr: number | null
  }
  social: {
    occupancy_rate: number | null
    utilisation_rate: number | null
    footfall_daily: number | null
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
  subunits: unknown[] | null
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