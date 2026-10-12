import { C, cap, mono, btn, bandColor } from '../theme'
import { Gauge, Bar, TierDot, TierKey, Stat } from './ui'
import type { Asset, AiAnswer, AiOption } from '../types'

const OPT_COLORS = [C.selected, C.good, C.muted]

export function AssetPanel(props: {
  asset: Asset
  year: 'now' | '3y'
  question: string
  setQuestion: (v: string) => void
  answer: AiAnswer | null
  loading: boolean
  onAsk: () => void
  preview: AiOption | null
  onPreview: (o: AiOption) => void
  onClearPreview: () => void
  onSimulate: () => void
  onClose: () => void
}) {
  const { asset, year, answer, preview } = props
  const now = year === 'now'
  const score = now ? asset.score : asset.score_3y
  const occ = now ? asset.occupancy : asset.occupancy_3y
  const bd = now ? asset.breakdown : asset.breakdown_3y
  const rule = { border: 0, borderTop: `1px solid ${C.line}`, margin: '20px 0' }

  return (
    <>
      <div className="fade" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ ...cap, fontSize: 10 }}>Selected asset</span>
        <span style={{ flex: 1 }} />
        <span style={{
          fontSize: 10, letterSpacing: '.12em', textTransform: 'uppercase', color: C.muted,
          border: `1px solid ${C.line}`, borderRadius: 5, padding: '4px 9px',
        }}>{asset.type.split('·')[0].trim()}</span>
        <button
          className="ctrl" onClick={props.onClose} aria-label="Close asset panel"
          style={{
            background: 'none', border: 0, color: C.muted, fontSize: 20, cursor: 'pointer',
            width: 30, height: 30, borderRadius: 6, lineHeight: 1, flex: 'none',
          }}
        >×</button>
      </div>

      <h2 className="fade" style={{ margin: '10px 0 18px', fontSize: 21, fontWeight: 500 }}>{asset.name}</h2>

      <div className="fade d1" style={{ display: 'flex', alignItems: 'center', gap: 22 }}>
        <Gauge score={score} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ ...cap, fontSize: 10, marginBottom: 12 }}>Weighted breakdown</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 13 }}>
            <Bar label="Financial" value={bd.financial} color={bandColor(bd.financial)} />
            <Bar label="Environmental" value={bd.environmental} color={bandColor(bd.environmental)} />
            <Bar label="Social" value={bd.social} color={bandColor(bd.social)} />
          </div>
        </div>
      </div>

      <hr style={rule} />

      <div className="fade d3" style={{ display: 'flex', gap: 20 }}>
        <Stat label="Occupancy" value={`${occ}%`} tier={now ? 'observed' : 'scenario'} />
        <div style={{ width: 1, background: C.line }} />
        <Stat label="Vacant" value={String(asset.vacancy_months)} unit="months" tier="observed" />
      </div>

      <hr style={rule} />

      <div className="fade d4">
        <div style={{ ...cap, fontSize: 10, marginBottom: 14 }}>Why it underperforms</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {asset.factors.map((f) => (
            <Bar key={f.label} label={f.label} value={f.weight} color={C.accent} suffix="%" />
          ))}
        </div>
      </div>

      <hr style={rule} />

      <div className="fade d5">
        <div style={{ ...cap, fontSize: 10, marginBottom: 6 }}>Evidence</div>
        {asset.evidence.map((e) => (
          <div key={e.label} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: '#cfc6cd', padding: '6px 0' }}>
            <TierDot tier={e.tier} />
            {e.label}
            <b style={{ ...mono, marginLeft: 'auto', fontWeight: 400, color: C.text }}>{e.value}</b>
          </div>
        ))}
        <TierKey />
      </div>

      <hr style={rule} />

      {answer && (
        <>
          <div className="fade" style={{ ...cap, fontSize: 10, marginBottom: 6 }}>Your question</div>
          <p className="fade" style={{ margin: '0 0 14px', fontSize: 14, fontStyle: 'italic' }}>“{answer.asked}”</p>

          <div className="fade d1" style={{
            padding: 15, background: C.card, border: `1px solid ${C.line}`,
            borderRadius: 8, marginBottom: 18,
          }}>
            <div style={{ ...cap, fontSize: 10, color: C.accent, marginBottom: 8 }}>Analysis</div>
            <p style={{ margin: 0, fontSize: 13, lineHeight: 1.65, color: '#cfc6cd' }}>{answer.analysis}</p>
          </div>

          <div style={{ ...cap, fontSize: 10, marginBottom: 12 }}>Candidate options</div>

          {answer.options.map((o, i) => {
            const active = preview?.id === o.id
            const col = OPT_COLORS[i % OPT_COLORS.length]
            return (
              <div key={o.id} className={`opt-card fade d${Math.min(i + 1, 5)}`} style={{
                padding: 15, marginBottom: 12, background: C.card, borderRadius: 8,
                border: `1px solid ${active ? col : C.line}`,
                boxShadow: active ? `0 0 0 1px ${col}44` : 'none',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                  <span style={{
                    width: 22, height: 22, flex: 'none', borderRadius: 5, background: `${col}22`,
                    border: `1px solid ${col}66`, color: col, display: 'flex', alignItems: 'center',
                    justifyContent: 'center', fontSize: 11, fontWeight: 700,
                  }}>{o.id}</span>
                  <strong style={{ fontSize: 14, color: col }}>{o.title.replace(/^Option [A-C] · /, '')}</strong>
                  {active && <span style={{ ...cap, fontSize: 9.5, color: col, marginLeft: 'auto' }}>Previewing</span>}
                </div>

                <p style={{ margin: '9px 0 13px', fontSize: 12.5, color: C.muted, lineHeight: 1.55 }}>{o.summary}</p>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '12px', marginBottom: 14 }}>
                  <div>
                    <div style={{ ...cap, fontSize: 9.5, marginBottom: 4 }}>CAPEX</div>
                    <div style={{ ...mono, fontSize: 14 }}>{o.capex}</div>
                  </div>
                  <div>
                    <div style={{ ...cap, fontSize: 9.5, marginBottom: 4 }}>Score</div>
                    <div style={{ ...mono, fontSize: 14 }}>
                      <span style={{ color: C.faint }}>{asset.score}</span>
                      <span style={{ color: C.faint, margin: '0 4px' }}>→</span>
                      <span style={{ color: bandColor(o.score_after) }}>{o.score_after}</span>
                    </div>
                  </div>
                  <div style={{ gridColumn: '1 / -1', paddingTop: 10, borderTop: `1px solid ${C.line}` }}>
                    <div style={{ ...cap, fontSize: 9.5, marginBottom: 4 }}>Embodied carbon avoided</div>
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                      <span style={{ ...mono, fontSize: 18, color: o.score_after > 40 ? C.good : C.muted }}>{o.carbon_avoided}</span>
                      <span style={{ fontSize: 11, color: C.faint }}>tonnes CO₂ not emitted</span>
                    </div>
                  </div>
                </div>

                {active && (
                  <ul style={{ paddingLeft: 18, margin: '0 0 13px', color: C.muted, fontSize: 12.5, lineHeight: 1.7 }}>
                    {o.changes.map((c) => <li key={c}>{c}</li>)}
                  </ul>
                )}

                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="btn" onClick={() => (active ? props.onClearPreview() : props.onPreview(o))} style={btn()}>
                    {active ? 'Clear preview' : 'Preview'}
                  </button>
                  <button className="btn" onClick={props.onSimulate} style={btn()}>Simulate</button>
                </div>
              </div>
            )
          })}

          <hr style={rule} />
        </>
      )}

      <label htmlFor="q" style={{ ...cap, fontSize: 10, display: 'block', marginBottom: 10 }}>
        {answer ? `Ask a follow-up about ${asset.id}` : `Ask about ${asset.id}`}
      </label>
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          id="q" className="inp"
          value={props.question}
          onChange={(e) => props.setQuestion(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') props.onAsk() }}
          placeholder={answer ? 'What if I prioritise environmental return?' : 'What should we do with this asset?'}
          style={{
            flex: 1, minWidth: 0, font: 'inherit', fontSize: 13, padding: '11px 13px',
            borderRadius: 7, border: `1px solid ${C.line}`, background: '#241c23', color: C.text,
          }}
        />
        <button className={`btn primary${props.loading ? ' thinking' : ''}`} onClick={props.onAsk} disabled={props.loading} style={btn(true)}>
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