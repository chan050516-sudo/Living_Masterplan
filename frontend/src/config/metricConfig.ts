// Single source of truth for how asset metrics are shown.
//
//   METRICS        profile path -> label, pillar, format (and display rules)
//   CORE_METRICS   asset type x authority group -> the 4 core metric paths
//                  (docs/metrics_matrix.md, "Proposed top-4 core metrics")
//   YEAR_METRICS   which simulated-year values replace profile values, and
//                  how they are re-tiered (see applyYearMetrics)
//
// Tiers are NOT configured here: they are served per asset by the backend
// (profile.tiers, resolved from backend/configs/field_metadata.yml).
// Components must not branch on asset type or authority for metric display;
// add a rule here instead.

import type { Asset, AssetProfile, MetricOverride, ServedTier } from '../types'

export type Pillar = 'Physical' | 'Environmental' | 'Financial' | 'Social'
export const PILLARS: Pillar[] = ['Physical', 'Environmental', 'Financial', 'Social']

export type Format =
  | 'ratio'   // 0.42 -> 42%
  | 'rm'      // RM 1,234,567
  | 'int'     // 1,235
  | 'dec1' | 'dec2'
  | 'area'    // 1,235 m²
  | 'tco2e'   // 865.4 tCO₂e
  | 'kwh'
  | 'degC'    // 40.2 °C
  | 'deltaC'  // +0.88 °C
  | 'months' | 'years' | 'minutes'
  | 'perDay'
  | 'text'    // snake_case -> Sentence case
  | 'date'
  | 'year'    // 2003 (no separator)

export type MetricDef = {
  label: string
  pillar: Pillar
  format: Format
  /** Unit text shown after the value (the formatter supplies it for most formats). */
  unit?: string
  /** Only shown for these asset types (e.g. unit counts for residential). */
  types?: string[]
  /** Treat 0 as "no data" (e.g. floor area of an undeveloped parcel). */
  hideZero?: boolean
  /** Shown in ExternalSignalsPanel, so left out of the pillar lists. */
  signalsPanel?: boolean
  /** Value is worth flagging red. */
  warn?: (v: number) => boolean
  hint?: string
  /** Human labels for enum values (format 'text'). */
  valueLabels?: Record<string, string>
}

const BUILDING_TYPES = ['commercial', 'residential', 'community_facility']

// ------------------------------------------------------------------
// Human labels. Nothing raw (snake_case) reaches the screen: every enum
// shown in the panel goes through one of these maps, and anything not
// listed falls back to humanize().
// ------------------------------------------------------------------

/** Words that are always upper-case when humanized. */
const ACRONYMS: Record<string, string> = {
  noi: 'NOI', dsr: 'DSR', lbs: 'LBS', uhi: 'UHI', gfa: 'GFA', capex: 'CAPEX',
  opex: 'OPEX', rm: 'RM', jmb: 'JMB', sdp: 'SDP', id: 'ID',
}

/** snake_case -> "Sentence case", keeping acronyms ("negative_noi" -> "Negative NOI"). */
export function humanize(raw: string): string {
  const words = raw.replace(/_/g, ' ').trim().split(/\s+/)
  const out = words.map((w, i) => {
    const lower = w.toLowerCase()
    if (ACRONYMS[lower]) return ACRONYMS[lower]
    return i === 0 ? lower.charAt(0).toUpperCase() + lower.slice(1) : lower
  })
  return out.join(' ')
}

const fromMap = (map: Record<string, string>) => (raw: string | null | undefined): string =>
  raw ? map[raw] ?? humanize(raw) : ''

export const ASSET_TYPE_LABELS: Record<string, string> = {
  commercial: 'Commercial',
  residential: 'Residential',
  community_facility: 'Community facility',
  green_space: 'Green space',
  undeveloped_parcel: 'Undeveloped parcel',
}

export const SUBTYPE_LABELS: Record<string, string> = {
  f_and_b: 'F&B',
  convenience_retail: 'Convenience retail',
  medical_retail: 'Medical retail',
  other_commercial: 'Other commercial',
  apartment_lowrise: 'Low-rise apartment',
  apartment_highrise: 'High-rise apartment',
  semidetached: 'Semi-detached',
  affordable_housing: 'Affordable housing',
  community_hall: 'Community hall',
  place_of_worship: 'Place of worship',
  sports_centre: 'Sports centre',
  public_service: 'Public service',
  pocket_park: 'Pocket park',
  green_corridor: 'Green corridor',
  sports_field: 'Sports field',
  water_body: 'Water body',
  solar_farm: 'Solar farm',
  vacant: 'Vacant land',
}

export const STATUS_LABELS: Record<string, string> = {
  healthy: 'Healthy',
  monitor: 'Monitor',
  deadspace_candidate: 'Deadspace candidate',
  underperforming_facility: 'Underperforming facility',
  development_risk: 'Development risk',
  improvement_opportunity: 'Improvement opportunity',
  community_value_gap: 'Community value gap',
  strategic_learning: 'Strategic learning',
  intervened: 'Intervened',
}

