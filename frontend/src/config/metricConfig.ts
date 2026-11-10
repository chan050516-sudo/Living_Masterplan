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
}

const BUILDING_TYPES = ['commercial', 'residential', 'community_facility']

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
  'trajectory.class': { label: 'Occupancy trajectory', pillar: 'Social', format: 'text' },
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

export function prettyText(s: string): string {
  const t = s.replace(/_/g, ' ')
  return t.charAt(0).toUpperCase() + t.slice(1)
}

/** Value text and unit text, kept apart so the unit can be styled quietly. */
export function formatValue(value: unknown, format: Format, unit?: string): { text: string; unit?: string } {
  if (value === null || value === undefined) return { text: '—' }
  if (format === 'text') return { text: prettyText(String(value)) }
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
  return formatValue(m.value, m.def.format, m.def.unit)
}

export function isWarn(m: ResolvedMetric): boolean {
  return !m.unknown && typeof m.value === 'number' && !!m.def.warn?.(m.value)
}

/** Pillar rows: every configured metric with data, minus the core ones and
 *  the ones ExternalSignalsPanel shows. */
export function pillarMetrics(asset: Asset, pillar: Pillar, exclude: Set<string>): ResolvedMetric[] {
  const out: ResolvedMetric[] = []
  for (const [key, def] of Object.entries(METRICS)) {
    if (def.pillar !== pillar || def.signalsPanel || exclude.has(key)) continue
    const m = resolveMetric(asset, key)
    if (m) out.push(m)
  }
  return out
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
