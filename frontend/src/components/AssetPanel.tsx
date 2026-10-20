import { C, cap, mono, btn } from '../theme'
import { Bar } from './ui'
import type { Asset, AnalyzeResult, MainMetric } from '../types'

const STATUS_COLOR: Record<string, string> = {
  healthy: '#3fb27f',
  monitor: '#f7931d',
  deadspace_candidate: '#d71920',
  underperforming_facility: '#d71920',
  development_risk: '#f15c22',
  improvement_opportunity: '#f7931d',
  vacant: '#9e9e9e',
  intervened: '#2196f3',
}

function pretty(s: string) {
  const t = s.replace(/_/g, ' ')
  return t.charAt(0).toUpperCase() + t.slice(1)
}

/** "Occupancy: 24.5%" → { label: "Occupancy", value: "24.5%" } */
function splitEvidence(line: string) {
  const i = line.indexOf(':')
  if (i === -1) return { label: line, value: '' }
  return { label: line.slice(0, i).trim(), value: line.slice(i + 1).trim() }
}

function fmt(v: number | null | undefined, unit: string) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  if (unit === 'ratio') return `${(v * 100).toFixed(1)}%`
  if (unit === 'RM') return `RM ${Math.round(v).toLocaleString()}`
  if (unit.startsWith('tCO2e')) return `${v.toLocaleString(undefined, { maximumFractionDigits: 1 })}`
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

/** Before → after, coloured by whether the move is an improvement. */
function MetricLine({ m, lowerIsBetter }: { m: MainMetric; lowerIsBetter?: boolean }) {
  const moved =
    m.baseline !== null && m.intervention !== null &&
    Math.abs(m.intervention - m.baseline) > 1e-9
  const better =
    moved && m.baseline !== null && m.intervention !== null
      ? (lowerIsBetter ? m.intervention < m.baseline : m.intervention > m.baseline)
      : null

  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, padding: '6px 0', fontSize: 12.5 }}>
      <span style={{ color: '#cfc6cd' }}>{m.label}</span>
      <span style={{ ...mono, marginLeft: 'auto', color: C.faint }}>{fmt(m.baseline, m.unit)}</span>
      <span style={{ color: C.faint }}>→</span>
      <span style={{
        ...mono,
        color: better === null ? C.text : better ? '#3fb27f' : '#d71920',
      }}>
        {fmt(m.intervention, m.unit)}
      </span>
    </div>
  )
}