export const MODE_LABELS: Record<string, string> = {
  direct: 'Direct',
  collaborative: 'Collaborative',
  advisory: 'Advisory',
}

export const TRAJECTORY_LABELS: Record<string, string> = {
  rapid_decline: 'Rapid decline',
  recent_failure: 'Recent failure',
  declining: 'Declining',
  chronic_low: 'Chronic low',
  stable: 'Stable',
  recovering: 'Recovering',
  never_alive: 'Never occupied',
  unknown: 'Unknown',
}

/** Every flag tiers.py can raise, in plain words. */
export const FLAG_LABELS: Record<string, string> = {
  low_occupancy: 'Low occupancy',
  below_benchmark_occupancy: 'Occupancy below subtype benchmark',
  long_vacancy: 'Long vacancy',
  negative_noi: 'Negative NOI',
  noi_yield_below: 'NOI yield below target',
  maintenance_surge_high: 'Maintenance cost surge',
  subtype_mix_dead: 'Dead units in the subtype mix',
  subtype_mix_low: 'Weak units in the subtype mix',
  built_value_not_realized: 'Built but not occupied',
  rapid_decline: 'Rapid occupancy decline',
  falling_from_healthy: 'Falling from a healthy peak',
  chronic_stagnation: 'Chronically below benchmark',
  low_utilisation: 'Low utilisation',
  dsr_below_threshold: 'Demand below supply',
  walking_accessibility_deficit: 'Poor walking access',
  driving_accessibility_deficit: 'Poor driving access',
  demographic_mismatch: 'Poor fit with local demographics',
  low_neighborhood_diversity: 'Low neighbourhood diversity',
  high_uhi_exposure: 'Urban heat hot spot',
  uhi_data_anomaly: 'Surface temperature anomaly',
  high_stranded_carbon: 'High stranded carbon',
  high_stranded_carbon_ratio_small_asset: 'High stranded carbon share',
  low_green_coverage: 'Low green coverage',
  low_canopy_coverage: 'Low tree canopy',
  low_green_per_capita: 'Too little green space per resident',
  negative_demand_supply_gap: 'More supply planned than demand',
  weak_future_demand: 'Weak future demand',
  insufficient_coverage: 'Serves too few residents',
  low_accessibility: 'Hard to reach on foot',
  low_accessibility_high_ecological_value: 'Hard to reach, high ecological value',
  low_occupancy_proxied: 'Low occupancy (estimated)',
  long_vacancy_proxied: 'Long vacancy (estimated)',
  business_presence_low: 'Few operating businesses',
  business_turnover_high: 'High business turnover',
  business_vitality_low: 'Low business vitality',
  low_footfall_lbs: 'Low foot traffic',
  short_dwell_lbs: 'Short visits',
  flow_island: 'Cut off from nearby foot traffic',
  operating_hemorrhage: 'Revenue below survival cost',
  data_conflict: 'Proxy sources disagree',
  noi_negative_counterfactual: 'Negative NOI if retained',
}

export const assetTypeLabel = fromMap(ASSET_TYPE_LABELS)
export const subtypeLabel = fromMap(SUBTYPE_LABELS)
export const statusLabel = fromMap(STATUS_LABELS)
export const modeLabel = fromMap(MODE_LABELS)
export const flagLabel = fromMap(FLAG_LABELS)

