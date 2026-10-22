import { useState } from 'react'
import { C, cap, mono } from '../theme'
import type { Asset, AssetStatus } from '../types'

/** Map each status enum to its colour. v1.2 §8.2. */
const STATUS_COLOR: Record<AssetStatus, string> = {
  healthy: '#3fb27f',
  monitor: '#f7931d',
  deadspace_candidate: '#d71920',
  underperforming_facility: '#d71920',
  development_risk: '#f15c22',
  improvement_opportunity: '#f7931d',
}

/** "deadspace_candidate" → "Deadspace candidate" */
function prettyStatus(s: string) {
  const t = s.replace(/_/g, ' ')
  return t.charAt(0).toUpperCase() + t.slice(1)
}

/** Pulls one line out of B6's evidence strings, e.g. findEvidence(ev, 'Occupancy'). */
function findEvidence(evidence: string[], prefix: string) {
  const hit = evidence.find((e) => e.startsWith(prefix + ':'))
  return hit ? hit.slice(prefix.length + 1).trim() : null
}

const FILTERS = [
  { key: 'all', label: 'All issues' },
  { key: 'deadspace_candidate', label: 'Deadspace' },
  { key: 'underperforming_facility', label: 'Facilities' },
  { key: 'improvement_opportunity', label: 'Opportunities' },
  { key: 'monitor', label: 'Monitor' },
] as const

const PAGE = 40

export function DeadspaceList({ assets, onPick }: {
  assets: Asset[]
  onPick: (a: Asset) => void
}) {
  const [filter, setFilter] = useState<string>('all')
  const [shown, setShown] = useState(PAGE)

  const flagged = assets.filter(
    (a) => a.diagnosis && a.diagnosis.status !== 'healthy',
  )

  const list = flagged
    .filter((a) => filter === 'all' || a.diagnosis!.status === filter)
    .sort((a, b) => b.diagnosis!.urgency_index - a.diagnosis!.urgency_index)

  const visible = list.slice(0, shown)

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 12 }}>
        <span style={cap}>Flagged assets</span>
        <span style={{ ...mono, fontSize: 11, color: C.accent }}>{list.length}</span>
        <span style={{ ...mono, fontSize: 11, color: C.faint }}>of {assets.length}</span>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 16 }}>
        {FILTERS.map((f) => (
          <button
            key={f.key}
            className={`chip${filter === f.key ? ' on' : ''}`}
            onClick={() => { setFilter(f.key); setShown(PAGE) }}
            style={{
              padding: '4px 10px', borderRadius: 999, fontSize: 11,
              letterSpacing: '.06em', cursor: 'pointer', font: 'inherit',
              fontWeight: filter === f.key ? 600 : 400,
            }}
          >
            {f.label}
          </button>
        ))}
      </div>

      {visible.map((a) => {
        const d = a.diagnosis!
        const col = STATUS_COLOR[d.status] ?? C.muted
        const occ = findEvidence(d.evidence, 'Occupancy')
        const vac = findEvidence(d.evidence, 'Vacancy')
        const subtype = findEvidence(d.evidence, 'Subtype')

        return (
          <button
            key={a.id}
            className="ds-card fade"
            onClick={() => onPick(a)}
            style={{
              display: 'block', width: '100%', textAlign: 'left', marginBottom: 10, padding: 14,
              background: C.card, border: `1px solid ${C.line}`,
              borderRadius: 8, cursor: 'pointer', color: C.text, font: 'inherit',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 8 }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: col, flex: 'none' }} />
                <strong style={{ fontSize: 13.5 }}>{a.name}</strong>
              </span>
              {subtype && (
                <span style={{ fontSize: 11, color: C.faint, whiteSpace: 'nowrap' }}>{subtype}</span>
              )}
            </div>

            <div style={{
              fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase',
              color: col, marginTop: 5, fontWeight: 600,
            }}>
              {prettyStatus(d.status)}
            </div>

            <div style={{ fontSize: 12, color: C.muted, marginTop: 8, lineHeight: 1.5 }}>
              {occ && `Occupancy ${occ}`}
              {occ && vac && ' · '}
              {vac && `vacant ${vac}`}
              {!occ && !vac && `${d.flags.length} flags raised`}
            </div>
          </button>
        )
      })}

      {shown < list.length && (
        <button
          className="btn"
          onClick={() => setShown(shown + PAGE)}
          style={{
            width: '100%', padding: '9px 0', marginBottom: 12, cursor: 'pointer',
            font: 'inherit', fontSize: 12, color: C.text,
            background: 'transparent', border: `1px solid ${C.line}`, borderRadius: 8,
          }}
        >
          Show {Math.min(PAGE, list.length - shown)} more
        </button>
      )}

      <p style={{ color: C.faint, fontSize: 12, lineHeight: 1.6 }}>
        Every asset on the map is clickable, not only the flagged ones. Ctrl-click to select several.
      </p>
    </>
  )
}