export function AssetPanel(props: {
  assets: Asset[]
  question: string
  setQuestion: (v: string) => void
  asked: string
  analysis: AnalyzeResult | null
  loading: boolean
  error: string | null
  onAsk: () => void
  previewing: boolean
  onPreview: () => void
  onClearPreview: () => void
  onSimulate: () => void
  onClose: () => void
}) {
  const { assets, analysis, asked, error, previewing } = props
  const rule = { border: 0, borderTop: `1px solid ${C.line}`, margin: '20px 0' }
  const multi = assets.length > 1

  return (
    <>
      <div className="fade" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ ...cap, fontSize: 10 }}>
          {multi ? `${assets.length} assets selected` : 'Selected asset'}
        </span>
        <span style={{ flex: 1 }} />
        <button
          className="ctrl" onClick={props.onClose} aria-label="Close asset panel"
          style={{
            background: 'none', border: 0, color: C.muted, fontSize: 20, cursor: 'pointer',
            width: 30, height: 30, borderRadius: 6, lineHeight: 1, flex: 'none',
          }}
        >×</button>
      </div>

      {assets.map((asset, idx) => {
        const d = asset.diagnosis
        const p = asset.profile
        const col = d ? STATUS_COLOR[d.status] ?? C.muted : STATUS_COLOR[asset.mapStatus] ?? C.muted

        return (
          <div key={asset.id} style={{ marginTop: idx === 0 ? 10 : 26 }}>
            <h2 className="fade" style={{ margin: 0, fontSize: 19, fontWeight: 500 }}>
              {asset.name}
            </h2>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 4 }}>
              <span style={{ ...mono, fontSize: 11, color: C.faint }}>{asset.id}</span>
              <span style={{ fontSize: 12, color: C.faint }}>
                {asset.subtype ?? asset.assetType}
              </span>
            </div>

            <div className="fade" style={{
              fontSize: 11, letterSpacing: '.11em', textTransform: 'uppercase',
              color: col, fontWeight: 600, marginTop: 9,
            }}>
              {pretty(d?.status ?? asset.mapStatus)}
            </div>

            {d && d.flags.length > 0 && (
              <div className="fade d1" style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 12 }}>
                {d.flags.map((f) => (
                  <span key={f} style={{
                    fontSize: 11, padding: '3px 8px', borderRadius: 5,
                    background: C.card, border: `1px solid ${C.line}`, color: '#cfc6cd',
                  }}>{pretty(f)}</span>
                ))}
              </div>
            )}

            {p && (
              <>
                <hr style={rule} />
                <div className="fade d2">
                  <div style={{ ...cap, fontSize: 10, marginBottom: 10 }}>Key figures</div>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, fontSize: 12.5, padding: '5px 0' }}>
                    <span style={{ color: '#cfc6cd' }}>Occupancy</span>
                    <span style={{ ...mono, marginLeft: 'auto' }}>
                      {fmt(p.social.occupancy_rate ?? p.social.utilisation_rate, 'ratio')}
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, fontSize: 12.5, padding: '5px 0' }}>
                    <span style={{ color: '#cfc6cd' }}>Annual NOI</span>
                    <span style={{
                      ...mono, marginLeft: 'auto',
                      color: (p.financial.noi_rm ?? 0) < 0 ? '#d71920' : C.text,
                    }}>
                      {fmt(p.financial.noi_rm, 'RM')}
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, fontSize: 12.5, padding: '5px 0' }}>
                    <span style={{ color: '#cfc6cd' }}>Stranded carbon</span>
                    <span style={{ ...mono, marginLeft: 'auto' }}>
                      {fmt(p.environmental.stranded_carbon_ratio, 'ratio')}
                    </span>
                  </div>
                </div>
              </>
            )}

            {d && d.contributing_factors.length > 0 && (
              <>
                <hr style={rule} />
                <div className="fade d3">
                  <div style={{ ...cap, fontSize: 10, marginBottom: 14 }}>Contributing factors</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    {d.contributing_factors.map((f) => (
                      <Bar
                        key={f.factor}
                        label={pretty(f.factor)}
                        value={Math.round(f.contribution * 100)}
                        color={C.accent}
                        suffix="%"
                      />
                    ))}
                  </div>
                </div>
              </>
            )}

            {d && d.evidence.length > 0 && (
              <>
                <hr style={rule} />
                <div className="fade d4">
                  <div style={{ ...cap, fontSize: 10, marginBottom: 6 }}>Evidence</div>
                  {d.evidence.map((line) => {
                    const { label, value } = splitEvidence(line)
                    return (
                      <div key={line} style={{
                        display: 'flex', alignItems: 'baseline', gap: 10,
                        fontSize: 12.5, color: '#cfc6cd', padding: '6px 0',
                      }}>
                        <span>{label}</span>
                        <b style={{ ...mono, marginLeft: 'auto', fontWeight: 400, color: C.text, textAlign: 'right' }}>
                          {value}
                        </b>
                      </div>
                    )
                  })}
                </div>
              </>
            )}
          </div>
        )
      })}

      <hr style={rule} />

      {error && (
        <div className="fade" style={{
          padding: 13, marginBottom: 16, borderRadius: 8,
          background: C.card, border: '1px solid #d7192066', fontSize: 12.5, color: '#f0b8b8',
        }}>
          {error}
        </div>
      )}

      {analysis && (
        <>
          <div className="fade" style={{ ...cap, fontSize: 10, marginBottom: 6 }}>Your question</div>
          <p className="fade" style={{ margin: '0 0 16px', fontSize: 14, fontStyle: 'italic' }}>
            “{asked}”
          </p>

          <div className="fade d1" style={{
            padding: 15, background: C.card, border: `1px solid ${C.line}`,
            borderRadius: 8, marginBottom: 16,
          }}>
            <div style={{ ...cap, fontSize: 10, color: C.accent, marginBottom: 8 }}>Selected plan</div>
            <strong style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>
              {analysis.decision.selected_candidate}
            </strong>
            <p style={{ margin: 0, fontSize: 13, lineHeight: 1.65, color: '#cfc6cd' }}>
              {analysis.decision.reasoning}
            </p>
          </div>

          {analysis.decision.key_trade_offs?.length > 0 && (
            <div className="fade d2" style={{ marginBottom: 16 }}>
              <div style={{ ...cap, fontSize: 10, marginBottom: 8 }}>Trade-offs</div>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5, color: C.muted, lineHeight: 1.7 }}>
                {analysis.decision.key_trade_offs.map((t) => <li key={t}>{t}</li>)}
              </ul>
            </div>
          )}

          {analysis.assets_analysis.map((a) => {
            const card = a.summary_card
            const fin = card.financial?.main_metric
            const soc = card.social?.main_metric
            const env = card.environmental?.main_metrics ?? []
            const saved = card.financial?.counterfactual?.capex_saved_rm
            const averted = card.environmental?.counterfactual?.net_carbon_averted_tco2e

            return (
              <div key={a.asset_id} className="fade d3" style={{
                padding: 15, marginBottom: 12, background: C.card,
                border: `1px solid ${previewing ? C.selected : C.line}`, borderRadius: 8,
              }}>
                <div style={{ ...mono, fontSize: 12, marginBottom: 10 }}>{a.asset_id}</div>
                {fin && <MetricLine m={fin} />}
                {soc && <MetricLine m={soc} />}
                {env.map((m) => (
                  <MetricLine key={m.label} m={m} lowerIsBetter />
                ))}

                {(saved !== undefined || averted !== undefined) && (
                  <div style={{ marginTop: 12, paddingTop: 12, borderTop: `1px solid ${C.line}` }}>
                    {saved !== undefined && (
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, fontSize: 12.5, padding: '4px 0' }}>
                        <span style={{ color: '#cfc6cd' }}>CAPEX avoided vs new build</span>
                        <span style={{ ...mono, marginLeft: 'auto', color: '#3fb27f' }}>{fmt(saved, 'RM')}</span>
                      </div>
                    )}
                    {averted !== undefined && (
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, fontSize: 12.5, padding: '4px 0' }}>
                        <span style={{ color: '#cfc6cd' }}>Embodied carbon averted</span>
                        <span style={{ ...mono, marginLeft: 'auto', color: '#3fb27f' }}>
                          {fmt(averted, 'tCO2e')} tCO₂e
                        </span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}

          <div className="fade d4" style={{
            padding: 15, marginBottom: 14, background: C.card,
            border: `1px solid ${C.line}`, borderRadius: 8,
          }}>
            <div style={{ ...cap, fontSize: 10, color: C.accent, marginBottom: 8 }}>Recommendation</div>
            <p style={{ margin: 0, fontSize: 13, lineHeight: 1.65, color: '#cfc6cd' }}>
              {analysis.decision.justification.recommendation}
            </p>
            {analysis.decision.justification.beyond_the_model && (
              <p style={{ margin: '10px 0 0', fontSize: 12, lineHeight: 1.6, color: C.faint }}>
                Beyond the model: {analysis.decision.justification.beyond_the_model}
              </p>
            )}
          </div>

          <div style={{ display: 'flex', gap: 8, marginBottom: 4 }}>
            <button
              className="btn"
              onClick={() => (previewing ? props.onClearPreview() : props.onPreview())}
              style={btn()}
            >
              {previewing ? 'Clear preview' : 'Preview on map'}
            </button>
            <button className="btn" onClick={props.onSimulate} style={btn()}>
              Full comparison
            </button>
          </div>

          <hr style={rule} />
        </>
      )}

      <label htmlFor="q" style={{ ...cap, fontSize: 10, display: 'block', marginBottom: 10 }}>
        {analysis
          ? 'Ask a follow-up'
          : multi
            ? `Ask about these ${assets.length} assets`
            : `Ask about ${assets[0].name}`}
      </label>
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          id="q" className="inp"
          value={props.question}
          onChange={(e) => props.setQuestion(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') props.onAsk() }}
          placeholder={analysis
            ? 'What if we prioritise environmental return?'
            : 'What should we do with these assets?'}
          style={{
            flex: 1, minWidth: 0, font: 'inherit', fontSize: 13, padding: '11px 13px',
            borderRadius: 7, border: `1px solid ${C.line}`, background: '#241c23', color: C.text,
          }}
        />
        <button
          className={`btn primary${props.loading ? ' thinking' : ''}`}
          onClick={props.onAsk} disabled={props.loading} style={btn(true)}
        >
          {props.loading ? 'Thinking…' : 'Ask'}
        </button>
      </div>
      {!analysis && (
        <p style={{ fontSize: 11.5, color: C.faint, lineHeight: 1.6, marginTop: 10 }}>
          Diagnosis is fact. Recommendations appear only when you ask. The LLM call takes a while.
        </p>
      )}
    </>
  )
}