// Order within a pillar follows the order here.
export const METRICS: Record<string, MetricDef> = {
  // ---------------- Physical ----------------
  'physical.floor_area_m2': { label: 'Floor area', pillar: 'Physical', format: 'area', hideZero: true },
  'physical.lettable_area_m2': { label: 'Lettable area', pillar: 'Physical', format: 'area', hideZero: true },
  'physical.land_area_m2': { label: 'Land area', pillar: 'Physical', format: 'area', hideZero: true },
  'physical.developable_area_m2': { label: 'Developable area', pillar: 'Physical', format: 'area' },
  'physical.potential_gfa_m2': { label: 'Buildable floor area (GFA)', pillar: 'Physical', format: 'area' },
  'physical.capacity': { label: 'Design capacity', pillar: 'Physical', format: 'int', hideZero: true },
  'physical.unit_count': { label: 'Units', pillar: 'Physical', format: 'int', types: ['residential'] },
  'physical.developer_held_units': { label: 'Unsold units (developer-held)', pillar: 'Physical', format: 'int', types: ['residential'] },
  'identity.completion_year': { label: 'Completed', pillar: 'Physical', format: 'year' },

  // ---------------- Environmental ----------------
  'environmental.surface_temp_delta_c': {
    label: 'Surface temp vs township', pillar: 'Environmental', format: 'deltaC',
    warn: (v) => v >= 3, hint: 'Landsat LST; ≥ +3.0 °C raises high_uhi_exposure',
  },
  'environmental.t_asset_c': { label: 'Surface temp (parcel)', pillar: 'Environmental', format: 'degC' },
  'environmental.t_township_c': { label: 'Surface temp (township)', pillar: 'Environmental', format: 'degC' },
  'environmental.apparent_temp_c': { label: 'Felt temperature', pillar: 'Environmental', format: 'degC' },
  'environmental.canopy_coverage': { label: 'Canopy coverage', pillar: 'Environmental', format: 'ratio' },
  'environmental.green_coverage': { label: 'Green coverage', pillar: 'Environmental', format: 'ratio' },
  'environmental.green_per_capita_m2': { label: 'Green space per resident', pillar: 'Environmental', format: 'dec1', unit: 'm²/person' },
  'environmental.carbon_operational_tco2e': { label: 'Operational carbon', pillar: 'Environmental', format: 'tco2e', unit: 'tCO₂e/yr' },
  'environmental.carbon_stranded_tco2e': { label: 'Stranded carbon', pillar: 'Environmental', format: 'tco2e', unit: 'tCO₂e/yr' },
  'environmental.stranded_carbon_ratio': {
    label: 'Stranded carbon share', pillar: 'Environmental', format: 'ratio', warn: (v) => v > 0.5,
  },
  'environmental.carbon_productive_tco2e': { label: 'Productive carbon', pillar: 'Environmental', format: 'tco2e', unit: 'tCO₂e/yr' },
  'environmental.embodied_carbon_tco2e': { label: 'Embodied carbon', pillar: 'Environmental', format: 'tco2e', unit: 'tCO₂e' },
  'environmental.energy_kwh_total': { label: 'Energy use', pillar: 'Environmental', format: 'kwh', unit: 'kWh/yr' },
  'environmental.energy_kwh_hvac': { label: 'Energy · cooling', pillar: 'Environmental', format: 'kwh', unit: 'kWh/yr' },
  'environmental.energy_kwh_lighting': { label: 'Energy · lighting & equipment', pillar: 'Environmental', format: 'kwh', unit: 'kWh/yr' },
  'environmental.energy_kwh_base_load': { label: 'Energy · base load', pillar: 'Environmental', format: 'kwh', unit: 'kWh/yr' },

  // ---------------- Financial ----------------
  'financial.noi_rm': { label: 'Net operating income', pillar: 'Financial', format: 'rm', unit: '/yr', warn: (v) => v < 0 },
  'financial.noi_yield': { label: 'NOI yield', pillar: 'Financial', format: 'ratio', warn: (v) => v < 0 },
  'financial.rental_income_rm': { label: 'Rental income', pillar: 'Financial', format: 'rm', unit: '/yr' },
  'financial.dsr': { label: 'Demand / supply ratio', pillar: 'Financial', format: 'dec2', warn: (v) => v < 0.8 },
  'financial.hemorrhage_ratio': {
    label: 'Revenue / survival cost', pillar: 'Financial', format: 'dec2', warn: (v) => v < 1,
    hint: 'Estimated revenue divided by the minimum cost to stay open; below 1 raises operating_hemorrhage',
  },
  'financial.estimated_revenue_rm': { label: 'Estimated revenue', pillar: 'Financial', format: 'rm', unit: '/yr' },
  'financial.survival_opex_floor_rm': { label: 'Survival cost floor', pillar: 'Financial', format: 'rm', unit: '/yr' },
  'financial.sale_price_rm': { label: 'Sale price', pillar: 'Financial', format: 'rm', signalsPanel: true },
  'financial.sale_date': { label: 'Sold on', pillar: 'Financial', format: 'date', signalsPanel: true },
  'financial.sale_profit_rm': { label: 'Profit vs build cost', pillar: 'Financial', format: 'rm', signalsPanel: true, warn: (v) => v < 0 },
  'financial.sale_return_ratio': { label: 'Return on build cost', pillar: 'Financial', format: 'ratio', signalsPanel: true, warn: (v) => v < 0 },
  'financial.demand_supply_gap': {
    label: 'Demand – supply gap', pillar: 'Financial', format: 'area', warn: (v) => v < 0,
    hint: 'Negative means more supply planned than demand; raises negative_demand_supply_gap',
  },
  'financial.infrastructure_cost_rm': { label: 'Infrastructure cost', pillar: 'Financial', format: 'rm' },
  'financial.cost_per_user_rm': { label: 'Cost per user', pillar: 'Financial', format: 'rm' },
  'financial.capex_initial_rm': { label: 'Build cost (CAPEX)', pillar: 'Financial', format: 'rm', hideZero: true },
  'financial.opex_annual_rm': { label: 'Operating cost', pillar: 'Financial', format: 'rm', unit: '/yr', hideZero: true },
  'financial.maintenance_annual_rm': { label: 'Maintenance cost', pillar: 'Financial', format: 'rm', unit: '/yr', hideZero: true },
  'financial.maintenance_surge_rm': { label: 'Maintenance this year', pillar: 'Financial', format: 'rm', hideZero: true },

  // ---------------- Social ----------------
  'social.occupancy_rate': { label: 'Occupancy', pillar: 'Social', format: 'ratio', warn: (v) => v < 0.5 },
  'social.proxied_occupancy': { label: 'Occupancy (estimated)', pillar: 'Social', format: 'ratio', warn: (v) => v < 0.5 },
  'social.utilisation_rate': { label: 'Utilisation', pillar: 'Social', format: 'ratio', warn: (v) => v < 0.4 },
  'social.service_coverage': { label: 'Service coverage', pillar: 'Social', format: 'ratio', warn: (v) => v < 0.6 },
  'social.occupied_units': { label: 'Occupied units', pillar: 'Social', format: 'int', types: ['residential'] },
  'social.vacancy_duration_months': { label: 'Vacant for', pillar: 'Social', format: 'months', warn: (v) => v > 12 },
  'social.footfall_daily': { label: 'Daily footfall', pillar: 'Social', format: 'perDay' },
  'social.business_presence_ratio': {
    label: 'Units with an operating business', pillar: 'Social', format: 'ratio', signalsPanel: true, warn: (v) => v < 0.3,
  },
  'social.flow_island_ratio': {
    label: 'Flow-island ratio', pillar: 'Social', format: 'dec2', signalsPanel: true, warn: (v) => v < 0.3,
    hint: 'Share of nearby footfall that reaches the asset; below 0.3 means network-isolated',
  },
  'social.lbs_unique_users_daily': { label: 'Daily unique visitors', pillar: 'Social', format: 'perDay', signalsPanel: true },
  'social.lbs_dwell_minutes': { label: 'Average stay', pillar: 'Social', format: 'minutes', signalsPanel: true },
  'social.proxied_occupancy_lbs': { label: 'Occupancy estimated from footfall', pillar: 'Social', format: 'ratio', signalsPanel: true },
  'social.traffic_exposure_vpd': { label: 'Passing traffic', pillar: 'Social', format: 'int', unit: 'vehicles/day', signalsPanel: true },
  'social.operational_place_count': { label: 'Operating businesses', pillar: 'Social', format: 'int', signalsPanel: true },
  'social.unit_mix_unit_count': { label: 'Consumer-facing units', pillar: 'Social', format: 'int', signalsPanel: true },
  'social.business_vitality_score': { label: 'Business vitality', pillar: 'Social', format: 'dec2', signalsPanel: true },
  'social.proxied_vacancy_duration': { label: 'Estimated vacancy', pillar: 'Social', format: 'months', signalsPanel: true },
  'social.business_turnover_count': { label: 'Business turnover', pillar: 'Social', format: 'int', signalsPanel: true },
  'social.external_demand_ratio': { label: 'Visitors / capacity', pillar: 'Social', format: 'ratio' },
  'social.lbs_visit_frequency_monthly': { label: 'Visits per visitor', pillar: 'Social', format: 'dec1', unit: '/month' },
  'social.proxied_occupancy_google': { label: 'Occupancy estimated from listings', pillar: 'Social', format: 'ratio' },
  'social.coverage_ratio_5min_walk': { label: 'Walk coverage · 5 min', pillar: 'Social', format: 'ratio' },
  'social.coverage_ratio_10min_walk': { label: 'Walk coverage · 10 min', pillar: 'Social', format: 'ratio' },
  'social.coverage_ratio_15min_walk': { label: 'Walk coverage · 15 min', pillar: 'Social', format: 'ratio' },
  'social.coverage_ratio_10min_drive': { label: 'Drive coverage · 10 min', pillar: 'Social', format: 'ratio' },
  'social.reachable_population_walk': { label: 'Residents within walking reach', pillar: 'Social', format: 'int' },
  'social.effective_demand_m2': { label: 'Effective demand', pillar: 'Social', format: 'area' },
  'social.demographic_mismatch': { label: 'Demographic mismatch', pillar: 'Social', format: 'dec2', warn: (v) => v > 0.4 },
  'social.neighborhood_diversity': { label: 'Neighbourhood diversity', pillar: 'Social', format: 'dec2', warn: (v) => v < 0.3 },
  'social.median_walk_distance_m': { label: 'Median walk to reach it', pillar: 'Social', format: 'int', unit: 'm' },
  'trajectory.class': { label: 'Occupancy trajectory', pillar: 'Social', format: 'text', valueLabels: TRAJECTORY_LABELS },
  'trajectory.years_below_benchmark': { label: 'Years below benchmark', pillar: 'Social', format: 'years' },
  'trajectory.peak_occupancy': { label: 'Peak occupancy', pillar: 'Social', format: 'ratio' },
  'trajectory.years_since_peak': { label: 'Years since peak', pillar: 'Social', format: 'years' },
  'trajectory.occupancy_trend_3yr': { label: '3-year occupancy trend', pillar: 'Social', format: 'ratio' },
  'trajectory.vacancy_streak_months': { label: 'Vacancy streak', pillar: 'Social', format: 'months' },
}

