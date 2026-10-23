import type { AssetProfile, AnalyzeResult } from './types'
import type { FeatureCollection } from 'geojson'

// import { MOCK_SCENARIO_1, MOCK_SCENARIO_2, MOCK_SCENARIO_3, MOCK_SCENARIO_4 } from '../../legacy/mockData'

const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
// const USE_MOCK_LLM = false

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
  
  /*
  if (USE_MOCK_LLM) {
    console.log("🚀 [MOCK MODE] Routing to correct scenario based on inputs...");
    return new Promise<AnalyzeResult>((resolve) => {
      setTimeout(() => {
        // Scenario 1
        if (userQuery.includes('feasibility') || userQuery.includes('BLD-0183') || selectedAssets.includes('BLD-0183')) {
          resolve(MOCK_SCENARIO_1)
        } 
        // Scenario 4
        else if (userQuery.includes('blueprint') || userQuery.includes('P-VAC-08') || selectedAssets.includes('P-VAC-08')) {
          resolve(MOCK_SCENARIO_4)
        }
        // Scenario 3
        else if (selectedAssets.length > 1) {
          resolve(MOCK_SCENARIO_3)
        } 
        // Scenario 2
        else {
          resolve(MOCK_SCENARIO_2)
        }
      }, 2000); 
    });
  }
  */
  
  const form = new FormData()
  form.append('user_query', userQuery)
  form.append('selected_assets', selectedAssets.join(','))
  for (const f of files.slice(0, 3)) form.append('files', f)
  return request<AnalyzeResult>('/api/analyze', { method: 'POST', body: form })
}