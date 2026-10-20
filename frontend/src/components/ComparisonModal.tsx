import { useState } from 'react'
import { C, cap, mono } from '../theme'
import type { AnalyzeResult, MainMetric } from '../types'

function fmt(v: number | null | undefined, unit: string) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  if (unit === 'ratio') return `${(v * 100).toFixed(1)}%`
  if (unit === 'RM') return `RM ${Math.round(v).toLocaleString()}`
  if (unit === 'm') return `${Math.round(v)} m`
  if (unit.startsWith('tCO2e')) return v.toLocaleString(undefined, { maximumFractionDigits: 1 })
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

function pretty(s: string) {
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
            <div style={{ ...cap, fontSize: 10, marginBottom: 12 }}>Time series</div>
            {Object.entries(timeline.metrics).map(([name, series]) => (
              <div key={name} style={{ marginBottom: 18 }}>
                <div style={{ fontSize: 12.5, color: '#cfc6cd', marginBottom: 8 }}>{pretty(name)}</div>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      <th style={{ ...cap, fontSize: 9.5, textAlign: 'left', padding: '0 8px 8px' }} />
                      {timeline.years.map((y) => (
                        <th key={y} style={{ ...cap, fontSize: 9.5, textAlign: 'right', padding: '0 8px 8px' }}>{y}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td style={{ fontSize: 12, color: C.faint, padding: '6px 8px' }}>Baseline</td>
                      {series.baseline.map((v, i) => (
                        <td key={i} style={{ ...mono, fontSize: 12, textAlign: 'right', padding: '6px 8px', color: C.faint }}>
                          {fmt(v, name.endsWith('_rm') ? 'RM' : '')}
                        </td>
                      ))}
                    </tr>
                    <tr>
                      <td style={{ fontSize: 12, padding: '6px 8px' }}>Intervention</td>
                      {series.intervention.map((v, i) => (
                        <td key={i} style={{ ...mono, fontSize: 12, textAlign: 'right', padding: '6px 8px' }}>
                          {fmt(v, name.endsWith('_rm') ? 'RM' : '')}
                        </td>
                      ))}
                    </tr>
                  </tbody>
                </table>
              </div>
            ))}
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