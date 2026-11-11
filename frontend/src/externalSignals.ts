// External proxy signals for sold assets: foot traffic (Kido LBS), business
// presence (Google Places) and the developer-realisation sale record.
//
// Ported from mathaba-experimental, where this read Yu Qian's mock tables from
// public/mock via rows('/mock/...'). The backend profile now serves every
// field (GET /api/assets/profiles), so this is a pure mapping from the profile
// and needs no fetch. Types are unchanged so the panel layout is unchanged.

import type { AssetProfile, ServedTier } from './types'

export type LbsSignals = {
  users: number | null          // daily unique visitors
  dwell: number | null          // average minutes per visit
  flowIsland: number | null     // reachable / local footfall; < 0.3 means network-isolated
  proxOcc: number | null        // occupancy estimated from footfall
  demandRatio: number | null    // visitors / capacity
  traffic: number | null        // vehicles per day passing
  isMock: boolean
}

export type PlacesSignals = {
  presence: number | null       // share of consumer-facing units with an operating business
  operational: number | null    // count of operating businesses
  units: number | null          // consumer-facing units
  vitality: number | null       // 0 to 1, from rating x review count
  vacancyMonths: number | null  // estimated months since last operating business
  turnover: number | null       // businesses replaced across snapshots
  isMock: boolean
}

export type SaleSignals = {
  price: number | null      // what Sime Darby sold it for
  date: string | null
  source: string | null
  profit: number | null     // sale price minus build cost (served, tier 2)
  saleReturn: number | null // profit / build cost
}

export type ExternalSignals = { lbs?: LbsSignals; places?: PlacesSignals; sale?: SaleSignals }

/** Profile path behind each signal, so rows can show the served tier. */
export const SIGNAL_PATHS = {
  users: 'social.lbs_unique_users_daily',
  dwell: 'social.lbs_dwell_minutes',
  flowIsland: 'social.flow_island_ratio',
  proxOcc: 'social.proxied_occupancy_lbs',
  traffic: 'social.traffic_exposure_vpd',
  presence: 'social.business_presence_ratio',
  vitality: 'social.business_vitality_score',
  vacancyMonths: 'social.proxied_vacancy_duration',
  turnover: 'social.business_turnover_count',
  price: 'financial.sale_price_rm',
  date: 'financial.sale_date',
  profit: 'financial.sale_profit_rm',
  saleReturn: 'financial.sale_return_ratio',
} as const

const anyValue = (o: Record<string, unknown>) =>
  Object.entries(o).some(([k, v]) => k !== 'isMock' && v !== null && v !== undefined)

const isMock = (tiers: Record<string, ServedTier> | undefined, path: string) => !!tiers?.[path]?.mock

export function signalsFromProfile(p: AssetProfile | null | undefined): ExternalSignals {
  if (!p) return {}
  const s = p.social
  const f = p.financial
  const t = p.tiers
  const out: ExternalSignals = {}

  const lbs: LbsSignals = {
    users: s.lbs_unique_users_daily ?? null,
    dwell: s.lbs_dwell_minutes ?? null,
    flowIsland: s.flow_island_ratio ?? null,
    proxOcc: s.proxied_occupancy_lbs ?? null,
    demandRatio: s.external_demand_ratio ?? null,
    traffic: s.traffic_exposure_vpd ?? null,
    isMock: isMock(t, SIGNAL_PATHS.users),
  }
  if (anyValue(lbs)) out.lbs = lbs

  const places: PlacesSignals = {
    presence: s.business_presence_ratio ?? null,
    operational: s.operational_place_count ?? null,
    units: s.unit_mix_unit_count ?? null,
    vitality: s.business_vitality_score ?? null,
    vacancyMonths: s.proxied_vacancy_duration ?? null,
    turnover: s.business_turnover_count ?? null,
    isMock: isMock(t, SIGNAL_PATHS.presence),
  }
  if (anyValue(places)) out.places = places

  const sale: SaleSignals = {
    price: f.sale_price_rm ?? null,
    date: f.sale_date ?? null,
    source: f.sale_data_source ?? null,
    profit: f.sale_profit_rm ?? null,
    saleReturn: f.sale_return_ratio ?? null,
  }
  if (sale.price != null) out.sale = sale

  return out
}
