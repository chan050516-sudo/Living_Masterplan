import { C, cap, mono, bandColor } from '../theme'
import type { Asset } from '../types'

export function DeadspaceList({ assets, year, onPick }: {
  assets: Asset[]
  year: 'now' | '3y'
  onPick: (a: Asset) => void
}) {
  const scoreOf = (a: Asset) => (year === 'now' ? a.score : a.score_3y)
  const list = assets.filter((a) => scoreOf(a) < 60).sort((a, b) => scoreOf(a) - scoreOf(b))

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 14 }}>
        <span style={cap}>Deadspace candidates</span>
        <span style={{ ...mono, fontSize: 11, color: C.accent }}>{list.length}</span>
      </div>

      {list.map((a) => {
        const s = scoreOf(a)
        const col = bandColor(s)
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
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: col, flex: 'none' }} />
                <strong style={{ fontSize: 14 }}>{a.name}</strong>
              </span>
              <span style={{ ...mono, fontSize: 22, color: col }}>{s}</span>
            </div>
            <div style={{ fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase', color: col, marginTop: 3, fontWeight: 600 }}>
              {a.status}
            </div>
            <div style={{ fontSize: 12, color: C.muted, marginTop: 8, lineHeight: 1.5 }}>
              Occupancy {year === 'now' ? a.occupancy : a.occupancy_3y}%
              {a.vacancy_months > 0 && ` · vacant ${a.vacancy_months} months`}
            </div>
          </button>
        )
      })}

      <p style={{ color: C.faint, fontSize: 12, lineHeight: 1.6 }}>
        Any asset on the map is clickable, not only the candidates listed here.
      </p>
    </>
  )
}