// Restrict building-only metrics without repeating the list above.
for (const k of ['environmental.energy_kwh_total', 'environmental.embodied_carbon_tco2e']) {
  METRICS[k].types = BUILDING_TYPES
}

// ------------------------------------------------------------------
// Authority groups (docs/metrics_matrix.md, "Authority groups")
// ------------------------------------------------------------------

export type AuthorityGroup = 'owned' | 'sold' | 'public'

export const AUTHORITY_GROUP_LABEL: Record<AuthorityGroup, string> = {
  owned: 'Owned',
  sold: 'Sold',
  public: 'Public',
}

/** authority.level only has full_control / advisory; ownership_status splits advisory. */
export function authorityGroup(profile: AssetProfile | null | undefined): AuthorityGroup {
  const a = profile?.authority
  if (!a || a.level === 'full_control') return 'owned'
  return a.ownership_status === 'public_transferred' ? 'public' : 'sold'
}

// ------------------------------------------------------------------
// Core metrics: asset type x authority group (most decision-relevant first)
// ------------------------------------------------------------------

export const CORE_METRICS: Record<string, Partial<Record<AuthorityGroup, string[]>>> = {
  commercial: {
    owned: ['social.occupancy_rate', 'financial.noi_rm', 'financial.dsr', 'environmental.stranded_carbon_ratio'],
    sold: ['social.proxied_occupancy', 'social.business_presence_ratio', 'financial.hemorrhage_ratio', 'social.flow_island_ratio'],
  },
  residential: {
    owned: ['social.occupancy_rate', 'trajectory.class', 'physical.developer_held_units', 'environmental.stranded_carbon_ratio'],
    sold: ['environmental.surface_temp_delta_c', 'environmental.canopy_coverage', 'social.coverage_ratio_10min_walk', 'financial.sale_price_rm'],
  },
  community_facility: {
    owned: ['social.utilisation_rate', 'social.service_coverage', 'social.coverage_ratio_5min_walk', 'financial.cost_per_user_rm'],
    public: ['social.service_coverage', 'social.coverage_ratio_5min_walk', 'social.demographic_mismatch', 'environmental.surface_temp_delta_c'],
  },
  green_space: {
    public: ['environmental.canopy_coverage', 'environmental.green_per_capita_m2', 'social.coverage_ratio_10min_walk', 'environmental.surface_temp_delta_c'],
  },
  undeveloped_parcel: {
    owned: ['financial.demand_supply_gap', 'physical.potential_gfa_m2', 'social.reachable_population_walk', 'financial.infrastructure_cost_rm'],
  },
}

