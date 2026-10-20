export type Tier = 'observed' | 'estimated' | 'scenario'

/* ---------- 1. Geometry layer: one feature in buildings.geojson ---------- */

export type BuildingProps = {
  building_id: string
  parcel_id: string
  asset_id: string
  building_type: string
  floors: number | null
  gfa_m2: number
  geometry_source: string
  id: string
  subtype: string | null
  /** Not in the export yet: derived locally from gfa_m2 and floors. */
  height?: number
}

/* ---------- 2. Diagnosis layer: one entry in deadspace_2026.json ---------- */

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
  asset_id: string
  year: number
  status: AssetStatus
  /** Flag names are open-ended: do not switch on a fixed list. */
  flags: string[]
  /** Sorting only. Never displayed. */
  urgency_index: number
  layer1: DeadspaceLayer
  layer2: DeadspaceLayer
  layer3: ActionabilityLayer
  contributing_factors: ContributingFactor[]
  /** Pre-formatted strings from B6, e.g. "Occupancy: 24.5%". Rendered as text. */
  evidence: string[]
  model_version: string
}

/* ---------- 3. The merged object the UI works with ---------- */

export type Asset = BuildingProps & {
  diagnosis: Diagnosis | null
  center: [number, number]
}

/* ---------- 4. LLM plan: one proposal per asset (v1.2 §7.2 Stage 2) ---------- */

export type Proposal = {
  asset_id: string
  type: string
  parameters: Record<string, unknown>
  expected_effects?: Record<string, number>
  rationale: string
}

export type Justification = {
  summary: string
  why_this_plan: string
  what_simulation_shows: string
  beyond_the_model: string | null
  recommendation: string
}

export type AiAnswer = {
  asked: string
  reasoning_trace: string
  plan: Proposal[]
  justification?: Justification
}

/* ---------- 5. Simulation comparison (v1.2 §6.7) ---------- */

export type MetricDelta = {
  before: number | null
  after: number | null
  unit: string
}

export type Comparison = {
  per_asset: Record<string, Record<string, MetricDelta>>
  aggregate: {
    asset_count: number
    total_carbon_before_tco2e: number
    total_carbon_after_tco2e: number
    carbon_delta_pct: number
    avoided_embodied_carbon_tco2e: number
  }
  focus_asset_id?: string
  metrics?: Record<string, MetricDelta>
  township_metrics: {
    walk_15min_avg_coverage_before: number
    walk_15min_avg_coverage_after: number
    walk_15min_coverage_delta: number
    total_carbon_before_tco2e: number
    total_carbon_after_tco2e: number
    carbon_delta_pct: number
    project_carbon_after_tco2e: number
    project_carbon_cumulative_tco2e: number
  }
}

export type MapDiffEntry = {
  asset_id: string
  change_type: string
  color: string
}

export type MapDiff = {
  changed_assets: MapDiffEntry[]
  spillover_assets: MapDiffEntry[]
  negative_assets: MapDiffEntry[]
  project_schedule: Array<{
    project_id: string
    baseline_delivery_year: number
    scenario_delivery_year: number
    delta_years: number
    status: string
  }>
}