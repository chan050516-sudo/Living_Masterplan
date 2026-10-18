import { C, cap, mono, btn, statusOf, humanize, fmt } from '../theme'
import { Bar, TierKey, Stat } from './ui'
import type { AssetProfile, AnalyzeResult } from '../types'

const MAX_FILES = 3

export function AssetPanel(props: {
  profile: AssetProfile
  question: string
  setQuestion: (v: string) => void
  files: File[]
  setFiles: (f: File[]) => void
  result: AnalyzeResult | null
  loading: boolean
  error: string | null
  onAsk: () => void
  showPlan: boolean
  onTogglePlan: () => void
  onShowResults: () => void
  onClose: () => void
}) {
  const { profile: p, result } = props
  const d = p.deadspace_diagnosis
  const status = statusOf(d.status)
  const occ = p.social.occupancy_rate ?? p.social.utilisation_rate
  const rule = { border: 0, borderTop: `1px solid ${C.line}`, margin: '20px 0' }

  return (
    <>
      <div className="fade" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ ...cap, fontSize: 10 }}>{p.identity.asset_id}</span>
        <span style={{ flex: 1 }} />
        <span style={{
          fontSize: 10, letterSpacing: '.12em', textTransform: 'uppercase', color: C.muted,
          border: `1px solid ${C.line}`, borderRadius: 5, padding: '4px 9px',
        }}>{humanize(p.identity.asset_type)}{p.identity.subtype ? ` · ${humanize(p.identity.subtype)}` : ''}</span>
        <button
          className="ctrl" onClick={props.onClose} aria-label="Close asset panel"
          style={{
            background: 'none', border: 0, color: C.muted, fontSize: 20, cursor: 'pointer',
            width: 30, height: 30, borderRadius: 6, lineHeight: 1, flex: 'none',
          }}
        >×</button>
      </div>

      <h2 className="fade" style={{ margin: '10px 0 10px', fontSize: 21, fontWeight: 500 }}>{p.identity.asset_name}</h2>

      <div className="fade d1" style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={{
          fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase', fontWeight: 600, color: status.color,
          border: `1px solid ${status.color}`, borderRadius: 5, padding: '3px 9px',
        }}>{status.label}</span>
        {d.urgency_index != null && (
          <span style={{ fontSize: 12, color: C.muted }}>Urgency <b style={{ ...mono, color: C.text }}>{fmt.num(d.urgency_index, 1)}</b></span>
        )}
        <span style={{ fontSize: 12, color: C.muted }}>
          {p.authority.level === 'full_control' ? 'Developer controlled' : humanize(p.authority.level ?? 'unknown authority')}
        </span>
      </div>

      <hr style={rule} />

      <div className="fade d2" style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '18px 20px' }}>
        <Stat label="Occupancy" value={fmt.pct(occ)} tier="observed" />
        <Stat label="Annual NOI" value={fmt.rm(p.financial.noi_rm)} tier="estimated" />
        <Stat label="Demand / supply" value={fmt.num(p.financial.dsr, 2)} unit="DSR" tier="estimated" />
        <Stat label="Vacant" value={fmt.num(p.trajectory.vacancy_streak_months)} unit="months" tier="observed" />
        <Stat label="Operational carbon" value={fmt.num(p.environmental.carbon_operational_tco2e)} unit="tCO₂e/yr" tier="estimated" />
        <Stat label="Stranded carbon" value={fmt.pct(p.environmental.stranded_carbon_ratio)} tier="estimated" />
      </div>

      {d.contributing_factors.length > 0 && (
        <>
          <hr style={rule} />
          <div className="fade d3">
            <div style={{ ...cap, fontSize: 10, marginBottom: 14 }}>Why it underperforms</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {d.contributing_factors.map((f) => (
                <Bar key={f.factor} label={humanize(f.factor)} value={Math.round(f.contribution * 100)} color={C.accent} suffix="%" />
              ))}
            </div>
          </div>
        </>
      )}

      <hr style={rule} />

      <div className="fade d4">
        <div style={{ ...cap, fontSize: 10, marginBottom: 6 }}>Evidence</div>
        {d.evidence.map((e, i) => {
          const sub = e.startsWith('  ')
          return (
            <div key={i} style={{
              fontSize: sub ? 12 : 12.5, color: sub ? C.muted : '#cfc6cd',
              padding: sub ? '2px 0 2px 14px' : '5px 0', lineHeight: 1.45,
            }}>{e.trim()}</div>
          )
        })}
        <TierKey />
      </div>

      <hr style={rule} />

      {result && <Decision result={result} showPlan={props.showPlan} onTogglePlan={props.onTogglePlan} onShowResults={props.onShowResults} rule={rule} />}

      <label htmlFor="q" style={{ ...cap, fontSize: 10, display: 'block', marginBottom: 10 }}>
        {result ? `Ask again about ${p.identity.asset_id}` : `Ask about ${p.identity.asset_id}`}
      </label>
      <textarea
        id="q" className="inp" rows={3}
        value={props.question}
        onChange={(e) => props.setQuestion(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); props.onAsk() } }}
        placeholder="e.g. What should we do with this asset? Budget RM 3m, no demolition."
        maxLength={5000}
        disabled={props.loading}
        style={{
          width: '100%', boxSizing: 'border-box', resize: 'vertical', font: 'inherit', fontSize: 13, padding: '11px 13px',
          borderRadius: 7, border: `1px solid ${C.line}`, background: '#241c23', color: C.text,
        }}
      />
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 8 }}>
        <label className="btn" style={{ ...btn(), opacity: props.loading ? 0.5 : 1 }}>
          Attach files
          <input
            type="file" multiple accept=".txt,.csv,.pdf" hidden disabled={props.loading}
            onChange={(e) => { props.setFiles(Array.from(e.target.files ?? []).slice(0, MAX_FILES)); e.target.value = '' }}
          />
        </label>
        <span style={{ flex: 1 }} />
        <button className={`btn primary${props.loading ? ' thinking' : ''}`} onClick={props.onAsk} disabled={props.loading} style={btn(true)}>
          {props.loading ? 'Analysing…' : 'Ask'}
        </button>
      </div>
      {props.files.length > 0 && (
        <div style={{ fontSize: 11.5, color: C.muted, marginTop: 8 }}>
          {props.files.map((f) => f.name).join(', ')}
          <button onClick={() => props.setFiles([])} style={{ background: 'none', border: 0, color: C.accent, cursor: 'pointer', fontSize: 11.5 }}>clear</button>
        </div>
      )}
      {props.loading && (
        <p style={{ fontSize: 11.5, color: C.faint, lineHeight: 1.6, marginTop: 10 }}>
          The AI is generating candidate plans and simulating each one. This usually takes 1–3 minutes.
        </p>
      )}
      {props.error && (
        <p style={{ fontSize: 12, color: C.bad, lineHeight: 1.5, marginTop: 10 }}>Analysis failed: {props.error}</p>
      )}
      {!result && !props.loading && !props.error && (
        <p style={{ fontSize: 11.5, color: C.faint, lineHeight: 1.6, marginTop: 10 }}>
          Diagnosis is fact. Recommendations appear only when you ask. Up to 3 .txt, .csv or .pdf files (10 MB each).
        </p>
      )}
    </>
  )
}