// Combinations with no assets today fall back in this order (matrix note).
const CORE_FALLBACK: Record<AuthorityGroup, AuthorityGroup[]> = {
  owned: ['owned', 'sold', 'public'],
  sold: ['sold', 'public', 'owned'],
  public: ['public', 'sold', 'owned'],
}

export function coreMetricKeys(assetType: string, group: AuthorityGroup): string[] {
  const byGroup = CORE_METRICS[assetType]
  if (!byGroup) return []
  for (const g of CORE_FALLBACK[group]) if (byGroup[g]) return byGroup[g]!
  return []
}

// ------------------------------------------------------------------
// Reading values
// ------------------------------------------------------------------

export function metricValue(profile: AssetProfile | null | undefined, path: string): unknown {
  if (!profile) return null
  const [section, field] = path.split('.', 2)
  const block = (profile as unknown as Record<string, Record<string, unknown> | null>)[section]
  return block ? block[field] ?? null : null
}

export type ResolvedMetric = {
  key: string
  def: MetricDef
  label: string
  value: unknown
  tier?: ServedTier
  /** Value is known to be meaningless (tier U): show "Unknown", not the number. */
  unknown: boolean
  override?: MetricOverride
}

/** Everything a row needs, or null when the metric should be hidden. */
export function resolveMetric(asset: Asset, key: string): ResolvedMetric | null {
  const def = METRICS[key]
  const profile = asset.profile
  if (!def || !profile) return null
  if (def.types && !def.types.includes(asset.assetType)) return null
  const value = metricValue(profile, key)
  if (value === null || value === undefined || value === '') return null
  if (def.hideZero && value === 0) return null

  const override = asset.metricOverrides?.[key]
  const served = profile.tiers?.[key]
  const tier: ServedTier | undefined = override
    ? { tier: override.tier, source: override.source }
    : served
  // "Occupancy (estimated)" + "estimated 2030" -> "Occupancy (estimated 2030)"
  const label = override ? `${def.label.replace(/\s*\(.*\)$/, '')} (${override.qualifier})` : def.label
  return { key, def, label, value, tier, unknown: tier?.tier === 'U', override }
}

// ------------------------------------------------------------------
// Formatting
// ------------------------------------------------------------------

const LOCALE = 'en-US'
const nf = (v: number, max = 0, min = 0) =>
  v.toLocaleString(LOCALE, { maximumFractionDigits: max, minimumFractionDigits: min })

