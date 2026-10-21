import { C, mono } from '../theme'

type Series = { label: string; values: number[]; color: string; dashed?: boolean }

/**
 * A small two-line chart drawn as inline SVG: no chart library needed.
 * Baseline and intervention share one y-scale so they're directly comparable.
 */
export function LineChart({ years, series, format }: {
  years: string[]
  series: Series[]
  format?: (v: number) => string
}) {
  const W = 560
  const H = 170
  const padL = 62
  const padR = 14
  const padT = 14
  const padB = 26

  const all = series.flatMap((s) => s.values).filter((v) => Number.isFinite(v))
  if (all.length === 0 || years.length === 0) return null

  let min = Math.min(...all)
  let max = Math.max(...all)
  const allPositive = min >= 0

  if (min === max) {
    // A flat line still needs a range to sit inside.
    const span = Math.abs(min) || 1
    min -= span * 0.5
    max += span * 0.5
  } else {
    const pad = (max - min) * 0.1
    max += pad
    min -= pad
  }

  // Quantities that cannot go negative shouldn't show a negative axis.
  if (allPositive) min = Math.max(0, min)
  if (max < 0) max = 0

  const x = (i: number) =>
    padL + (i / Math.max(1, years.length - 1)) * (W - padL - padR)
  const y = (v: number) =>
    padT + (1 - (v - min) / (max - min)) * (H - padT - padB)

  const fmt = format ?? ((v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 1 }))

  // Horizontal guide lines at top, middle and bottom of the range.
  const ticks = [max, (max + min) / 2, min]
  const zeroY = min < 0 && max > 0 ? y(0) : null

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img"
      aria-label={series.map((s) => s.label).join(' versus ')}>
      {ticks.map((t, i) => (
        <g key={i}>
          <line x1={padL} x2={W - padR} y1={y(t)} y2={y(t)} stroke={C.line} strokeWidth="1" />
          <text x={padL - 8} y={y(t) + 3.5} textAnchor="end" fontSize="9.5" fill={C.faint} style={mono}>
            {fmt(t)}
          </text>
        </g>
      ))}

      {zeroY !== null && (
        <line x1={padL} x2={W - padR} y1={zeroY} y2={zeroY}
          stroke="#6d5c6a" strokeWidth="1" strokeDasharray="3 3" />
      )}

      {years.map((yr, i) => (
        <text key={yr} x={x(i)} y={H - 7} textAnchor="middle" fontSize="9.5" fill={C.faint} style={mono}>
          {yr}
        </text>
      ))}

      {series.map((s) => {
        const pts = s.values
          .map((v, i) => (Number.isFinite(v) ? `${x(i)},${y(v)}` : null))
          .filter(Boolean)
          .join(' ')
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
              Number.isFinite(v) ? (
                <circle key={i} cx={x(i)} cy={y(v)} r="3" fill={C.bg} stroke={s.color} strokeWidth="1.6" />
              ) : null,
            )}
          </g>
        )
      })}
    </svg>
  )
}