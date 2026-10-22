import { C, cap, mono, btn } from '../theme'
import { Bar } from './ui'
import type { Asset, AnalyzeResult, MainMetric } from '../types'
import type { AnalyzeHistoryItem } from '../App'

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

function fmt(v: number | null | undefined, unit: string) {
  if (v === null || v === undefined || Number.isNaN(v) || String(v).toLowerCase() === 'nan') {
    return '—'
  }
  if (unit === 'ratio') return `${(v * 100).toFixed(1)}%`
  if (unit === 'RM') return `RM ${Math.round(v).toLocaleString()}`
  if (unit.startsWith('tCO2e')) return `${v.toLocaleString(undefined, { maximumFractionDigits: 1 })}`
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

function SectionTitle({ title, color = C.accent }: { title: string; color?: string }) {
  return (
    <div style={{ ...cap, fontSize: 11, color, borderBottom: `1px solid ${C.line}`, paddingBottom: 6, marginBottom: 12, marginTop: 24, letterSpacing: '0.05em' }}>
      {title}
    </div>
  )
}

function MetricLine({ m, lowerIsBetter }: { m: MainMetric; lowerIsBetter?: boolean }) {
  const moved = m.baseline !== null && m.intervention !== null && Math.abs(m.intervention - m.baseline) > 1e-9
  const better = moved && m.baseline !== null && m.intervention !== null
      ? (lowerIsBetter ? m.intervention < m.baseline : m.intervention > m.baseline)
      : null

  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, padding: '6px 0', fontSize: 12.5 }}>
      <span style={{ color: '#cfc6cd' }}>{m.label}</span>
      <span style={{ ...mono, marginLeft: 'auto', color: C.faint }}>{fmt(m.baseline, m.unit)}</span>
      <span style={{ color: C.faint }}>→</span>
      <span style={{ ...mono, fontWeight: 600, color: better === null ? C.text : better ? '#3fb27f' : '#d71920' }}>
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
  history: AnalyzeHistoryItem[] // Add history prop
}) {
  const { assets, analysis, asked, error, previewing, history } = props
  const multi = assets.length > 1

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      
      <div className="fade" style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        <span style={{ ...cap, fontSize: 10 }}>
          {multi ? `${assets.length} assets selected` : 'Selected asset'}
        </span>
        <span style={{ flex: 1 }} />
        <button className="ctrl" onClick={props.onClose} style={{ background: 'none', border: 0, color: C.muted, fontSize: 20, cursor: 'pointer', width: 30, height: 30, borderRadius: 6, lineHeight: 1, flex: 'none' }}>×</button>
      </div>

      {!multi && !analysis && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 12, padding: '8px 11px', borderRadius: 7, background: C.card, border: `1px solid ${C.line}`, fontSize: 11.5, color: C.faint, lineHeight: 1.5 }}>
          <kbd style={{ ...mono, fontSize: 10, padding: '2px 6px', borderRadius: 4, background: '#2b212a', border: `1px solid ${C.line}`, color: '#cfc6cd' }}>Ctrl</kbd>
          click another asset to analyse them together
        </div>
      )}

      <div style={{ flex: 1, overflowY: 'auto', paddingRight: 4 }}>
        {assets.map((asset, idx) => {
          const d = asset.diagnosis
          const p = asset.profile
          const col = d ? STATUS_COLOR[d.status] ?? C.muted : STATUS_COLOR[asset.mapStatus] ?? C.muted

          // Check if this asset has a globally accepted intervention
          const acceptedItem = history.find(h => h.status === 'accepted')
          const isPrimaryIntervened = acceptedItem?.result.interventions?.some(i => i.target_asset_id === asset.id && i.role === 'primary')
          
          // Check current analysis for catalytic links
          const isCatalyticBeneficiary = analysis?.interventions?.some(i => i.beneficiary_asset_id === asset.id)
          const catalyticTargetId = analysis?.interventions?.find(i => i.beneficiary_asset_id === asset.id)?.target_asset_id

          return (
            <div key={asset.id} style={{ marginTop: idx === 0 ? 6 : 36 }}>
              
              <h2 className="fade" style={{ margin: 0, fontSize: 22, fontWeight: 600, letterSpacing: '-0.01em' }}>{asset.name}</h2>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 4 }}>
                <span style={{ ...mono, fontSize: 12, color: C.faint }}>
                  {asset.id.startsWith('A-') ? asset.id.replace('A-', 'FAC-') : 
                   asset.id.startsWith('G-') ? asset.id.replace('G-', 'GRN-') : 
                   asset.id}
                </span>
                <span style={{ fontSize: 13, color: C.faint }}>
                  · {asset.subtype ? asset.subtype.replace(/_/g, ' ') : asset.assetType}
                </span>
              </div>

              <div className="fade" style={{ display: 'inline-block', fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase', color: col, fontWeight: 700, marginTop: 12, border: `1px solid ${col}`, borderRadius: 4, padding: '3px 8px', background: `${col}15` }}>
                {pretty(d?.status ?? asset.mapStatus)}

                  {p?.authority && (
                    <div style={{ 
                      fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase', 
                      color: p.authority.level === 'full_control' ? '#3fb27f' : p.authority.level === 'shared' ? '#f7931d' : '#d71920', 
                      fontWeight: 700, border: `1px solid currentColor`, borderRadius: 4, 
                      padding: '3px 8px', background: 'rgba(255,255,255,0.05)' 
                    }}>
                      🔒 {p.authority.level.replace('_', ' ')}
                    </div>
                  )}
              </div>

              {/* 1. Key Figures */}
              {p && (
                <>
                  <SectionTitle title="Core Metrics" />
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px 20px', fontSize: 13 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: `1px dashed ${C.line}`, paddingBottom: 6 }}>
                      <span style={{ color: C.muted }}>Occupancy</span>
                      <span style={{ ...mono, fontWeight: 500 }}>{fmt(p.social.occupancy_rate ?? p.social.utilisation_rate, 'ratio')}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: `1px dashed ${C.line}`, paddingBottom: 6 }}>
                      <span style={{ color: C.muted }}>Stranded Carbon</span>
                      <span style={{ ...mono, fontWeight: 500, color: (p.environmental.stranded_carbon_ratio ?? 0) > 0.5 ? '#d71920' : C.text }}>
                        {fmt(p.environmental.stranded_carbon_ratio, 'ratio')}
                      </span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: `1px dashed ${C.line}`, paddingBottom: 6 }}>
                      <span style={{ color: C.muted }}>Annual NOI</span>
                      <span style={{ ...mono, fontWeight: 500, color: (p.financial.noi_rm ?? 0) < 0 ? '#d71920' : C.text }}>
                        {fmt(p.financial.noi_rm, 'RM')}
                      </span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: `1px dashed ${C.line}`, paddingBottom: 6 }}>
                      <span style={{ color: C.muted }}>Walk Coverage</span>
                      <span style={{ ...mono, fontWeight: 500 }}>{fmt(p.social.coverage_ratio_10min_walk, 'ratio')}</span>
                    </div>
                  </div>
                </>
              )}

              {/* 2. Intervention Alerts */}
              {isPrimaryIntervened && (
                <div style={{ marginTop: 16, padding: 12, background: 'rgba(0,210,255,0.1)', border: '1px solid rgba(0,210,255,0.3)', borderRadius: 6 }}>
                  <span style={{ fontSize: 11, color: '#00d2ff', fontWeight: 600 }}>🚧 PRIMARY INTERVENTION ACTIVE</span>
                  <p style={{ margin: '4px 0 0', fontSize: 12, color: '#cfc6cd' }}>
                    This asset is currently undergoing primary structural intervention.
                  </p>
                </div>
              )}

              {isCatalyticBeneficiary && (
                <div style={{ marginTop: 16, padding: 12, background: 'rgba(168,85,247,0.1)', border: '1px solid rgba(168,85,247,0.3)', borderRadius: 6 }}>
                  <span style={{ fontSize: 11, color: '#a855f7', fontWeight: 600 }}>✨ CATALYTIC BENEFICIARY</span>
                  <p style={{ margin: '4px 0 0', fontSize: 12, color: '#cfc6cd' }}>
                    This asset benefits from nearby intervention at <b>{catalyticTargetId}</b>.
                  </p>
                </div>
              )}

              {/* 3. Diagnosis */}
              {d && (d.flags.length > 0 || d.contributing_factors.length > 0) && (
                <>
                  <SectionTitle title="Diagnosis" />
                  {d.flags.length > 0 && (
                    <div className="fade d1" style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 16 }}>
                      {d.flags.map((f) => (
                        <span key={f} style={{ fontSize: 11, padding: '4px 10px', borderRadius: 6, background: C.card, border: `1px solid ${C.line}`, color: '#cfc6cd' }}>
                          {pretty(f)}
                        </span>
                      ))}
                    </div>
                  )}
                  {d.contributing_factors.length > 0 && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 16 }}>
                      {d.contributing_factors.map((f) => (
                        <Bar key={f.factor} label={pretty(f.factor)} value={Math.round(f.contribution * 100)} color={col} suffix="%" />
                      ))}
                    </div>
                  )}
                </>
              )}

              {/* 4. Evidence */}
              {d && d.evidence.length > 0 && (
                <>
                  <SectionTitle title="Supporting Evidence" color="#cfc6cd" />
                  <p style={{ fontSize: 10, color: C.faint, marginTop: -8, marginBottom: 8, fontStyle: 'italic' }}>
                    (Baseline diagnostic evidence from 2026)
                  </p>
                  <div className="fade d2" style={{ background: 'rgba(255,255,255,0.02)', borderRadius: 8, padding: '4px 12px', border: `1px solid ${C.line}` }}>
                    {d.evidence.map((line, i) => {
                      const splitIdx = line.indexOf(':')
                      const isMultiLine = line.includes('\n')
                      if (splitIdx !== -1 && !isMultiLine) {
                        const label = line.slice(0, splitIdx).trim()
                        let value = line.slice(splitIdx + 1).trim()
                          value = value.replace(/nan/gi, '—')
                        return (
                          <div key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 12, fontSize: 12.5, padding: '10px 0', borderBottom: i === d.evidence.length - 1 ? 'none' : `1px dashed ${C.line}` }}>
                            <span style={{ color: C.muted, flex: 1, lineHeight: 1.4 }}>{label}</span>
                            <span style={{ ...mono, color: C.text, textAlign: 'right', flexShrink: 0, fontWeight: 500 }}>{value}</span>
                          </div>
                        )
                      }
                      
                      let safeLine = splitIdx !== -1 ? line.slice(splitIdx + 1).trim() : line;
                      safeLine = safeLine.replace(/nan/gi, '—');
                      return (
                        <div key={i} style={{ padding: '10px 0', borderBottom: i === d.evidence.length - 1 ? 'none' : `1px dashed ${C.line}` }}>
                          {splitIdx !== -1 && (
                            <div style={{ fontSize: 12, fontWeight: 600, color: C.accent, marginBottom: 4 }}>
                              {line.slice(0, splitIdx).trim()}
                            </div>
                          )}
                          <div style={{ fontSize: 12.5, color: '#cfc6cd', whiteSpace: 'pre-wrap', lineHeight: 1.5, fontFamily: mono.fontFamily }}>
                            {safeLine}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </>
              )}
            </div>
          )
        })}

        <hr style={{ border: 0, borderTop: `1px solid ${C.line}`, margin: '28px 0' }} />

        {error && (
          <div className="fade" style={{ padding: 14, marginBottom: 20, borderRadius: 8, background: 'rgba(215,25,32,0.1)', border: '1px solid rgba(215,25,32,0.3)', fontSize: 13, color: '#f0b8b8' }}>
            {error}
          </div>
        )}

        {analysis && (
          <div className="fade d3">
            <div style={{ ...cap, fontSize: 10, color: C.faint, marginBottom: 8 }}>Analysis Query</div>
            <p style={{ margin: '0 0 24px', fontSize: 14, fontStyle: 'italic', color: '#cfc6cd', lineHeight: 1.6 }}>“{asked}”</p>

            <SectionTitle title="AI Selected Plan" color="#3fb27f" />
            <div style={{ padding: 16, background: 'rgba(63,178,127,0.08)', border: `1px solid rgba(63,178,127,0.3)`, borderRadius: 8, marginBottom: 20 }}>
              <strong style={{ fontSize: 15, display: 'block', marginBottom: 8, color: '#fff' }}>{analysis.decision.selected_candidate}</strong>
              <p style={{ margin: 0, fontSize: 13, lineHeight: 1.65, color: '#cfc6cd' }}>{analysis.decision.reasoning}</p>
            </div>

            {analysis.decision.key_trade_offs?.length > 0 && (
              <div style={{ marginBottom: 24 }}>
                <div style={{ ...cap, fontSize: 10, color: C.muted, marginBottom: 10 }}>Key Trade-offs</div>
                <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: '#cfc6cd', lineHeight: 1.7 }}>
                  {analysis.decision.key_trade_offs.map((t) => <li key={t} style={{ marginBottom: 4 }}>{t}</li>)}
                </ul>
              </div>
            )}

            <SectionTitle title="Simulated Outcomes" color="#2196f3" />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginBottom: 24 }}>
              {analysis.assets_analysis.map((a) => {
                const card = a.summary_card
                const fin = card.financial?.main_metric
                const soc = card.social?.main_metric
                const env = card.environmental?.main_metrics ?? []
                const saved = card.financial?.counterfactual?.capex_saved_rm
                const averted = card.environmental?.counterfactual?.net_carbon_averted_tco2e

                return (
                  <div key={a.asset_id} style={{ padding: 16, background: C.card, border: `1px solid ${C.line}`, borderRadius: 8 }}>
                    <div style={{ ...mono, fontSize: 13, fontWeight: 600, marginBottom: 12, color: '#fff' }}>{a.asset_id}</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {fin && <MetricLine m={fin} />}
                      {soc && <MetricLine m={soc} />}
                      {env.map((m) => <MetricLine key={m.label} m={m} lowerIsBetter />)}
                    {/* 渲染 Subunits 表格 */}
                    {card.subunits && card.subunits.length > 0 && (
                      <div style={{ marginTop: 14, paddingTop: 14, borderTop: `1px dashed ${C.line}` }}>
                        <div style={{ ...cap, fontSize: 10, color: C.accent, marginBottom: 8 }}>Subtype Breakdown</div>
                        <table style={{ width: '100%', fontSize: 11.5, borderCollapse: 'collapse' }}>
                          <thead>
                            <tr style={{ borderBottom: `1px solid ${C.line}`, color: C.muted, textAlign: 'left' }}>
                              <th style={{ paddingBottom: 4, fontWeight: 500 }}>Subtype</th>
                              <th style={{ paddingBottom: 4, fontWeight: 500, textAlign: 'right' }}>Area</th>
                              <th style={{ paddingBottom: 4, fontWeight: 500, textAlign: 'right' }}>Occ %</th>
                            </tr>
                          </thead>
                          <tbody>
                            {card.subunits.map((sub: any) => {
                              const isDead = sub.occupancy_intervention === 0;
                              return (
                                <tr key={sub.subtype} style={{ borderBottom: `1px solid rgba(255,255,255,0.05)` }}>
                                  <td style={{ padding: '6px 0', textTransform: 'capitalize', color: isDead ? C.faint : C.text }}>
                                    {sub.subtype.replace(/_/g, ' ')}
                                  </td>
                                  <td style={{ padding: '6px 0', textAlign: 'right', ...mono, color: C.muted }}>
                                    {sub.area_m2} m²
                                  </td>
                                  <td style={{ padding: '6px 0', textAlign: 'right', ...mono }}>
                                    <span style={{ color: isDead ? C.faint : C.text }}>{(sub.occupancy_baseline * 100).toFixed(0)}%</span>
                                    <span style={{ color: C.faint, margin: '0 4px' }}>→</span>
                                    <span style={{ 
                                      color: isDead ? C.faint : (sub.occupancy_intervention > sub.occupancy_baseline ? '#3fb27f' : C.text), 
                                      fontWeight: 600 
                                    }}>
                                      {isDead ? 'Removed' : `${(sub.occupancy_intervention * 100).toFixed(0)}%`}
                                    </span>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                    </div>
                    {(saved !== undefined || averted !== undefined) && (
                      <div style={{ marginTop: 14, paddingTop: 14, borderTop: `1px dashed ${C.line}`, display: 'flex', flexDirection: 'column', gap: 8 }}>
                        {saved !== undefined && (
                          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, fontSize: 13 }}>
                            <span style={{ color: C.muted }}>CAPEX avoided vs new build</span>
                            <span style={{ ...mono, marginLeft: 'auto', color: '#3fb27f', fontWeight: 600 }}>{fmt(saved, 'RM')}</span>
                          </div>
                        )}
                        {averted !== undefined && (
                          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, fontSize: 13 }}>
                            <span style={{ color: C.muted }}>Embodied carbon averted</span>
                            <span style={{ ...mono, marginLeft: 'auto', color: '#3fb27f', fontWeight: 600 }}>{fmt(averted, 'tCO2e')} tCO₂e</span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>

            <div style={{ padding: 16, background: 'rgba(255,255,255,0.03)', border: `1px solid ${C.line}`, borderRadius: 8, marginBottom: 16 }}>
              <div style={{ ...cap, fontSize: 10, color: C.accent, marginBottom: 6 }}>Recommendation</div>
              <p style={{ margin: 0, fontSize: 13, lineHeight: 1.65, color: '#cfc6cd' }}>{analysis.decision.justification.recommendation}</p>
              {analysis.decision.justification.beyond_the_model && (
                <p style={{ margin: '12px 0 0', fontSize: 12, lineHeight: 1.6, color: C.faint }}><b>Beyond model:</b> {analysis.decision.justification.beyond_the_model}</p>
              )}
            </div>

            <div style={{ display: 'flex', gap: 10, marginBottom: 24 }}>
              <button className="btn" onClick={() => (previewing ? props.onClearPreview() : props.onPreview())} style={btn()}>
                {previewing ? 'Clear map preview' : 'Preview on map'}
              </button>
              <button className="btn primary" onClick={props.onSimulate} style={btn(true)}>View Full Comparison</button>
            </div>
          </div>
        )}
      </div>

      <div style={{ marginTop: 16, paddingTop: 16, borderTop: `1px solid ${C.line}` }}>
        <label htmlFor="q" style={{ ...cap, fontSize: 10, display: 'block', marginBottom: 10, color: C.faint }}>
          {analysis ? 'Ask a follow-up question' : multi ? `Ask about these ${assets.length} assets` : `Ask about ${assets[0].name}`}
        </label>
        <div style={{ display: 'flex', gap: 8 }}>
          <input id="q" className="inp" value={props.question} onChange={(e) => props.setQuestion(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') props.onAsk() }} placeholder={analysis ? 'What if we prioritise environmental return?' : 'What should we do with these assets?'} style={{ flex: 1, minWidth: 0, font: 'inherit', fontSize: 13, padding: '12px 14px', borderRadius: 8, border: `1px solid ${C.line}`, background: '#241c23', color: C.text }} />
          <button className={`btn primary${props.loading ? ' thinking' : ''}`} onClick={props.onAsk} disabled={props.loading} style={{ ...btn(true), padding: '0 20px' }}>
            {props.loading ? 'Thinking…' : 'Ask'}
          </button>
        </div>
      </div>
    </div>
  )
}