/** Value text and unit text, kept apart so the unit can be styled quietly. */
export function formatValue(
  value: unknown, format: Format, unit?: string, valueLabels?: Record<string, string>,
): { text: string; unit?: string } {
  if (value === null || value === undefined) return { text: '—' }
  if (format === 'text') return { text: valueLabels?.[String(value)] ?? humanize(String(value)) }
  if (format === 'date') return { text: String(value) }
  const v = Number(value)
  if (!Number.isFinite(v)) return { text: '—' }
  const sign = v < 0 ? '−' : ''
  const a = Math.abs(v)
  switch (format) {
    case 'ratio': {
      const pct = v * 100
      return { text: `${pct < 0 ? '−' : ''}${nf(Math.abs(pct), Math.abs(pct) < 10 ? 1 : 0)}%`, unit }
    }
    case 'rm': return { text: `${sign}RM ${nf(a)}`, unit }
    case 'int': return { text: `${sign}${nf(a)}`, unit }
    case 'year': return { text: String(Math.round(v)) }
    case 'dec1': return { text: `${sign}${nf(a, 1, 1)}`, unit }
    case 'dec2': return { text: `${sign}${nf(a, 2, 2)}`, unit }
    case 'area': return { text: `${sign}${nf(a)}`, unit: unit ?? 'm²' }
    case 'tco2e': return { text: `${sign}${nf(a, 1)}`, unit: unit ?? 'tCO₂e' }
    case 'kwh': return { text: `${sign}${nf(a)}`, unit: unit ?? 'kWh' }
    case 'degC': return { text: nf(v, 1, 1), unit: '°C' }
    case 'deltaC': return { text: `${v > 0 ? '+' : v < 0 ? '−' : ''}${nf(a, 2, 2)}`, unit: '°C' }
    case 'months': return { text: nf(v), unit: Math.round(v) === 1 ? 'month' : 'months' }
    case 'years': return { text: nf(v), unit: Math.round(v) === 1 ? 'year' : 'years' }
    case 'minutes': return { text: nf(v), unit: 'min' }
    case 'perDay': return { text: nf(v), unit: unit ?? '/day' }
  }
  return { text: String(value) }
}

export function formatMetric(m: ResolvedMetric): { text: string; unit?: string } {
  if (m.unknown) return { text: 'Unknown' }
  return formatValue(m.value, m.def.format, m.def.unit, m.def.valueLabels)
}

export function isWarn(m: ResolvedMetric): boolean {
  return !m.unknown && typeof m.value === 'number' && !!m.def.warn?.(m.value)
}

// ------------------------------------------------------------------
// Flag evidence: the profile values that explain each flag.
// Shown when the flag row is expanded. Values come from the served
// profile, never from the B6 evidence strings, which are a snapshot of
// older metrics (see docs/DECISIONS.md, D15).
// ------------------------------------------------------------------

export const FLAG_EVIDENCE: Record<string, string[]> = {
  low_occupancy: ['social.occupancy_rate'],
  below_benchmark_occupancy: ['social.occupancy_rate'],
  long_vacancy: ['social.vacancy_duration_months', 'trajectory.vacancy_streak_months'],
  negative_noi: ['financial.noi_rm', 'financial.noi_yield', 'financial.rental_income_rm', 'financial.opex_annual_rm', 'financial.maintenance_annual_rm'],
  noi_yield_below: ['financial.noi_yield'],
  maintenance_surge_high: ['financial.maintenance_surge_rm', 'financial.maintenance_annual_rm'],
  subtype_mix_dead: [],
  subtype_mix_low: [],
  built_value_not_realized: ['social.occupancy_rate', 'social.occupied_units', 'physical.developer_held_units'],
  rapid_decline: ['trajectory.class', 'trajectory.peak_occupancy', 'trajectory.years_since_peak', 'trajectory.occupancy_trend_3yr'],
  falling_from_healthy: ['trajectory.class', 'trajectory.peak_occupancy', 'trajectory.years_since_peak', 'trajectory.occupancy_trend_3yr'],
  chronic_stagnation: ['trajectory.class', 'trajectory.years_below_benchmark', 'trajectory.peak_occupancy', 'trajectory.years_since_peak', 'trajectory.occupancy_trend_3yr'],
  low_utilisation: ['social.utilisation_rate'],
  dsr_below_threshold: ['financial.dsr', 'social.effective_demand_m2'],
  walking_accessibility_deficit: ['social.coverage_ratio_5min_walk', 'social.median_walk_distance_m'],
  driving_accessibility_deficit: ['social.coverage_ratio_10min_drive'],
  demographic_mismatch: ['social.demographic_mismatch'],
  low_neighborhood_diversity: ['social.neighborhood_diversity'],
  high_uhi_exposure: ['environmental.surface_temp_delta_c', 'environmental.t_asset_c', 'environmental.t_township_c'],
  uhi_data_anomaly: ['environmental.surface_temp_delta_c', 'environmental.t_asset_c', 'environmental.t_township_c'],
  high_stranded_carbon: ['environmental.stranded_carbon_ratio', 'environmental.carbon_stranded_tco2e', 'environmental.carbon_operational_tco2e'],
  high_stranded_carbon_ratio_small_asset: ['environmental.stranded_carbon_ratio', 'environmental.carbon_stranded_tco2e', 'environmental.carbon_operational_tco2e'],
  low_green_coverage: ['environmental.green_coverage'],
  low_canopy_coverage: ['environmental.canopy_coverage'],
  low_green_per_capita: ['environmental.green_per_capita_m2'],
  negative_demand_supply_gap: ['financial.demand_supply_gap', 'physical.potential_gfa_m2'],
  weak_future_demand: ['financial.demand_supply_gap', 'physical.potential_gfa_m2'],
  insufficient_coverage: ['social.service_coverage'],
  low_accessibility: ['social.coverage_ratio_10min_walk'],
  low_accessibility_high_ecological_value: ['social.coverage_ratio_10min_walk', 'environmental.canopy_coverage'],
  low_occupancy_proxied: ['social.proxied_occupancy', 'social.proxied_occupancy_lbs', 'social.proxied_occupancy_google'],
  long_vacancy_proxied: ['social.proxied_vacancy_duration'],
  business_presence_low: ['social.business_presence_ratio', 'social.operational_place_count', 'social.unit_mix_unit_count'],
  business_turnover_high: ['social.business_turnover_count'],
  business_vitality_low: ['social.business_vitality_score'],
  low_footfall_lbs: ['social.lbs_unique_users_daily'],
  short_dwell_lbs: ['social.lbs_dwell_minutes'],
  flow_island: ['social.flow_island_ratio'],
  operating_hemorrhage: ['financial.hemorrhage_ratio', 'financial.estimated_revenue_rm', 'financial.survival_opex_floor_rm'],
  data_conflict: ['social.business_presence_ratio', 'social.operational_place_count', 'social.unit_mix_unit_count', 'social.external_demand_ratio'],
  noi_negative_counterfactual: [],
}

