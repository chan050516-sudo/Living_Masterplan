// External proxy signals for sold assets: foot traffic (Kido LBS) and business presence (Google Places).
// TEMPORARY SOURCE: Yu Qian's mock tables copied into public/mock. When the backend API carries
// these fields, replace loadExternalSignals() and keep the types; the panel won't need changes.

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

export type ExternalSignals = { lbs?: LbsSignals; places?: PlacesSignals }

const num = (v: unknown): number | null => {
  if (v === null || v === undefined || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}
const bool = (v: unknown) => String(v).toLowerCase() === 'true'

async function rows(url: string): Promise<Record<string, unknown>[]> {
  try {
    const r = await fetch(url)
    if (!r.ok) return []
    const data = await r.json()
    return Array.isArray(data) ? data : data ? [data] : []
  } catch {
    return []
  }
}

let cache: Promise<Map<string, ExternalSignals>> | null = null

export function loadExternalSignals(): Promise<Map<string, ExternalSignals>> {
  if (cache) return cache
  cache = Promise.all([
    rows('/mock/asset_lbs_metrics.json'),
    rows('/mock/asset_business_presence.json'),
  ]).then(([lbs, places]) => {
    const map = new Map<string, ExternalSignals>()
    for (const r of lbs) {
      const id = String(r.asset_id ?? '')
      if (!id) continue
      map.set(id, {
        ...map.get(id),
        lbs: {
          users: num(r.lbs_unique_users_daily),
          dwell: num(r.lbs_dwell_time_minutes),
          flowIsland: num(r.flow_island_ratio),
          proxOcc: num(r.proxied_occupancy_lbs),
          demandRatio: num(r.observed_demand_ratio),
          traffic: num(r.traffic_exposure_vpd),
          isMock: bool(r.is_mock),
        },
      })
    }
    for (const r of places) {
      const id = String(r.asset_id ?? '')
      if (!id) continue
      map.set(id, {
        ...map.get(id),
        places: {
          presence: num(r.business_presence_ratio),
          operational: num(r.operational_place_count),
          units: num(r.consumer_facing_unit_count),
          vitality: num(r.business_vitality_score),
          vacancyMonths: num(r.proxied_vacancy_duration),
          turnover: num(r.business_turnover_count),
          isMock: bool(r.is_mock),
        },
      })
    }
    return map
  })
  return cache
}