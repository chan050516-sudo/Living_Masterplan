import type { AssetProfile, AnalyzeResult } from './types'
import type { FeatureCollection } from 'geojson'

import {
  MOCK_SCENARIO_CASE1,
  MOCK_SCENARIO_CASE2,
} from './mockData'

const BASE = import.meta.env.VITE_API_URL || 'https://living-masterplan-api-1071997994154.asia-southeast1.run.app'
const USE_MOCK_LLM = true

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

/** Runs the LLM pipeline over the selected assets. */
export function runAnalysis(userQuery: string, selectedAssets: string[], files: File[] = []) {
  if (USE_MOCK_LLM) {
    console.log("🚀 [MOCK MODE] Routing to correct scenario based on inputs...");
    return new Promise<AnalyzeResult>((resolve) => {
      setTimeout(() => {
        // Case 1: BLD-0037 in the selected set OR PDF attached OR budget mentioned
        const isCase1 =
          selectedAssets.includes("BLD-0037") ||
          selectedAssets.includes("BLD-0260") ||
          files.some((f) => f.name.toLowerCase().endsWith(".pdf")) ||
          /BLD-0037|feasibility|budget|engineering spec|retrofit/i.test(userQuery)

        // Case 2: BLD-0736 or BLD-0067 mentioned, or tenant matching / soft keywords
        const isCase2 =
          selectedAssets.includes("BLD-0736") ||
          selectedAssets.includes("BLD-0067") ||
          /tenant|shoplot|flow island|kopitiam|landlord|owner/i.test(userQuery)

        if (isCase1) {
          resolve(MOCK_SCENARIO_CASE1)
        } else if (isCase2) {
          resolve(MOCK_SCENARIO_CASE2)
        } else {
          // Fallback: keep existing behaviour for any old demo scenarios.
          resolve(MOCK_SCENARIO_CASE1)
        }
      }, 1500)
    })
  }

  const form = new FormData()
  form.append('user_query', userQuery)
  form.append('selected_assets', selectedAssets.join(','))
  for (const f of files.slice(0, 3)) form.append('files', f)
  return request<AnalyzeResult>('/api/analyze', { method: 'POST', body: form })
}