import { C, cap, mono, btn, fmt, humanize } from '../theme'
import type { AnalyzeResult, AssetAnalysis, AssetProfiles, MainMetric } from '../types'

const TIMELINE_ROWS: Array<[string, string, (v: number) => string]> = [
  ['noi_rm', 'Annual NOI', fmt.rm],
  ['space_utilization', 'Space utilisation', (v) => fmt.pct(v)],
  ['carbon_operational_tco2e', 'Operational carbon (tCO₂e/yr)', (v) => fmt.num(v)],
  ['carbon_stranded_tco2e', 'Stranded carbon (tCO₂e/yr)', (v) => fmt.num(v)],
]

const fmtMetric = (m: MainMetric, v: number) =>
  m.unit === 'RM' ? fmt.rm(v) : m.unit === 'ratio' ? fmt.pct(v) : `${fmt.num(v)} ${m.unit}`

// Lower is better for carbon; higher is better for everything else here
const improved = (m: MainMetric) =>
  /carbon/i.test(m.label) ? m.intervention < m.baseline : m.intervention > m.baseline

export function ComparisonModal({ data, profiles, onClose }: {
  data: AnalyzeResult
  profiles: AssetProfiles
  onClose: () => void
}) {
  const t = data.township_metrics
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
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 6 }}>
          <h2 style={{ margin: 0, fontSize: 19 }}>Simulation results</h2>
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
        <p style={{ margin: '0 0 20px', fontSize: 12.5, color: C.muted }}>
          {data.decision.selected_candidate} · baseline vs. with intervention · run {data.run_id}
        </p>

        {t && t.total_carbon_before_tco2e != null && (
          <div style={{ display: 'flex', gap: 28, padding: '14px 18px', background: C.card, borderRadius: 8, marginBottom: 22 }}>
            <Kpi label="Township carbon before" value={`${fmt.num(t.total_carbon_before_tco2e)} tCO₂e`} />
            <Kpi label="Township carbon after" value={`${fmt.num(t.total_carbon_after_tco2e)} tCO₂e`} />
            <Kpi label="Change" value={`${t.carbon_delta_pct > 0 ? '+' : ''}${fmt.pct(t.carbon_delta_pct, 2)}`}
              color={t.carbon_delta_pct > 0 ? C.bad : C.good} />
          </div>
        )}

        {data.assets_analysis.map((a) => (
          <AssetResult key={a.asset_id} a={a} name={profiles[a.asset_id]?.identity.asset_name} />
        ))}

        <div style={{ display: 'flex', gap: 10, marginTop: 22, paddingTop: 18, borderTop: `1px solid ${C.line}` }}>
          <span style={{ flex: 1 }} />
          <button className="btn" onClick={onClose} style={btn()}>Close</button>
        </div>
      </div>
    </div>
  )
}

function Kpi({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div style={{ ...cap, fontSize: 9.5, marginBottom: 5 }}>{label}</div>
      <div style={{ ...mono, fontSize: 17, color: color ?? C.text }}>{value}</div>
    </div>
  )
}

function AssetResult({ a, name }: { a: AssetAnalysis; name?: string }) {
  const card = a.summary_card
  const metrics = [card.financial.main_metric, card.social.main_metric, ...card.environmental.main_metrics]
  const cf = card.financial.counterfactual
  const ce = card.environmental.counterfactual
  const cell = { ...mono, padding: '9px 12px', fontSize: 12.5, borderBottom: '1px solid #3c3340' }

  return (
    <section style={{ marginBottom: 28 }}>
      <h3 style={{ margin: '0 0 12px', fontSize: 15, fontWeight: 600 }}>
        {name ?? a.asset_id} <span style={{ ...mono, fontSize: 12, color: C.faint, fontWeight: 400 }}>{a.asset_id}</span>
      </h3>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 10, marginBottom: 14 }}>
        {metrics.map((m) => (
          <div key={m.label} style={{ padding: 13, background: C.card, border: `1px solid ${C.line}`, borderRadius: 8 }}>
            <div style={{ ...cap, fontSize: 9.5, marginBottom: 6 }}>{m.label}</div>
            <div style={{ ...mono, fontSize: 13 }}>
              <span style={{ color: C.faint }}>{fmtMetric(m, m.baseline)}</span>
              <span style={{ color: C.faint, margin: '0 6px' }}>→</span>
              <span style={{ color: improved(m) ? C.good : m.intervention === m.baseline ? C.text : C.bad }}>{fmtMetric(m, m.intervention)}</span>
            </div>
          </div>
        ))}
      </div>

      {(cf.capex_if_new_build_rm > 0 || ce.net_carbon_averted_tco2e > 0) && (
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10, marginBottom: 14,
          padding: '14px 16px', background: 'rgba(67,160,71,.09)', border: '1px solid rgba(67,160,71,.35)', borderRadius: 8,
        }}>
          <div>
            <div style={{ ...cap, fontSize: 9.5, color: C.good, marginBottom: 6 }}>CAPEX: new build vs reuse</div>
            <div style={{ ...mono, fontSize: 13 }}>{fmt.rm(cf.capex_if_new_build_rm)} vs {fmt.rm(cf.capex_if_repurpose_rm)}</div>
            <div style={{ fontSize: 12, color: C.muted, marginTop: 4 }}>Saved {fmt.rm(cf.capex_saved_rm)}</div>
          </div>
          <div>
            <div style={{ ...cap, fontSize: 9.5, color: C.good, marginBottom: 6 }}>Embodied carbon: new build vs reuse</div>
            <div style={{ ...mono, fontSize: 13 }}>{fmt.num(ce.embodied_if_new_build_tco2e)} vs {fmt.num(ce.embodied_if_repurpose_tco2e)} tCO₂e</div>
            <div style={{ fontSize: 12, color: C.muted, marginTop: 4 }}>Avoided {fmt.num(ce.net_carbon_averted_tco2e)} tCO₂e</div>
          </div>
        </div>
      )}

      {a.timeline.years.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={{ ...cap, fontSize: 10, textAlign: 'left', padding: '9px 12px', borderBottom: '1px solid #5a4b58' }}>Metric</th>
                {a.timeline.years.map((y) => (
                  <th key={y} style={{ ...cap, fontSize: 10, textAlign: 'right', padding: '9px 12px', borderBottom: '1px solid #5a4b58' }}>{y}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {TIMELINE_ROWS.filter(([k]) => a.timeline.metrics[k]).flatMap(([k, label, f]) => {
                const m = a.timeline.metrics[k]
                return (['baseline', 'intervention'] as const).map((series) => (
                  <tr key={`${k}-${series}`}>
                    <td style={{ ...cell, fontFamily: 'inherit', color: series === 'baseline' ? C.muted : C.text }}>
                      {series === 'baseline' ? label : ''}
                      <span style={{ color: series === 'baseline' ? C.faint : C.intervene, fontSize: 11, marginLeft: series === 'baseline' ? 8 : 0 }}>
                        {humanize(series === 'baseline' ? 'baseline' : 'with plan')}
                      </span>
                    </td>
                    {m[series].map((v, i) => (
                      <td key={i} style={{ ...cell, textAlign: 'right', color: series === 'baseline' ? C.muted : C.text }}>{f(v)}</td>
                    ))}
                  </tr>
                ))
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
