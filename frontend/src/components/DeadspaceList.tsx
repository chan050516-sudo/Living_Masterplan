import { useState } from 'react'
import { C, cap, mono, statusOf, humanize, fmt } from '../theme'
import type { AssetProfile, MapStatus } from '../types'

const FILTERS: MapStatus[] = ['deadspace_candidate', 'underperforming_facility', 'development_risk', 'improvement_opportunity', 'monitor']

export function DeadspaceList({ profiles, onPick }: {
  profiles: AssetProfile[]
  onPick: (id: string) => void
}) {
  const [filter, setFilter] = useState<MapStatus>('deadspace_candidate')

  const counts = Object.fromEntries(FILTERS.map((f) => [f, profiles.filter((p) => p.deadspace_diagnosis.status === f).length]))
  const list = profiles
    .filter((p) => p.deadspace_diagnosis.status === filter)
    .sort((a, b) => (b.deadspace_diagnosis.urgency_index ?? 0) - (a.deadspace_diagnosis.urgency_index ?? 0))

  return (
    <>
      <div style={{ ...cap, marginBottom: 12 }}>Assets needing attention</div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 16 }}>
        {FILTERS.map((f) => {
          const active = f === filter
          const { color, label } = statusOf(f)
          return (
            <button
              key={f}
              onClick={() => setFilter(f)}
              style={{
                display: 'flex', alignItems: 'center', gap: 6, padding: '5px 10px', borderRadius: 14,
                border: `1px solid ${active ? color : C.line}`, background: active ? `${color}22` : 'transparent',
                color: active ? C.text : C.muted, fontSize: 11.5, cursor: 'pointer', fontFamily: 'inherit',
              }}
            >
              <span style={{ width: 7, height: 7, borderRadius: '50%', background: color }} />
              {label}
              <span style={{ ...mono, color: active ? color : C.faint }}>{counts[f]}</span>
            </button>
          )
        })}
      </div>

      {list.length === 0 && <p style={{ color: C.faint, fontSize: 12.5 }}>No assets with this status.</p>}

      {list.map((p) => {
        const d = p.deadspace_diagnosis
        const { color, label } = statusOf(d.status)
        return (
          <button
            key={p.identity.asset_id}
            className="ds-card fade"
            onClick={() => onPick(p.identity.asset_id)}
            style={{
              display: 'block', width: '100%', textAlign: 'left', marginBottom: 10, padding: 14,
              background: C.card, border: `1px solid ${C.line}`,
              borderRadius: 8, cursor: 'pointer', color: C.text, font: 'inherit',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, flex: 'none' }} />
                <strong style={{ fontSize: 14, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.identity.asset_name}</strong>
              </span>
              <span title="Urgency index" style={{ ...mono, fontSize: 20, color, flex: 'none' }}>{fmt.num(d.urgency_index, 1)}</span>
            </div>
            <div style={{ fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase', color, marginTop: 3, fontWeight: 600 }}>
              {label} · {humanize(p.identity.asset_type)}
            </div>
            <div style={{ fontSize: 12, color: C.muted, marginTop: 8, lineHeight: 1.5 }}>
              Occupancy {fmt.pct(p.social.occupancy_rate ?? p.social.utilisation_rate)}
              {(p.trajectory.vacancy_streak_months ?? 0) > 0 && ` · vacant ${fmt.num(p.trajectory.vacancy_streak_months)} months`}
              {d.flags.length > 0 && ` · ${d.flags.slice(0, 2).map(humanize).join(', ')}`}
            </div>
          </button>
        )
      })}

      <p style={{ color: C.faint, fontSize: 12, lineHeight: 1.6 }}>
        Sorted by urgency index. Any asset on the map is clickable, not only the ones listed here.
      </p>
    </>
  )
}