function Decision({ result, showPlan, onTogglePlan, onShowResults, rule }: {
  result: AnalyzeResult
  showPlan: boolean
  onTogglePlan: () => void
  onShowResults: () => void
  rule: React.CSSProperties
}) {
  const { decision } = result
  const j = decision.justification
  const sections: Array<[string, string | null]> = [
    ['Why this plan', j.why_this_plan],
    ['What the simulation shows', j.what_simulation_shows],
    ['Beyond the model', j.beyond_the_model],
    ['Recommendation', j.recommendation],
  ]

  return (
    <>
      <div className="fade" style={{ ...cap, fontSize: 10, color: C.accent, marginBottom: 6 }}>AI recommendation</div>
      <h3 className="fade" style={{ margin: '0 0 10px', fontSize: 16, fontWeight: 600 }}>{decision.selected_candidate}</h3>
      {j.summary && <p className="fade d1" style={{ margin: '0 0 14px', fontSize: 13, lineHeight: 1.65, color: '#cfc6cd' }}>{j.summary}</p>}

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <button className={`btn${showPlan ? ' primary' : ''}`} onClick={onTogglePlan} style={btn(showPlan)}>
          {showPlan ? 'Hide plan on map' : 'Show plan on map'}
        </button>
        <button className="btn" onClick={onShowResults} style={btn()}>Simulation results</button>
      </div>

      {sections.filter(([, text]) => text).map(([title, text], i) => (
        <div key={title} className={`fade d${Math.min(i + 1, 5)}`} style={{
          padding: 14, background: C.card, border: `1px solid ${C.line}`, borderRadius: 8, marginBottom: 10,
        }}>
          <div style={{ ...cap, fontSize: 9.5, marginBottom: 6 }}>{title}</div>
          <p style={{ margin: 0, fontSize: 12.5, lineHeight: 1.6, color: '#cfc6cd' }}>{text}</p>
        </div>
      ))}

      {decision.key_trade_offs.length > 0 && (
        <>
          <div style={{ ...cap, fontSize: 10, margin: '16px 0 6px' }}>Key trade-offs</div>
          <ul style={{ paddingLeft: 18, margin: 0, color: C.muted, fontSize: 12.5, lineHeight: 1.7 }}>
            {decision.key_trade_offs.map((t) => <li key={t}>{t}</li>)}
          </ul>
        </>
      )}

      {result.candidates_summary && result.candidates_summary.length > 0 && (
        <>
          <div style={{ ...cap, fontSize: 10, margin: '18px 0 10px' }}>Candidate plans considered</div>
          {result.candidates_summary.map((c) => {
            const chosen = c.name === decision.selected_candidate
            return (
              <div key={c.name} className="opt-card" style={{
                padding: 13, marginBottom: 10, background: C.card, borderRadius: 8,
                border: `1px solid ${chosen ? C.good : C.line}`,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <strong style={{ fontSize: 13, color: chosen ? C.good : C.text }}>{c.name}</strong>
                  {chosen && <span style={{ ...cap, fontSize: 9.5, color: C.good, marginLeft: 'auto' }}>Selected</span>}
                </div>
                {c.strategy_summary && <p style={{ margin: '7px 0 8px', fontSize: 12, color: C.muted, lineHeight: 1.55 }}>{c.strategy_summary}</p>}
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {c.plan.map((item, i) => (
                    <span key={i} style={{ ...mono, fontSize: 10.5, color: '#cfc6cd', border: `1px solid ${C.line}`, borderRadius: 4, padding: '2px 7px' }}>
                      {item.asset_id ?? '—'} · {humanize(String(item.type ?? 'action'))}
                    </span>
                  ))}
                </div>
              </div>
            )
          })}
        </>
      )}

      <hr style={rule} />
    </>
  )
}
