import { C, cap, mono, bandColor, tierColor } from '../theme'
import type { Tier } from '../types'

export function Gauge({ score }: { score: number }) {
  const r = 46
  const circ = 2 * Math.PI * r
  const col = bandColor(score)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
      <svg width={118} height={118} viewBox="0 0 120 120" role="img" aria-label={`Performance score ${score} out of 100`}>
        <circle cx="60" cy="60" r={r} fill="none" stroke="#3e333d" strokeWidth="7" />
        <circle
          cx="60" cy="60" r={r} fill="none" stroke={col} strokeWidth="7" strokeLinecap="round"
          strokeDasharray={`${(score / 100) * circ} ${circ}`}
          transform="rotate(-90 60 60)"
          style={{ transition: 'stroke-dasharray .6s cubic-bezier(.22,.8,.3,1), stroke .3s ease' }}
        />
        <text x="54" y="68" textAnchor="middle" fontSize="33" fill={C.text} style={mono}>{score}</text>
        <text x="74" y="68" textAnchor="start" fontSize="10" fill={C.faint} style={mono}>/100</text>
      </svg>
      <span style={{ ...cap, fontSize: 9.5 }}>Performance</span>
    </div>
  )
}

export function Bar({ label, value, color, suffix }: { label: string; value: number; color: string; suffix?: string }) {
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 6 }}>
        <span style={{ color: '#cfc6cd' }}>{label}</span>
        <span style={{ ...mono, color: C.text }}>{value}{suffix ?? ''}</span>
      </div>
      <div style={{ height: 4, borderRadius: 2, background: '#3e333d', overflow: 'hidden' }}>
        <div style={{
          width: `${Math.min(value, 100)}%`, height: '100%', background: color,
          transition: 'width .55s cubic-bezier(.22,.8,.3,1), background .3s ease',
        }} />
      </div>
    </div>
  )
}

export function TierDot({ tier }: { tier: Tier }) {
  return <span style={{ width: 6, height: 6, borderRadius: '50%', flex: 'none', display: 'inline-block', background: tierColor[tier] }} />
}

export function TierKey() {
  return (
    <div style={{ display: 'flex', gap: 14, fontSize: 10.5, color: C.faint, marginTop: 10 }}>
      {(['observed', 'estimated', 'scenario'] as Tier[]).map((t) => (
        <span key={t} style={{ display: 'flex', alignItems: 'center', gap: 5, textTransform: 'capitalize' }}>
          <TierDot tier={t} />{t}
        </span>
      ))}
    </div>
  )
}

export function Stat({ label, value, unit, tier }: { label: string; value: string; unit?: string; tier: Tier }) {
  return (
    <div style={{ flex: 1 }}>
      <div style={{ ...cap, fontSize: 10, marginBottom: 6 }}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 5 }}>
        <span style={{ ...mono, fontSize: 26 }}>{value}</span>
        {unit && <span style={{ fontSize: 12, color: C.faint }}>{unit}</span>}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 10.5, color: C.faint, marginTop: 5, textTransform: 'capitalize' }}>
        <TierDot tier={tier} />{tier}
      </div>
    </div>
  )
}

export function MapLegend({ preview, year }: { preview: boolean; year: 'now' | '3y' }) {
  const items: Array<[string, string]> = [
    [C.bad, 'Underperforming'],
    [C.warn, 'At risk'],
    [C.good, 'Performing'],
    [C.selected, 'Selected'],
  ]
  if (preview) items.push([C.spill, 'Spillover'])

  return (
    <div className="pop" style={{
      position: 'absolute', left: 20, bottom: 20, padding: '14px 18px', borderRadius: 10,
      background: 'rgba(31,24,30,.94)', border: `1px solid ${C.line}`,
      backdropFilter: 'blur(6px)', minWidth: 236,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 }}>
        <span style={{ ...cap, fontSize: 10 }}>Performance score</span>
        <span style={{ ...cap, fontSize: 10, color: C.faint }}>{year === 'now' ? 'Current' : '+3 years'}</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '10px 14px' }}>
        {items.map(([c, label]) => (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: '#cfc6cd' }}>
            <span style={{ width: 9, height: 9, borderRadius: '50%', background: c, flex: 'none' }} />{label}
          </div>
        ))}
      </div>
    </div>
  )
}

export function MapControls({ bearing, tilted, onZoom, onCompass, onTilt }: {
  bearing: number
  tilted: boolean
  onZoom: (d: 1 | -1) => void
  onCompass: () => void
  onTilt: () => void
}) {
  const box: React.CSSProperties = {
    width: 44, height: 42, display: 'flex', alignItems: 'center', justifyContent: 'center',
    background: 'transparent', border: 0, color: '#cfc6cd', cursor: 'pointer',
    fontSize: 18, fontFamily: 'inherit', lineHeight: 1,
  }
  const div = <div style={{ height: 1, background: C.line }} />

  return (
    <div style={{
      position: 'absolute', right: 20, top: 20, borderRadius: 11, overflow: 'hidden',
      background: 'rgba(31,24,30,.94)', border: `1px solid ${C.line}`, backdropFilter: 'blur(6px)',
      display: 'flex', flexDirection: 'column', boxShadow: '0 6px 18px rgba(0,0,0,.3)',
    }}>
      <button className="ctrl" onClick={onCompass} aria-label="Reset bearing to north"
        style={{ ...box, flexDirection: 'column', height: 52, gap: 3 }}>
        <span style={{ fontSize: 9, letterSpacing: '.12em', color: C.faint, fontWeight: 700 }}>N</span>
        <svg width="14" height="16" viewBox="0 0 14 16"
          style={{ transform: `rotate(${-bearing}deg)`, transition: 'transform .25s ease' }} aria-hidden="true">
          <path d="M7 1 L11 14 L7 11 Z" fill={C.accent} />
          <path d="M7 1 L3 14 L7 11 Z" fill="#6d5c6a" />
        </svg>
      </button>
      {div}
      <button className="ctrl" onClick={onTilt} aria-label={tilted ? 'Switch to flat view' : 'Switch to 3D view'}
        style={{ ...box, fontSize: 10, letterSpacing: '.1em', fontWeight: 700, color: tilted ? C.accent : '#cfc6cd' }}>
        {tilted ? '3D' : '2D'}
      </button>
      {div}
      <button className="ctrl" onClick={() => onZoom(1)} aria-label="Zoom in" style={box}>+</button>
      {div}
      <button className="ctrl" onClick={() => onZoom(-1)} aria-label="Zoom out" style={box}>−</button>
    </div>
  )
}