import { C, mono } from '../theme'

type Series = { label: string; values: (number | null)[]; color: string; dashed?: boolean }

/**
 * Two-line comparison chart drawn as inline SVG.
 * The shaded band between the lines is the effect of the intervention:
 * green where it improves the metric, red where it worsens it.
 * Nulls are treated as gaps (not zero) so a baseline-missing asset
 * does not incorrectly suggest a drop to 0.
 */
export function LineChart({ years, series, format, lowerIsBetter = false }: {
  years: string[]
  series: Series[]
  format?: (v: number) => string
  lowerIsBetter?: boolean
}) {
  const W = 560
  const H = 140
  const padL = 60
  const padR = 56
  const padT = 12
  const padB = 24

  // Only numeric values are used for min/max scaling.
  const numeric = series
    .flatMap((s) => s.values)
    .filter((v): v is number => v !== null && Number.isFinite(v))
  if (numeric.length === 0 || years.length === 0) return null

  let min = Math.min(...numeric)
  let max = Math.max(...numeric)
  const allPositive = min >= 0

  if (min === max) {
    const span = Math.abs(min) || 1
    min -= span * 0.5
    max += span * 0.5
  } else {
    const pad = (max - min) * 0.12
    max += pad
    min -= pad
  }
  if (allPositive) min = Math.max(0, min)
  if (max < 0) max = 0

  const x = (i: number) => padL + (i / Math.max(1, years.length - 1)) * (W - padL - padR)
  const y = (v: number) => padT + (1 - (v - min) / (max - min)) * (H - padT - padB)

  const fmt = format ?? ((v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 1 }))

  const baseline = series[0]
  const plan = series[1]

  // Compare the last *finite* value of each series, skipping nulls.
  const lastFinite = (values: (number | null)[]): number | null => {
    for (let i = values.length - 1; i >= 0; i--) {
      const v = values[i]
      if (v !== null && Number.isFinite(v)) return v
    }
    return null
  }

  let bandColour: string | null = null
  if (baseline && plan) {
    const b = lastFinite(baseline.values)
    const p = lastFinite(plan.values)
    if (b !== null && p !== null && Math.abs(p - b) > 1e-9) {
      const better = lowerIsBetter ? p < b : p > b
      bandColour = better ? '#3fb27f' : '#d71920'
    }
  }

  // The band is only drawn on segments where BOTH series have a number.
  const bandSegments: string[] = []
  if (baseline && plan && baseline.values.length === plan.values.length) {
    let opened = false
    for (let i = 0; i < plan.values.length; i++) {
      const pv = plan.values[i]
      const bv = baseline.values[i]
      if (pv === null || bv === null || !Number.isFinite(pv) || !Number.isFinite(bv)) {
        if (opened) { bandSegments.push('Z'); opened = false }
        continue
      }
      if (!opened) {
        bandSegments.push(`M${x(i)},${y(bv)}`)
        opened = true
      }
      // Trace forward along the plan, we close the band backwards in a second pass
      bandSegments.push(`L${x(i)},${y(pv)}`)
    }
    if (opened) bandSegments.push('Z')
  }

  const ticks = [max, (max + min) / 2, min]

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img"
      aria-label={series.map((s) => s.label).join(' versus ')}>
      {ticks.map((t, i) => (
        <g key={i}>
          <line x1={padL} x2={W - padR} y1={y(t)} y2={y(t)}
            stroke="#ffffff" strokeOpacity="0.06" strokeWidth="1" />
          <text x={padL - 8} y={y(t) + 3.5} textAnchor="end" fontSize="9" fill={C.faint} style={mono}>
            {fmt(t)}
          </text>
        </g>
      ))}

      {bandColour && (
        <path
          d={[
            ...plan.values.map((v, i) =>
              v === null || !Number.isFinite(v) ? '' : `${i === 0 ? 'M' : 'L'}${x(i)},${y(v)}`
            ).filter(Boolean),
            ...baseline.values
              .map((v, i) => ({ v, i }))
              .reverse()
              .map(({ v, i }) => v === null || !Number.isFinite(v) ? '' : `L${x(i)},${y(v)}`)
              .filter(Boolean),
            'Z',
          ].filter(Boolean).join(' ')}
          fill={bandColour}
          fillOpacity="0.12"
          stroke="none"
        />
      )}

      {years.map((yr, i) => (
        <text key={yr} x={x(i)} y={H - 6} textAnchor="middle" fontSize="9" fill={C.faint} style={mono}>
          {yr}
        </text>
      ))}

      {series.map((s) => {
        const pts = s.values
          .map((v, i) => (v === null || !Number.isFinite(v) ? null : `${x(i)},${y(v)}`))
          .filter((p): p is string => p !== null)
          .join(' ')
        const last = lastFinite(s.values)
        return (
          <g key={s.label}>
            <polyline
              points={pts}
              fill="none"
              stroke={s.color}
              strokeWidth="2"
              strokeLinejoin="round"
              strokeLinecap="round"
              strokeDasharray={s.dashed ? '5 4' : undefined}
            />
            {s.values.map((v, i) =>
              v !== null && Number.isFinite(v) ? (
                <circle key={i} cx={x(i)} cy={y(v)} r="2.6" fill={C.bg} stroke={s.color} strokeWidth="1.5" />
              ) : null,
            )}
            {last !== null && (
              <text
                x={W - padR + 7}
                y={y(last) + 3.5}
                fontSize="9.5"
                fill={s.color}
                style={mono}
              >
                {fmt(last)}
              </text>
            )}
          </g>
        )
      })}
    </svg>
  )
}