/** Flags whose evidence lives in the Tenancy tab's subtype table. */
export const FLAG_SEE_TENANCY = new Set(['subtype_mix_dead', 'subtype_mix_low'])

// ------------------------------------------------------------------
// Placement: every value gets exactly ONE home below the core cards.
//   1. evidence of a raised flag (Diagnosis tab), highest weight first
//   2. ExternalSignalsPanel (Tenancy tab) for signalsPanel metrics
//   3. its pillar (Metrics tab)
// Core metrics are the only allowed repeat: they also keep their home.
// ------------------------------------------------------------------

export type FlagRow = {
  flag: string
  label: string
  weight: number
  tier?: ServedTier['tier']
  evidence: ResolvedMetric[]
  seeTenancy: boolean
  /** Labels of higher-weight flags that already show this flag's values. */
  sharedWith: string[]
}

export type Placement = {
  flags: FlagRow[]
  /** Metric keys shown under a flag, so the signals panel and pillars skip them. */
  claimed: Set<string>
  pillars: Record<Pillar, ResolvedMetric[]>
}

export function placeMetrics(asset: Asset): Placement {
  const d = asset.diagnosis
  const claimed = new Set<string>()
  const claimedBy = new Map<string, string>()
  const weight = new Map((d?.contributing_factors ?? []).map((f) => [f.factor, f.contribution]))
  const order = [...(d?.flags ?? [])].sort((a, b) => (weight.get(b) ?? 0) - (weight.get(a) ?? 0))

  const flags: FlagRow[] = order.map((flag) => {
    const evidence: ResolvedMetric[] = []
    const sharedWith = new Set<string>()
    for (const key of FLAG_EVIDENCE[flag] ?? []) {
      if (claimed.has(key)) { sharedWith.add(claimedBy.get(key)!); continue }
      const m = resolveMetric(asset, key)
      if (m) { evidence.push(m); claimed.add(key); claimedBy.set(key, flagLabel(flag)) }
    }
    const servedTier = d?.flag_tiers?.[flag]
    return {
      flag,
      label: flagLabel(flag),
      weight: weight.get(flag) ?? 0,
      tier: servedTier ? FLAG_TIER[servedTier] : undefined,
      evidence,
      seeTenancy: FLAG_SEE_TENANCY.has(flag),
      sharedWith: [...sharedWith],
    }
  })

  const pillars = { Physical: [], Environmental: [], Financial: [], Social: [] } as Record<Pillar, ResolvedMetric[]>
  for (const [key, def] of Object.entries(METRICS)) {
    if (def.signalsPanel || claimed.has(key)) continue
    const m = resolveMetric(asset, key)
    if (m) pillars[def.pillar].push(m)
  }
  return { flags, claimed, pillars }
}

/** "Deadspace candidate · Negative NOI, Long vacancy" (top 2 flags by weight). */
export function diagnosisSummary(placement: Placement): string[] {
  return placement.flags.slice(0, 2).map((f) => f.label)
}

// ------------------------------------------------------------------
// Panel tabs and pillar defaults
// ------------------------------------------------------------------

// Ask AI is not a tab: the ask bar is pinned under the panel (D20).
export type PanelTab = 'diagnosis' | 'metrics' | 'tenancy'

export const PANEL_TABS: Array<{ key: PanelTab; label: string }> = [
  { key: 'diagnosis', label: 'Diagnosis' },
  { key: 'metrics', label: 'Metrics' },
  { key: 'tenancy', label: 'Tenancy' },
]

/** Pillars open by default in the Metrics tab. */
export const DEFAULT_OPEN_PILLARS: Record<string, Pillar[]> = {
  default: ['Financial', 'Social'],
  undeveloped_parcel: ['Physical'],
}

export function openPillars(assetType: string): Set<Pillar> {
  return new Set(DEFAULT_OPEN_PILLARS[assetType] ?? DEFAULT_OPEN_PILLARS.default)
}

