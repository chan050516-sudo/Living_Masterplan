import type { AssetProfile, AnalyzeResult } from './types'
import type { FeatureCollection } from 'geojson'

import {
  MOCK_SCENARIO_CASE1,
  MOCK_SCENARIO_CASE2,
} from './mockData'

const BASE = import.meta.env.VITE_API_URL || 'https://living-masterplan-api-1071997994154.asia-southeast1.run.app'

// ─────────────────────────────────────────────────────────────
// Demo routing
// ─────────────────────────────────────────────────────────────
// Only a selection whose ENTIRE asset set belongs to one frozen
// demo scenario — and whose query does not cross into the other
// scenario — is served from the pre-recorded mock. Everything
// else goes to the real /api/analyze.
//
// These force the live path:
//   - any non-demo asset in the selection
//   - a mix of case1 and case2 assets
//   - a case1 asset set combined with a case2 query hint
//   - a case2 asset set combined with a case1 hint or a PDF
// ─────────────────────────────────────────────────────────────

const DEMO_CASE1_ASSETS = new Set(['BLD-0037', 'BLD-0260', 'BLD-0004'])
const DEMO_CASE2_ASSETS = new Set(['BLD-0736', 'BLD-0734', 'BLD-0067'])
const DEMO_ALL_ASSETS = new Set([...DEMO_CASE1_ASSETS, ...DEMO_CASE2_ASSETS])

const CASE1_QUERY_HINT = /BLD-0037|feasibility|budget|engineering spec|retrofit/i
const CASE2_QUERY_HINT = /tenant|shoplot|flow island|kopitiam|landlord|owner/i

export type AnalysisRoute =
  | { kind: 'mock'; scenario: 'case1' | 'case2' }
  | { kind: 'live' }

export function routeAnalysis(
  selectedAssets: string[],
  userQuery: string,
  files: File[],
): AnalysisRoute {
  // No assets (ask() already blocks this, but be defensive).
  if (selectedAssets.length === 0) return { kind: 'live' }

  // Every selected asset must be a demo asset.
  const allDemo = selectedAssets.every((id) => DEMO_ALL_ASSETS.has(id))
  if (!allDemo) return { kind: 'live' }

  // The selection must belong entirely to one case.
  const allCase1 = selectedAssets.every((id) => DEMO_CASE1_ASSETS.has(id))
  const allCase2 = selectedAssets.every((id) => DEMO_CASE2_ASSETS.has(id))
  if (!allCase1 && !allCase2) return { kind: 'live' }

  // Query / file hints must not cross-contaminate the other case.
  const hasPdf = files.some((f) => f.name.toLowerCase().endsWith('.pdf'))
  const case1Hit = CASE1_QUERY_HINT.test(userQuery) || hasPdf
  const case2Hit = CASE2_QUERY_HINT.test(userQuery)

  if (allCase1 && !case2Hit) return { kind: 'mock', scenario: 'case1' }
  if (allCase2 && !case1Hit) return { kind: 'mock', scenario: 'case2' }

  // Asset set matches one case, but the query hints at the other → live.
  return { kind: 'live' }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch { /* body wasn't JSON */ }
    throw new Error(`${path} failed: ${res.status} ${detail}`)
  }
  
  return res.json() as Promise<T>
}

/** Every asset's 2026 baseline. Call once on load and keep it. */
export function fetchProfiles() {
  return request<Record<string, AssetProfile>>('/api/assets/profiles')
}

/** Buildings, parcels and green space as one FeatureCollection. */
export function fetchGeometry(runId?: string, year: number = 2026) {
  const params = new URLSearchParams()
  if (runId) params.append('run_id', runId)
  params.append('year', year.toString())
  return request<FeatureCollection>(`/api/map/geometry?${params.toString()}`)
}

/** Runs the LLM pipeline over the selected assets.
 *  - Demo set (case1/case2 assets only, matching query) → frozen mock.
 *  - Everything else → real /api/analyze (2-4 min).
 */
export function runAnalysis(userQuery: string, selectedAssets: string[], files: File[] = []) {
  const route = routeAnalysis(selectedAssets, userQuery, files)

  if (route.kind === 'mock') {
    console.log(`🚀 [MOCK] → ${route.scenario}`, { selectedAssets, userQuery })
    return new Promise<AnalyzeResult>((resolve) => {
      setTimeout(() => {
        resolve(route.scenario === 'case1' ? MOCK_SCENARIO_CASE1 : MOCK_SCENARIO_CASE2)
      }, 1500)
    })
  }

  console.log('🌐 [LIVE] real /api/analyze — can take 2-4 minutes', {
    selectedAssets, userQuery, fileCount: files.length,
  })
  const form = new FormData()
  form.append('user_query', userQuery)
  form.append('selected_assets', selectedAssets.join(','))
  for (const f of files.slice(0, 3)) form.append('files', f)
  return request<AnalyzeResult>('/api/analyze', { method: 'POST', body: form })
}