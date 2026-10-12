import { C, cap, mono, btn } from '../theme'
import type { Comparison, ComparisonRow } from '../types'

const cols: Array<keyof Pick<ComparisonRow, 'current' | 'a' | 'b' | 'c'>> = ['current', 'a', 'b', 'c']
const heads = ['Current plan', 'A · Repurpose', 'B · Retrofit + green', 'C · Delay']

export function ComparisonModal({ data, onClose }: { data: Comparison; onClose: () => void }) {
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(15,11,15,.68)', zIndex: 10,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        backdropFilter: 'blur(2px)',
      }}
    >
      <div
        className="pop"
        onClick={(e) => e.stopPropagation()}
        style={{
          background: C.panel, border: '1px solid #5a4b58', borderRadius: 12, padding: '26px 28px',
          maxWidth: 1060, width: '92%', maxHeight: '88vh', overflowY: 'auto',
          boxShadow: '0 32px 70px rgba(0,0,0,.55)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 20 }}>
          <h2 style={{ margin: 0, fontSize: 19 }}>Scenario comparison</h2>
          <span style={{ flex: 1 }} />
          <button
            className="ctrl"
            onClick={onClose}
            aria-label="Close"
            style={{
              background: 'none', border: 0, color: C.muted, fontSize: 20, cursor: 'pointer',
              width: 32, height: 32, borderRadius: 6, lineHeight: 1,
            }}
          >×</button>
        </div>

        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              <th style={{ ...cap, textAlign: 'left', padding: '11px 14px', borderBottom: '1px solid #5a4b58', width: '28%' }}>Metric</th>
              {heads.map((h) => (
                <th key={h} style={{ ...cap, textAlign: 'left', padding: '11px 14px', borderBottom: '1px solid #5a4b58' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r, i) => (
              <tr key={r.label} className="fade" style={{ animationDelay: `${0.03 * i}s` }}>
                <td style={{
                  padding: '11px 14px', fontSize: 13, color: r.key ? C.text : C.muted,
                  borderBottom: '1px solid #3c3340', fontWeight: r.key ? 600 : 400,
                  background: r.key ? '#2d2330' : undefined,
                  borderTop: r.key ? '1px solid #5a4b58' : undefined,
                }}>{r.label}</td>
                {cols.map((k) => {
                  const win = r.best === k
                  const v = r[k]
                  const positive = r.delta && typeof v === 'string' && v.startsWith('+')
                  return (
                    <td key={k} style={{
                      ...mono, padding: '11px 14px', fontSize: r.key ? 17 : 13.5,
                      borderBottom: '1px solid #3c3340',
                      borderTop: r.key ? '1px solid #5a4b58' : undefined,
                      background: win ? 'rgba(67,160,71,.14)' : r.key ? '#2d2330' : undefined,
                      boxShadow: win ? `inset 2px 0 ${C.good}` : undefined,
                      color: positive || (win && r.key) ? C.good : C.text,
                      fontWeight: r.key ? 600 : 400,
                    }}>{v}</td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>

        <div style={{
          marginTop: 22, padding: '16px 18px', background: 'rgba(247,147,29,.09)',
          border: '1px solid rgba(247,147,29,.35)', borderRadius: 8,
        }}>
          <div style={{ ...cap, fontSize: 10, color: C.accent, marginBottom: 7 }}>Recommended</div>
          <strong style={{ fontSize: 14 }}>{data.recommended}</strong>
          <p style={{ margin: '6px 0 0', fontSize: 12.5, color: '#cfc6cd', lineHeight: 1.6 }}>{data.reason}</p>
        </div>

        <div style={{ display: 'flex', gap: 10, marginTop: 22, paddingTop: 18, borderTop: `1px solid ${C.line}` }}>
          <span style={{ flex: 1 }} />
          <button className="btn" onClick={onClose} style={btn()}>Close</button>
          <button className="btn primary" style={btn(true)}>Apply to plan</button>
        </div>
      </div>
    </div>
  )
}