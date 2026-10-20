import type { MapStatus } from './types'

export const C = {
  bg: '#2b212a',
  panel: '#332832',
  card: '#271e26',
  line: '#473b46',
  text: '#f2eef1',
  muted: '#99a5c0',
  faint: '#7b7080',
  accent: '#f7931d',
  bad: '#d71920',
  warn: '#ecaa00',
  good: '#43a047',
  selected: '#2196f3',
  intervene: '#2196f3',
  spill: '#a855f7',
  context: '#5f5566',
} as const

export const tierColor = { observed: C.intervene, estimated: C.warn, scenario: C.bad } as const

// map_status colours follow API.md ("map_status Enum Values")
export const STATUS: Record<MapStatus, { color: string; label: string }> = {
  deadspace_candidate: { color: '#ff5722', label: 'Deadspace candidate' },
  underperforming_facility: { color: '#ff9800', label: 'Underperforming facility' },
  development_risk: { color: '#ab47bc', label: 'Development risk' },
  monitor: { color: C.warn, label: 'Monitor' },
  improvement_opportunity: { color: '#e91e63', label: 'Improvement opportunity' },
  healthy: { color: '#4caf50', label: 'Healthy' },
  vacant: { color: '#9e9e9e', label: 'Vacant parcel' },
  intervened: { color: C.intervene, label: 'In AI plan' },
}

export const statusOf = (s: string | undefined) => STATUS[s as MapStatus] ?? { color: C.context, label: s ?? 'Unknown' }

// MapLibre expression: colour each feature by its map_status
export const statusColorExpr = () =>
  ['match', ['get', 'map_status'], ...Object.entries(STATUS).flatMap(([k, v]) => [k, v.color]), C.context] as unknown as never

export const humanize = (s: string) => s.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())

const isNum = (v: number | null | undefined): v is number => typeof v === 'number' && Number.isFinite(v)

export const fmt = {
  pct: (v: number | null | undefined, digits = 0) => (isNum(v) ? `${(v * 100).toFixed(digits)}%` : '—'),
  num: (v: number | null | undefined, digits = 0) =>
    isNum(v) ? v.toLocaleString('en-MY', { maximumFractionDigits: digits, minimumFractionDigits: digits }) : '—',
  rm: (v: number | null | undefined) => {
    if (!isNum(v)) return '—'
    const a = Math.abs(v)
    const sign = v < 0 ? '−' : ''
    if (a >= 1e6) return `${sign}RM ${(a / 1e6).toFixed(2)}m`
    if (a >= 1e3) return `${sign}RM ${(a / 1e3).toFixed(0)}k`
    return `${sign}RM ${a.toFixed(0)}`
  },
}

export const btn = (active = false): React.CSSProperties => ({
  padding: '7px 16px',
  borderRadius: 6,
  border: `1px solid ${active ? C.accent : C.line}`,
  background: active ? C.accent : 'transparent',
  color: active ? '#1a1419' : '#cfc6cd',
  cursor: 'pointer',
  fontSize: 13,
  fontWeight: active ? 700 : 400,
  fontFamily: 'inherit',
})

export const cap: React.CSSProperties = {
  fontSize: 11,
  letterSpacing: '.14em',
  textTransform: 'uppercase',
  color: C.muted,
  fontWeight: 600,
}

export const mono: React.CSSProperties = {
  fontFamily: 'ui-monospace, monospace',
  fontVariantNumeric: 'tabular-nums',
}