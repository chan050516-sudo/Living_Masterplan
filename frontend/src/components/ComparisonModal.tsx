import { useState } from 'react'
import { C, cap, mono } from '../theme'
import type { Comparison, MetricDelta } from '../types'

/** Turns a raw number into something readable, based on its unit. */
function fmt(v: number | null, unit: string) {
  if (v === null || v === undefined) return '—'
  if (unit === 'ratio') return `${(v * 100).toFixed(1)}%`
  if (unit === 'RM') return `RM ${Math.round(v).toLocaleString()}`
  if (unit === 'm') return `${Math.round(v)} m`
  if (unit === 'Celsius') return `+${v.toFixed(1)} °C`
  if (unit.startsWith('tCO2e')) return `${v.toLocaleString(undefined, { maximumFractionDigits: 1 })}`
  return String(v)
}

function pretty(s: string) {
  const t = s.replace(/_tco2e$/, '').replace(/_rm$/, '').replace(/_m$/, '').replace(/_/g, ' ')
  return t.charAt(0).toUpperCase() + t.slice(1)
}

/** Did the metric move, and is up good or bad? Returns a colour or null. */
function deltaColor(key: string, d: MetricDelta) {
  if (d.before === null || d.after === null) return null
  const diff = d.after - d.before
  if (Math.abs(diff) < 1e-9) return null
  const lowerIsBetter = /carbon|stranded|distance|maintenance|surge|temp/.test(key)
  const good = lowerIsBetter ? diff < 0 : diff > 0
  return good ? '#3fb27f' : '#d71920'
}

function MetricRow({ name, d }: { name: string; d: MetricDelta }) {
  const col = deltaColor(name, d)
  const unit = d.unit ?? ''
  return (
    <tr>
      <td style={{ padding: '9px 10px', fontSize: 12.5, color: '#cfc6cd' }}>
        {pretty(name)}
        {unit.startsWith('tCO2e') && <span style={{ color: C.faint }}> (tCO₂e)</span>}
      </td>
      <td style={{ ...mono, padding: '9px 10px', fontSize: 13, textAlign: 'right', color: C.faint }}>
        {fmt(d.before, unit)}
      </td>
      <td style={{ ...mono, padding: '9px 10px', fontSize: 13, textAlign: 'right', color: col ?? C.text }}>
        {fmt(d.after, unit)}
      </td>
    </tr>
  )
}

export function ComparisonModal({ data, onClose }: { data: Comparison; onClose: () => void }) {
  const assetIds = Object.keys(data.per_asset)
  const [active, setActive] = useState(data.focus_asset_id ?? assetIds[0] ?? '')

  const rows = data.per_asset[active] ?? {}
  const t = data.township_metrics
  const a = data.aggregate

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 50, display: 'flex',
        alignItems: 'center', justifyContent: 'center', padding: 28,
        background: 'rgba(12,8,12,.72)', backdropFilter: 'blur(3px)',
      }}
    >
      <div
        className="pop"
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 'min(820px, 100%)', maxHeight: '100%', overflowY: 'auto',
          background: C.panel, border: `1px solid ${C.line}`, borderRadius: 12, padding: 26,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
          <span style={{ ...cap, fontSize: 11 }}>Scenario comparison</span>
          <span style={{ flex: 1 }} />
          <button
            className="ctrl" onClick={onClose} aria-label="Close comparison"
            style={{
              background: 'none', border: 0, color: C.muted, fontSize: 20,
              cursor: 'pointer', width: 30, height: 30, borderRadius: 6, lineHeight: 1,
            }}
          >×</button>
        </div>

        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
          gap: 14, marginBottom: 24,
        }}>
          <Headline
            label="Embodied carbon avoided"
            value={a.avoided_embodied_carbon_tco2e.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            unit="tCO₂e"
            good
          />
          <Headline
            label="Township carbon"
            value={`${(t.carbon_delta_pct * 100).toFixed(1)}%`}
            unit={t.carbon_delta_pct < 0 ? 'reduction' : 'increase'}
            good={t.carbon_delta_pct < 0}
          />
          <Headline
            label="15-min walk coverage"
            value={`${(t.walk_15min_coverage_delta * 100).toFixed(1)}%`}
            unit="change"
            good={t.walk_15min_coverage_delta >= 0}
          />
        </div>

        {assetIds.length > 1 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 14 }}>
            {assetIds.slice(0, 12).map((id) => (
              <button
                key={id}
                className={`chip${active === id ? ' on' : ''}`}
                onClick={() => setActive(id)}
                style={{
                  ...mono, padding: '4px 10px', borderRadius: 999, fontSize: 11,
                  cursor: 'pointer', fontWeight: active === id ? 600 : 400,
                }}
              >
                {id}
              </button>
            ))}
          </div>
        )}

        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              <th style={{ ...cap, fontSize: 10, textAlign: 'left', padding: '0 10px 10px' }}>
                {active || 'Metric'}
              </th>
              <th style={{ ...cap, fontSize: 10, textAlign: 'right', padding: '0 10px 10px', color: C.faint }}>Before</th>
              <th style={{ ...cap, fontSize: 10, textAlign: 'right', padding: '0 10px 10px' }}>After</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(rows).map(([name, d]) => (
              <MetricRow key={name} name={name} d={d} />
            ))}
          </tbody>
        </table>

        <div style={{ marginTop: 22, paddingTop: 18, borderTop: `1px solid ${C.line}` }}>
          <div style={{ ...cap, fontSize: 10, marginBottom: 12 }}>Township</div>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <tbody>
              <MetricRow
                name="total_carbon_tco2e"
                d={{ before: t.total_carbon_before_tco2e, after: t.total_carbon_after_tco2e, unit: 'tCO2e' }}
              />
              <MetricRow
                name="walk_15min_coverage"
                d={{ before: t.walk_15min_avg_coverage_before, after: t.walk_15min_avg_coverage_after, unit: 'ratio' }}
              />
              <tr>
                <td style={{ padding: '9px 10px', fontSize: 12.5, color: '#cfc6cd' }}>
                  Cumulative project carbon <span style={{ color: C.faint }}>(tCO₂e)</span>
                </td>
                <td style={{ padding: '9px 10px', textAlign: 'right', color: C.faint }}>—</td>
                <td style={{ ...mono, padding: '9px 10px', fontSize: 13, textAlign: 'right' }}>
                  {t.project_carbon_cumulative_tco2e.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </td>
              </tr>
            </tbody>
          </table>
          <p style={{ fontSize: 11.5, color: C.faint, lineHeight: 1.6, marginTop: 14 }}>
            Across {a.asset_count} assets. Township totals include delivered development projects; the per-asset table does not.
          </p>
        </div>
      </div>
    </div>
  )
}

function Headline({ label, value, unit, good }: {
  label: string; value: string; unit: string; good: boolean
}) {
  return (
    <div style={{
      padding: 15, background: C.card, border: `1px solid ${C.line}`, borderRadius: 8,
    }}>
      <div style={{ ...cap, fontSize: 9.5, marginBottom: 8 }}>{label}</div>
      <div style={{ ...mono, fontSize: 24, color: good ? '#3fb27f' : '#d71920' }}>{value}</div>
      <div style={{ fontSize: 11, color: C.faint, marginTop: 3 }}>{unit}</div>
    </div>
  )
}