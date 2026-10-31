import { useState } from 'react'
import { C, cap, mono } from '../theme'
import type { AnalyzeResult, MainMetric } from '../types'
import { LineChart } from './LineChart'

function fmt(v: number | null | undefined, unit: string) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  if (unit === 'ratio') return `${(v * 100).toFixed(1)}%`
  if (unit === 'RM') return `RM ${Math.round(v).toLocaleString()}`
  if (unit === 'm') return `${Math.round(v)} m`
  if (unit.startsWith('tCO2e')) return v.toLocaleString(undefined, { maximumFractionDigits: 1 })
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

/** Metric keys that shouldn't be title-cased mechanically. */
const LABELS: Record<string, string> = {
  noi_rm: 'NOI',
  noi: 'NOI',
  noi_yield: 'NOI yield',
  dsr: 'DSR',
  carbon_operational_tco2e: 'Operational Carbon',
  carbon_stranded_tco2e: 'Stranded Carbon',
  carbon_productive_tco2e: 'Productive Carbon',
  occupancy_rate: 'Occupancy',
  space_utilization: 'Space Utilization',
  space_utilisation: 'Space Utilisation',
  utilisation_rate: 'Utilisation',
  effective_demand_m2: 'Effective demand',
  coverage_ratio_15min_walk: '15-min walk coverage',
  coverage_ratio_10min_walk: '10-min walk coverage',
  coverage_ratio_5min_walk: '5-min walk coverage',
  surface_temp_delta_c: 'Surface Temp ΔT',
}

function pretty(s: string) {
  if (LABELS[s]) return LABELS[s]
  const t = s.replace(/_tco2e$/, '').replace(/_rm$/, '').replace(/_m2$/, ' m²').replace(/_/g, ' ')
  return t.charAt(0).toUpperCase() + t.slice(1)
}

function moveColor(before: number | null, after: number | null, lowerIsBetter: boolean) {
  if (before === null || after === null) return null
  const diff = after - before
  if (Math.abs(diff) < 1e-9) return null
  const good = lowerIsBetter ? diff < 0 : diff > 0
  return good ? '#3fb27f' : '#d71920'
}

function Row({ label, before, after, unit, lowerIsBetter = false }: {
  label: string
  before: number | null
  after: number | null
  unit: string
  lowerIsBetter?: boolean
}) {
  const col = moveColor(before, after, lowerIsBetter)
  return (
    <tr>
      <td style={{ padding: '9px 10px', fontSize: 12.5, color: '#cfc6cd' }}>{label}</td>
      <td style={{ ...mono, padding: '9px 10px', fontSize: 13, textAlign: 'right', color: C.faint }}>
        {fmt(before, unit)}
      </td>
      <td style={{ ...mono, padding: '9px 10px', fontSize: 13, textAlign: 'right', color: col ?? C.text }}>
        {fmt(after, unit)}
      </td>
    </tr>
  )
}

function Headline({ label, value, unit, good }: {
  label: string; value: string; unit: string; good: boolean
}) {
  return (
    <div style={{ padding: 15, background: C.card, border: `1px solid ${C.line}`, borderRadius: 8 }}>
      <div style={{ ...cap, fontSize: 9.5, marginBottom: 8 }}>{label}</div>
      <div style={{ ...mono, fontSize: 23, color: good ? '#3fb27f' : '#d71920' }}>{value}</div>
      <div style={{ fontSize: 11, color: C.faint, marginTop: 3 }}>{unit}</div>
    </div>
  )
}

