import type { AnalyzeResult, AssetProfiles, MapGeometry } from './types'

// Empty by default: Vite proxies /api to the backend in dev (see vite.config.ts).
// Set VITE_API_URL to call a deployed backend directly.
const BASE = import.meta.env.VITE_API_URL ?? ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body)
    } catch { /* non-JSON error body */ }
    throw new Error(`${res.status}: ${detail}`)
  }
  return res.json() as Promise<T>
}

export const getAssetProfiles = () => request<AssetProfiles>('/api/assets/profiles')

export const getMapGeometry = (runId?: string) =>
  request<MapGeometry>(`/api/map/geometry${runId ? `?run_id=${encodeURIComponent(runId)}` : ''}`)

export function analyze(userQuery: string, assetIds: string[], files: File[] = []) {
  const form = new FormData()
  form.append('user_query', userQuery)
  form.append('selected_assets', assetIds.join(','))
  for (const f of files) form.append('files', f)
  return request<AnalyzeResult>('/api/analyze', { method: 'POST', body: form })
}
