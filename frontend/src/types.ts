import type { Feature, FeatureCollection, Geometry } from 'geojson'

export type Tier = 'observed' | 'estimated' | 'scenario'

// ---- GET /api/map/geometry ----

export type MapStatus =
  | 'healthy'
  | 'deadspace_candidate'
  | 'monitor'
  | 'underperforming_facility'
  | 'development_risk'
  | 'improvement_opportunity'
  | 'intervened'
  | 'vacant'

// Buildings, parcels and green areas are polygons; some amenities are points
// and some blue features (rivers, drains) are lines.
export type MapFeature = Feature<Geometry, {
  asset_id: string | null
  map_status: MapStatus
  height_m: number | null
}>

export type MapGeometry = FeatureCollection<MapFeature['geometry'], MapFeature['properties']>

// ---- GET /api/assets/profiles ----

export type Factor = { factor: string; contribution: number }

export type Subunit = {
  subtype: string
  area_m2: number
  occupancy: number | null
  allocated_carbon_tco2e: number | null
  allocated_noi_rm: number | null
}

export type AssetProfile = {
  identity: {
    asset_id: string
    asset_name: string
    asset_type: string
    subtype: string | null
    land_use: string | null
    status: string | null
    completion_year: number | null
  }
  physical: {
    floor_area_m2: number | null
    lettable_area_m2: number | null
    land_area_m2: number | null
    capacity: number | null
  }
  authority: { level: string | null; ownership_status: string | null }
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
    surface_temp_delta_c: number | null
  }
  trajectory: {
    class: string | null
    peak_occupancy: number | null
    years_since_peak: number | null
    occupancy_trend_3yr: number | null
    vacancy_streak_months: number | null
  }
  deadspace_diagnosis: {
    status: MapStatus
    flags: string[]
    urgency_index: number | null
    contributing_factors: Factor[]
    evidence: string[]
  }
  leases: { anchor_lease?: { end_year: number; floor_area_m2: number } } | null
  subunits: Subunit[] | null
}

export type AssetProfiles = Record<string, AssetProfile>

// ---- POST /api/analyze ----

export type BeforeAfter = { baseline: number; intervention: number }
export type MainMetric = BeforeAfter & { label: string; unit: string }

export type AssetAnalysis = {
  asset_id: string
  summary_card: {
    financial: {
      main_metric: MainMetric
      counterfactual: { capex_if_new_build_rm: number; capex_if_repurpose_rm: number; capex_saved_rm: number }
    }
    social: {
      main_metric: MainMetric
      metrics: Record<string, BeforeAfter>
    }
    environmental: {
      main_metrics: MainMetric[]
      counterfactual: { embodied_if_new_build_tco2e: number; embodied_if_repurpose_tco2e: number; net_carbon_averted_tco2e: number }
    }
    subunits: Array<{
      subtype: string
      area_m2: number
      occupancy_baseline: number
      occupancy_intervention: number
      allocated_carbon_tco2e: number
      allocated_noi_rm: number
    }> | null
  }
  timeline: {
    years: string[]
    metrics: Record<string, { baseline: number[]; intervention: number[] }>
  }
}

export type PlanItem = { asset_id?: string; type?: string; [k: string]: unknown }

export type AnalyzeResult = {
  run_id: string
  scenario_id: string | null
  decision: {
    selected_candidate: string | null
    reasoning: string
    key_trade_offs: string[]
    justification: {
      summary: string
      why_this_plan: string
      what_simulation_shows: string
      beyond_the_model: string | null
      recommendation: string
    }
  }
  assets_analysis: AssetAnalysis[]
  township_metrics: Record<string, number>
  candidates_summary?: Array<{ name: string; strategy_summary: string; plan: PlanItem[] }>
}
