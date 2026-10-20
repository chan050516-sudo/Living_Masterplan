export type Tier = 'observed' | 'estimated' | 'scenario'

/* ---------- Diagnosis (B6) ---------- */

export type AssetStatus =
  | 'healthy'
  | 'monitor'
  | 'deadspace_candidate'
  | 'underperforming_facility'
  | 'development_risk'
  | 'improvement_opportunity'

export type DeadspaceLayer = {
  triggered: boolean
  reasons: string[]
}

export type ActionabilityLayer = {
  actionable: boolean
  candidate_interventions: string[]
}

export type ContributingFactor = {
  factor: string
  contribution: number
}

export type Diagnosis = {
  asset_id?: string
  year?: number
  status: AssetStatus
  /** Flag names are open-ended: do not switch on a fixed list. */
  flags: string[]
  /** Sorting only. Never displayed. */
  urgency_index: number
  layer1?: DeadspaceLayer
  layer2?: DeadspaceLayer
  layer3?: ActionabilityLayer
  contributing_factors: ContributingFactor[]
  /** Pre-formatted strings from B6, e.g. "Occupancy: 24.5%". */
  evidence: string[]
  model_version?: string
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
    surface_temp_delta_c: number | null
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
  /** Metres, derived from floors for 3D extrusion. 0 for points and flat shapes. */
  height: number
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
  baseline: number | null
  intervention: number | null
  unit: string
}

export type AssetAnalysis = {
  asset_id: string
  summary_card: {
    financial?: {
      main_metric?: MainMetric
      counterfactual?: Record<string, number>
    }
    social?: {
      main_metric?: MainMetric
      metrics?: Record<string, { baseline: number; intervention: number }>
    }
    environmental?: {
      main_metrics?: MainMetric[]
      counterfactual?: Record<string, number>
    }
    subunits?: Array<Record<string, unknown>>
  }
  timeline?: {
    years: string[]
    metrics: Record<string, { baseline: number[]; intervention: number[] }>
  }
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
  township_metrics: {
    total_carbon_before_tco2e: number
    total_carbon_after_tco2e: number
    carbon_delta_pct: number
  }
}