/** One line under the authority badge: which evaluation lens applies. */
export const EVALUATION_TRACK: Record<AuthorityGroup, { label: string; why: string }> = {
  owned: {
    label: 'Operating performance',
    why: 'Sime Darby owns this asset, so its operating figures are its own records.',
  },
  sold: {
    label: 'Developer realisation + community value',
    why: 'Sime Darby sold this asset, so its operating figures are estimates from external proxies, not records.',
  },
  public: {
    label: 'Community + environmental value',
    why: 'This asset was handed to the local council, so it is judged on community and environmental value.',
  },
}

// ------------------------------------------------------------------
// Simulated years (/api/map/geometry metrics_json)
// ------------------------------------------------------------------
//
// For years other than the 2026 baseline the map endpoint sends B4
// simulation values. They replace the profile value but carry no tier,
// and for non-owned assets they are built on proxies or a neutral 0.5
// default (docs/metrics_matrix.md footnotes 2 and 4). Each value is
// re-tiered here by where it came from:
//
//   owned                 projected from observed data   -> "simulated"
//   non-owned + proxy     seeded from LBS / Google       -> 3a "estimated"
//   non-owned, no proxy   neutral default assumption     -> U  "assumed"
//
// Occupancy-dependent fields follow the occupancy rule; other fields keep
// their served tier and are marked "simulated".

type YearRule = { target: string; occupancyBased: boolean; target_if_proxy?: string }

export const YEAR_METRICS: Record<string, YearRule> = {
  occupancy_rate: { target: 'social.occupancy_rate', target_if_proxy: 'social.proxied_occupancy', occupancyBased: true },
  utilisation_rate: { target: 'social.utilisation_rate', occupancyBased: true },
  carbon_stranded_tco2e: { target: 'environmental.carbon_stranded_tco2e', occupancyBased: true },
  stranded_carbon_ratio: { target: 'environmental.stranded_carbon_ratio', occupancyBased: true },
  noi_rm: { target: 'financial.noi_rm', occupancyBased: true },
  carbon_operational_tco2e: { target: 'environmental.carbon_operational_tco2e', occupancyBased: false },
  canopy_coverage: { target: 'environmental.canopy_coverage', occupancyBased: false },
  coverage_ratio_10min_walk: { target: 'social.coverage_ratio_10min_walk', occupancyBased: false },
  effective_demand_m2: { target: 'social.effective_demand_m2', occupancyBased: false },
}

export const BASE_YEAR = 2026

/**
 * Apply one simulated year's metrics to a copy of the 2026 profile.
 * Returns the overrides so the panel can label each replaced value.
 */
export function applyYearMetrics(
  profile: AssetProfile,
  metrics: Record<string, unknown>,
  year: number,
): Record<string, MetricOverride> {
  const overrides: Record<string, MetricOverride> = {}
  if (year === BASE_YEAR) return overrides
  const group = authorityGroup(profile)
  const hasProxy = profile.social.proxied_occupancy != null

  for (const [field, rule] of Object.entries(YEAR_METRICS)) {
    const raw = metrics[field]
    if (raw === null || raw === undefined || Number.isNaN(Number(raw))) continue
    const target = hasProxy && rule.target_if_proxy ? rule.target_if_proxy : rule.target
    const [section, key] = target.split('.', 2)
    ;(profile as unknown as Record<string, Record<string, unknown>>)[section][key] = Number(raw)

    const served = profile.tiers?.[target]?.tier
    let o: Omit<MetricOverride, 'year'>
    if (group === 'owned' || !rule.occupancyBased) {
      // A projection is no longer an observation: tier 1 drops to 2.
      o = { tier: served && served !== '1' ? served : '2', qualifier: `simulated ${year}`, source: 'b4_simulation' }
    } else if (hasProxy) {
      o = { tier: '3a', qualifier: `estimated ${year}`, source: 'b4_simulation_seeded_from_proxy' }
    } else {
      o = { tier: 'U', qualifier: `assumed ${year}`, source: 'b4_simulation_neutral_default' }
    }
    overrides[target] = { year, ...o }
  }
  return overrides
}

// ------------------------------------------------------------------
// Diagnosis flags: B6 flag_tiers values -> badge tier
// ------------------------------------------------------------------

export const FLAG_TIER: Record<string, ServedTier['tier']> = {
  tier_1_observed: '1',
  tier_2_derived: '2',
  tier_3a_proxied: '3a',
  tier_3b_counterfactual: '3b',
}

// ------------------------------------------------------------------
// Subtype tenancy table: columns appear when any row has data
// ------------------------------------------------------------------

export const SUBUNIT_COLUMNS: Array<{
  field: 'occupancy' | 'operational_count' | 'vitality_score'
  label: string
  note: string
}> = [
  { field: 'occupancy', label: 'Occupancy', note: 'observed occupancy per subtype' },
  { field: 'operational_count', label: 'Operating', note: 'operating businesses / designed units (Google Places)' },
  { field: 'vitality_score', label: 'Vitality', note: 'rating × log(reviews), 0–1 (Google Places)' },
]