export function ComparisonModal({ data, onClose }: { data: AnalyzeResult; onClose: () => void }) {
  const ids = data.assets_analysis.map((a) => a.asset_id)
  const [active, setActive] = useState(ids[0] ?? '')
  const current = data.assets_analysis.find((a) => a.asset_id === active)
  const t = data.township_metrics
  const j = data.decision.justification

  // Totals across every asset in the plan.
  let capexSaved = 0
  let carbonAverted = 0
  for (const a of data.assets_analysis) {
    capexSaved += a.summary_card.financial?.counterfactual?.capex_saved_rm ?? 0
    carbonAverted += a.summary_card.environmental?.counterfactual?.net_carbon_averted_tco2e ?? 0
  }

  const metrics: MainMetric[] = []
  if (current?.summary_card.financial?.main_metric) metrics.push(current.summary_card.financial.main_metric)
  if (current?.summary_card.social?.main_metric) metrics.push(current.summary_card.social.main_metric)

  const socialExtras = current?.summary_card.social?.metrics ?? {}
  const envMetrics = current?.summary_card.environmental?.main_metrics ?? []
  const timeline = current?.timeline

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
          width: 'min(860px, 100%)', maxHeight: '100%', overflowY: 'auto',
          background: C.panel, border: `1px solid ${C.line}`, borderRadius: 12, padding: 26,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
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

        <h2 style={{ margin: '0 0 6px', fontSize: 19, fontWeight: 500 }}>
          {data.decision.selected_candidate}
        </h2>
        <div style={{ ...mono, fontSize: 11, color: C.faint, marginBottom: 22 }}>
          {data.scenario_id}
        </div>

        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
          gap: 14, marginBottom: 24,
        }}>
          <Headline
            label="Embodied carbon averted"
            value={carbonAverted.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            unit="tCO₂e not emitted"
            good={carbonAverted > 0}
          />
          <Headline
            label="CAPEX avoided"
            value={`RM ${Math.round(capexSaved).toLocaleString()}`}
            unit="vs building new"
            good={capexSaved > 0}
          />
          <Headline
            label="Township carbon"
            value={`${(t.carbon_delta_pct * 100).toFixed(2)}%`}
            unit={t.carbon_delta_pct < 0 ? 'reduction' : 'increase'}
            good={t.carbon_delta_pct < 0}
          />
        </div>

        <div style={{
          padding: 16, background: C.card, border: `1px solid ${C.line}`,
          borderRadius: 8, marginBottom: 22,
        }}>
          <div style={{ ...cap, fontSize: 10, color: C.accent, marginBottom: 9 }}>What the simulation shows</div>
          <p style={{ margin: 0, fontSize: 13, lineHeight: 1.65, color: '#cfc6cd' }}>
            {j.what_simulation_shows}
          </p>
          <div style={{ ...cap, fontSize: 10, color: C.accent, margin: '16px 0 9px' }}>Why this plan</div>
          <p style={{ margin: 0, fontSize: 13, lineHeight: 1.65, color: '#cfc6cd' }}>
            {j.why_this_plan}
          </p>
        </div>

        {ids.length > 1 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 14 }}>
            {ids.map((id) => (
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
              <th style={{ ...cap, fontSize: 10, textAlign: 'right', padding: '0 10px 10px', color: C.faint }}>
                Baseline
              </th>
              <th style={{ ...cap, fontSize: 10, textAlign: 'right', padding: '0 10px 10px' }}>
                Intervention
              </th>
            </tr>
          </thead>
          <tbody>
            {metrics.map((m) => (
              <Row key={m.label} label={m.label} before={m.baseline} after={m.intervention} unit={m.unit} />
            ))}
            {Object.entries(socialExtras).map(([k, v]) => (
              <Row key={k} label={pretty(k)} before={v.baseline} after={v.intervention} unit={k.includes('ratio') ? 'ratio' : ''} />
            ))}
            {envMetrics.map((m) => (
              <Row key={m.label} label={m.label} before={m.baseline} after={m.intervention} unit={m.unit} lowerIsBetter />
            ))}
          </tbody>
        </table>

        {timeline && Object.keys(timeline.metrics).length > 0 && (
          <div style={{ marginTop: 24, paddingTop: 18, borderTop: `1px solid ${C.line}` }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
              <span style={{ ...cap, fontSize: 10 }}>Over time</span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: C.faint }}>
                <svg width="22" height="8" aria-hidden="true">
                  <line x1="0" y1="4" x2="22" y2="4" stroke="#8d7f8a" strokeWidth="2" strokeDasharray="5 4" />
                </svg>
                Baseline
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: C.faint }}>
                <svg width="22" height="8" aria-hidden="true">
                  <line x1="0" y1="4" x2="22" y2="4" stroke={C.accent} strokeWidth="2" />
                </svg>
                Intervention
              </span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {Object.entries(timeline.metrics)
              .filter(([, s]) =>
                [...s.baseline, ...s.intervention].some((v) => Number.isFinite(v) && v !== 0),
              )
              .map(([name, series]) => {
                const unit = /carbon|tco2e/i.test(name) ? 'tCO2e'
                  : /_rm$|noi|capex|opex|income|rental/i.test(name) ? 'RM'
                    : /ratio|rate|utilisation|utilization|occupancy|coverage/i.test(name) ? 'ratio'
                      : ''
                return (
                <div key={name} style={{
                  padding: '13px 14px 6px',
                  background: C.card,
                  border: `1px solid ${C.line}`,
                  borderRadius: 8,
                }}>
                  {(() => {
                    const b = series.baseline[series.baseline.length - 1]
                    const p = series.intervention[series.intervention.length - 1]
                    const lower = /carbon|stranded|vacancy|maintenance|temp/i.test(name)
                    const moved = Number.isFinite(b) && Number.isFinite(p) && Math.abs(p - b) > 1e-9
                    const better = moved ? (lower ? p < b : p > b) : null
                    const pct = moved && b !== 0 ? ((p - b) / Math.abs(b)) * 100 : null

                    return (
                      <div style={{
                        display: 'flex', alignItems: 'baseline', gap: 10,
                        marginBottom: 4, flexWrap: 'wrap',
                      }}>
                        <span style={{ fontSize: 13, color: C.text }}>{pretty(name)}</span>
                        <span style={{ fontSize: 11, color: C.faint }}>
                          {unit === 'RM' ? 'RM' : unit === 'ratio' ? '%' : unit === 'tCO2e' ? 'tCO₂e' : ''}
                        </span>
                        {better !== null && (
                          <span style={{
                            ...mono, fontSize: 11, padding: '2px 8px', borderRadius: 999,
                            color: better ? '#3fb27f' : '#d71920',
                            background: better ? 'rgba(63,178,127,.12)' : 'rgba(215,25,32,.12)',
                          }}>
                            {pct !== null && Math.abs(pct) < 1000
                              ? `${pct > 0 ? '+' : ''}${pct.toFixed(0)}% by ${timeline.years[timeline.years.length - 1]}`
                              : `${better ? 'improves' : 'worsens'} by ${timeline.years[timeline.years.length - 1]}`}
                          </span>
                        )}
                      </div>
                    )
                  })()}
                  <LineChart
                    years={timeline.years}
                    lowerIsBetter={/carbon|stranded|vacancy|maintenance|temp/i.test(name)}
                    format={(v) => fmt(v, unit).replace('RM ', '')}
                    series={[
                      { label: 'Baseline', values: series.baseline, color: '#8d7f8a', dashed: true },
                      { label: 'Intervention', values: series.intervention, color: C.accent },
                    ]}
                  />
                </div>
              )
            })}
            </div>
          </div>
        )}

        <div style={{ marginTop: 22, paddingTop: 18, borderTop: `1px solid ${C.line}` }}>
          <div style={{ ...cap, fontSize: 10, marginBottom: 12 }}>Township</div>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <tbody>
              <Row
                label="Total carbon (tCO₂e)"
                before={t.total_carbon_before_tco2e}
                after={t.total_carbon_after_tco2e}
                unit="tCO2e"
                lowerIsBetter
              />
            </tbody>
          </table>
          <p style={{ fontSize: 11.5, color: C.faint, lineHeight: 1.6, marginTop: 14 }}>
            Township totals include development projects delivered on schedule, so they can rise even when the
            intervention itself avoids emissions. The averted embodied carbon above is the effect of reuse.
          </p>
        </div>
      </div>
    </div>
  )
}