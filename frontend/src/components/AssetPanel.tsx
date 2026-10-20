import { C, cap, mono, btn } from '../theme'
import { Bar } from './ui'
import type { Asset, AiAnswer, AssetStatus } from '../types'

const STATUS_COLOR: Record<AssetStatus, string> = {
  healthy: '#3fb27f',
  monitor: '#f7931d',
  deadspace_candidate: '#d71920',
  underperforming_facility: '#d71920',
  development_risk: '#f15c22',
  improvement_opportunity: '#f7931d',
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

export function AssetPanel(props: {
  assets: Asset[]
  question: string
  setQuestion: (v: string) => void
  answer: AiAnswer | null
  loading: boolean
  onAsk: () => void
  previewing: boolean
  onPreview: () => void
  onClearPreview: () => void
  onSimulate: () => void
  onClose: () => void
}) {
  const { assets, answer, previewing } = props
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
        const col = d ? STATUS_COLOR[d.status] ?? C.muted : C.muted

        return (
          <div key={asset.id} style={{ marginTop: idx === 0 ? 10 : 26 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
              <h2 className="fade" style={{ ...mono, margin: 0, fontSize: 19, fontWeight: 500 }}>
                {asset.id}
              </h2>
              <span style={{ fontSize: 12, color: C.faint }}>
                {asset.subtype ?? asset.building_type}
              </span>
            </div>

            <div className="fade" style={{
              fontSize: 11, letterSpacing: '.11em', textTransform: 'uppercase',
              color: col, fontWeight: 600, marginTop: 7,
            }}>
              {d ? pretty(d.status) : 'No diagnosis'}
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

            {d && d.contributing_factors.length > 0 && (
              <>
                <hr style={rule} />
                <div className="fade d2">
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
                <div className="fade d3">
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

            {d && d.layer3.candidate_interventions.length > 0 && (
              <div style={{ fontSize: 11.5, color: C.faint, marginTop: 14, lineHeight: 1.6 }}>
                Available actions: {d.layer3.candidate_interventions.map(pretty).join(', ').toLowerCase()}
              </div>
            )}
          </div>
        )
      })}

      <hr style={rule} />

      {answer && (
        <>
          <div className="fade" style={{ ...cap, fontSize: 10, marginBottom: 6 }}>Your question</div>
          <p className="fade" style={{ margin: '0 0 14px', fontSize: 14, fontStyle: 'italic' }}>
            “{answer.asked}”
          </p>

          <div className="fade d1" style={{
            padding: 15, background: C.card, border: `1px solid ${C.line}`,
            borderRadius: 8, marginBottom: 18,
          }}>
            <div style={{ ...cap, fontSize: 10, color: C.accent, marginBottom: 8 }}>Reasoning</div>
            <p style={{ margin: 0, fontSize: 13, lineHeight: 1.65, color: '#cfc6cd' }}>
              {answer.reasoning_trace}
            </p>
          </div>

          <div style={{ ...cap, fontSize: 10, marginBottom: 12 }}>
            Proposed plan{answer.plan.length > 1 ? ` · ${answer.plan.length} assets` : ''}
          </div>

          {answer.plan.map((p, i) => (
            <div key={p.asset_id} className={`opt-card fade d${Math.min(i + 1, 5)}`} style={{
              padding: 15, marginBottom: 12, background: C.card, borderRadius: 8,
              border: `1px solid ${previewing ? C.selected : C.line}`,
            }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 9 }}>
                <strong style={{ ...mono, fontSize: 13 }}>{p.asset_id}</strong>
                <span style={{ fontSize: 14, color: C.selected }}>{pretty(p.type)}</span>
                {typeof p.parameters.to_subtype === 'string' && (
                  <span style={{ fontSize: 12, color: C.faint }}>→ {p.parameters.to_subtype}</span>
                )}
              </div>
              <p style={{ margin: '9px 0 0', fontSize: 12.5, color: C.muted, lineHeight: 1.55 }}>
                {p.rationale}
              </p>
            </div>
          ))}

          {answer.justification && (
            <div className="fade" style={{
              padding: 15, marginBottom: 12, background: C.card,
              border: `1px solid ${C.line}`, borderRadius: 8,
            }}>
              <div style={{ ...cap, fontSize: 10, color: C.accent, marginBottom: 8 }}>Recommendation</div>
              <p style={{ margin: 0, fontSize: 13, lineHeight: 1.65, color: '#cfc6cd' }}>
                {answer.justification.recommendation}
              </p>
            </div>
          )}

          <div style={{ display: 'flex', gap: 8, marginBottom: 4 }}>
            <button
              className="btn"
              onClick={() => (previewing ? props.onClearPreview() : props.onPreview())}
              style={btn()}
            >
              {previewing ? 'Clear preview' : 'Preview on map'}
            </button>
            <button className="btn" onClick={props.onSimulate} style={btn()}>Simulate</button>
          </div>

          <hr style={rule} />
        </>
      )}

      <label htmlFor="q" style={{ ...cap, fontSize: 10, display: 'block', marginBottom: 10 }}>
        {answer
          ? 'Ask a follow-up'
          : multi
            ? `Ask about these ${assets.length} assets`
            : `Ask about ${assets[0].id}`}
      </label>
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          id="q" className="inp"
          value={props.question}
          onChange={(e) => props.setQuestion(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') props.onAsk() }}
          placeholder={answer
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
      {!answer && (
        <p style={{ fontSize: 11.5, color: C.faint, lineHeight: 1.6, marginTop: 10 }}>
          Diagnosis is fact. Recommendations appear only when you ask.
        </p>
      )}
    </>
  )
}