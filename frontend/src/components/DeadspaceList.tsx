import { useState } from 'react'
import { C, cap, mono } from '../theme'
import type { Asset, AssetStatus, InterventionMode } from '../types'
import { statusLabel, subtypeLabel } from '../config/metricConfig'

/** Map each status enum to its colour. */
const STATUS_COLOR: Record<AssetStatus, string> = {
  healthy: '#3fb27f',
  monitor: '#f7931d',
  deadspace_candidate: '#d71920',
  underperforming_facility: '#d71920',
  development_risk: '#f15c22',
  improvement_opportunity: '#f7931d',
  // v6.1g — statuses that acknowledge a diagnosed problem the
  // developer cannot directly own. Red hue shared with
  // deadspace_candidate so the reader sees "this is a problem";
  // the intervention_mode badge underneath tells them what can
  // actually be done.
  community_value_gap: '#d71920',
  strategic_learning: '#f15c22',
  intervened: '#2196f3',
}

/** Map intervention mode to a border colour and a badge label. */
const MODE_STYLE: Record<InterventionMode, {
  label: string
  border: string
  dot: string
  description: string
}> = {
  direct: {
    label: 'SDP DIRECT',
    border: '#d71920',
    dot: '#d71920',
    description: 'Sime Darby owns this asset and can execute any intervention.',
  },
  collaborative: {
    label: 'COLLABORATIVE',
    border: '#a855f7',
    dot: '#a855f7',
    description: 'Sold / strata asset. SDP can collaborate via JMB or walkway improvement.',
  },
  advisory: {
    label: 'ADVISORY',
    border: '#7b7080',
    dot: '#7b7080',
    description: 'Sold asset with no collaboration path. SDP can only recommend.',
  },
}

const prettyStatus = statusLabel

function findEvidence(evidence: string[], prefix: string) {
  const hit = evidence.find((e) => e.startsWith(prefix + ':'))
  return hit ? hit.slice(prefix.length + 1).trim() : null
}

/** Filters combine the two orthogonal dimensions:
 *  - what is the diagnosis (status)
 *  - what can SDP do about it (mode)
 */
const FILTERS = [
  { key: 'all', label: 'All issues' },
  { key: 'deadspace_candidate', label: 'Deadspace' },
  { key: 'community_value_gap', label: 'Community gap' },
  { key: 'strategic_learning', label: 'Learning' },
  { key: 'underperforming_facility', label: 'Facilities' },
  { key: 'improvement_opportunity', label: 'Opportunities' },
  { key: 'flow_island', label: 'Flow island' },
  { key: 'monitor', label: 'Monitor' },
] as const

const PAGE = 40

/** Sort priority inside the same status: direct > collaborative
 *  > advisory. A reader scanning the deadspace list wants to see
 *  the ones they can act on today at the top. */
function modeRank(mode?: InterventionMode): number {
  if (mode === 'direct') return 0
  if (mode === 'collaborative') return 1
  if (mode === 'advisory') return 2
  return 3
}

export function DeadspaceList({ assets, onPick, filter, onFilter }: {
  assets: Asset[]
  onPick: (a: Asset) => void
  filter: string
  onFilter: (f: string) => void
}) {
  const [shown, setShown] = useState(PAGE)

  const flagged = assets.filter(
    (a) => a.diagnosis && a.diagnosis.status !== 'healthy',
  )

  const list = flagged
    .filter((a) => {
      if (filter === 'all') return true
      if (filter === 'flow_island') return a.diagnosis!.flags.includes('flow_island')
      return a.diagnosis!.status === filter
    })
    .sort((a, b) => {
      const byMode = modeRank(a.diagnosis!.intervention_mode)
        - modeRank(b.diagnosis!.intervention_mode)
      if (byMode !== 0) return byMode
      return b.diagnosis!.urgency_index - a.diagnosis!.urgency_index
    })

  const visible = list.slice(0, shown)

  const directCount = flagged.filter((a) => a.diagnosis!.intervention_mode === 'direct').length
  const collabCount = flagged.filter((a) => a.diagnosis!.intervention_mode === 'collaborative').length
  const advisoryCount = flagged.filter((a) => a.diagnosis!.intervention_mode === 'advisory').length

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 12 }}>
        <span style={cap}>Flagged assets</span>
        <span style={{ ...mono, fontSize: 11, color: C.accent }}>{list.length}</span>
        <span style={{ ...mono, fontSize: 11, color: C.faint }}>of {assets.length}</span>
      </div>

      {/* Mode legend — helps the reader understand the three
          execution buckets before they read the list. */}
      <div style={{
        display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 14,
        padding: '8px 10px', background: C.card, border: `1px solid ${C.line}`,
        borderRadius: 8, fontSize: 11,
      }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ ...mono, color: MODE_STYLE.direct.dot }}>●</span>
          <span style={{ color: C.muted }}>Direct</span>
          <span style={{ ...mono, color: C.faint }}>{directCount}</span>
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ ...mono, color: MODE_STYLE.collaborative.dot }}>◐</span>
          <span style={{ color: C.muted }}>Collaborative</span>
          <span style={{ ...mono, color: C.faint }}>{collabCount}</span>
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ ...mono, color: MODE_STYLE.advisory.dot }}>○</span>
          <span style={{ color: C.muted }}>Advisory</span>
          <span style={{ ...mono, color: C.faint }}>{advisoryCount}</span>
        </span>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 16 }}>
        {FILTERS.map((f) => (
          <button
            key={f.key}
            className={`chip${filter === f.key ? ' on' : ''}`}
            onClick={() => { onFilter(f.key); setShown(PAGE) }}
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
        const mode = d.intervention_mode
        const modeStyle = mode ? MODE_STYLE[mode] : null

        const occ = findEvidence(d.evidence, 'Occupancy')
        const vac = findEvidence(d.evidence, 'Vacancy')
        // Register subtype, human-labelled (evidence strings carry the raw key).
        const subtype = subtypeLabel(a.profile?.identity.subtype)

        return (
          <button
            key={a.id}
            className="ds-card fade"
            onClick={() => onPick(a)}
            style={{
              display: 'block', width: '100%', textAlign: 'left', marginBottom: 10, padding: 14,
              background: C.card,
              border: `1px solid ${C.line}`,
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
              display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 5,
            }}>
              <span style={{
                fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase',
                color: col, fontWeight: 600,
              }}>
                {prettyStatus(d.status)}
              </span>
              {modeStyle && (
                <span
                  title={modeStyle.description}
                  style={{
                    fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase',
                    color: modeStyle.dot,
                    padding: '1px 6px',
                    borderRadius: 3,
                    background: `${modeStyle.dot}14`,
                    border: `1px solid ${modeStyle.dot}40`,
                    fontWeight: 600,
                  }}
                >
                  {modeStyle.label}
                </span>
              )}
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